"""
agent/nodes.py – Optimized for speed (faster LLM, fewer calls, pass-through grader)
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, TypedDict

from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from agent.prompts import (
    AGENT_SYSTEM_PROMPT,
    GENERATION_PROMPT,
    QUERY_REWRITE_PROMPT,
    REFLECTION_PROMPT,
    RETRIEVAL_GRADE_PROMPT,
)
from agent.tools import fetch_full_chunk, hybrid_retrieval
from config.settings import get_settings

# ── Load settings ─────────────────────────────────────────────────────────────
settings = get_settings()

# ── Fast LLM instances (gpt-4o-mini recommended) ─────────────────────────────
_llm = ChatOpenAI(
    model=settings.openai_chat_model,
    temperature=0,
    openai_api_key=settings.openai_api_key
)

_llm_json = ChatOpenAI(
    model=settings.openai_chat_model,
    temperature=0,
    model_kwargs={"response_format": {"type": "json_object"}},
    openai_api_key=settings.openai_api_key
)

# ── State schema (unchanged) ─────────────────────────────────────────────────
class AgentState(TypedDict):
    question: str
    chat_history: list[dict]
    rewritten_queries: list[str]
    raw_chunks: list[dict]
    graded_chunks: list[dict]
    reranked_chunks: list[dict]
    full_chunks: list[dict]
    context: str
    answer: str
    citations: list[dict]
    reflection_loops: int
    reflection_result: dict
    final_answer: str


# ⚡ 1. Query Rewriter – only 2 queries (faster)
async def query_rewriter_node(state: AgentState) -> dict:
    history_str = "\n".join(
        f"{m['role'].upper()}: {m['content']}"
        for m in state["chat_history"][-6:]
    )
    prompt = QUERY_REWRITE_PROMPT.format(
        n=2,  # <-- was 3, now 2 queries
        history=history_str or "None",
        question=state["question"],
    )
    response = await _llm.ainvoke(prompt)
    raw = response.content.strip()
    try:
        queries = json.loads(raw)
        if not isinstance(queries, list):
            queries = [state["question"]]
    except:
        queries = re.findall(r'"([^"]+)"', raw) or [state["question"]]
    if state["question"] not in queries:
        queries.insert(0, state["question"])
    return {"rewritten_queries": queries[:2]}  # cap at 2


# 2. Retriever (unchanged)
async def retriever_node(state: AgentState) -> dict:
    tasks = [
        hybrid_retrieval(q, top_k=settings.max_retrieval_k)
        for q in state["rewritten_queries"]
    ]
    results_per_query = await asyncio.gather(*tasks)
    merged: dict[str, dict] = {}
    for results in results_per_query:
        for chunk in results:
            cid = chunk["chunk_id"]
            if cid not in merged or chunk["score"] > merged[cid]["score"]:
                merged[cid] = chunk
    sorted_chunks = sorted(merged.values(), key=lambda x: x["score"], reverse=True)
    return {"raw_chunks": sorted_chunks[:settings.max_retrieval_k]}


# ⚡ 3. Retrieval Grader – SKIP LLM (pass‑through) – saves ~40% time
async def retrieval_grader_node(state: AgentState) -> dict:
    # No LLM call – keep all raw chunks as graded
    return {"graded_chunks": state["raw_chunks"]}


# ⚡ 4. Reranker – simple score‑based, no Cohere call
async def reranker_node(state: AgentState) -> dict:
    chunks = state["graded_chunks"]
    if not chunks:
        return {"reranked_chunks": []}
    top_n = settings.rerank_top_n
    reranked = sorted(chunks, key=lambda x: x.get("score", 0), reverse=True)[:top_n]
    return {"reranked_chunks": reranked}


# 5. Context Builder (unchanged)
async def context_builder_node(state: AgentState) -> dict:
    chunks = state["reranked_chunks"]
    if not chunks:
        return {
            "context": "No relevant content found.",
            "full_chunks": [],
            "citations": [],
        }
    full_tasks = [fetch_full_chunk(c["chunk_id"]) for c in chunks]
    full_data = await asyncio.gather(*full_tasks)
    full_chunks = [f for f in full_data if f is not None]
    citations = []
    context_parts = []
    for i, fc in enumerate(full_chunks, 1):
        source_file = fc.get("source_file", "Unknown")
        page_or_slide = fc.get("page_or_slide", "N/A")
        section_title = fc.get("section_title", "")
        doc_type = fc.get("doc_type", "")
        engagement_id = fc.get("engagement_id", "")
        content = fc.get("content", "")[:1500]
        label = f"Source {i}"
        page_label = "Page" if doc_type == "pdf" else "Slide" if doc_type == "pptx" else "Section"
        context_part = (
            f"[{label}] {source_file} | {page_label} {page_or_slide}"
            + (f" | {section_title}" if section_title else "")
            + f"\n{content}"
        )
        context_parts.append(context_part)
        citations.append({
            "label": label,
            "source_file": source_file,
            "page_label": page_label,
            "page": page_or_slide,
            "section": section_title,
            "engagement_id": engagement_id,
            "doc_type": doc_type,
        })
    context = "\n\n---\n\n".join(context_parts)
    return {"context": context, "full_chunks": full_chunks, "citations": citations}


# 6. Generator (unchanged)
async def generator_node(state: AgentState) -> dict:
    prompt = GENERATION_PROMPT.format(
        question=state["question"],
        context=state["context"],
    )
    messages = [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
        *state["chat_history"][-4:],
        {"role": "user", "content": prompt},
    ]
    response = await _llm.ainvoke(messages)
    return {"answer": response.content.strip()}


# ⚡ 7. Reflection Grader – SKIP if max loops = 0
async def reflection_grader_node(state: AgentState) -> dict:
    # If reflection disabled, immediately accept answer
    if settings.max_reflection_loops == 0:
        return {
            "reflection_result": {"quality": "good"},
            "final_answer": state["answer"],
        }
    # Otherwise run the normal check
    prompt = REFLECTION_PROMPT.format(
        question=state["question"],
        answer=state["answer"],
    )
    try:
        response = await _llm_json.ainvoke(prompt)
        result = json.loads(response.content)
    except Exception:
        result = {"quality": "good", "reason": "Evaluation parse error."}
    return {
        "reflection_result": result,
        "final_answer": state["answer"] if result.get("quality") == "good" else "",
    }


# 8. Conditional edge (respects settings)
def should_retry(state: AgentState) -> str:
    if settings.max_reflection_loops == 0:
        return "end"
    loops = state.get("reflection_loops", 0)
    result = state.get("reflection_result", {})
    if (
        result.get("quality") == "needs_improvement"
        and loops < settings.max_reflection_loops
        and result.get("suggested_followup_query")
    ):
        return "retry"
    return "end"


# 9. Retry prep node (unchanged)
async def retry_prep_node(state: AgentState) -> dict:
    followup = state["reflection_result"].get("suggested_followup_query", state["question"])
    return {
        "question": followup,
        "reflection_loops": state.get("reflection_loops", 0) + 1,
        "raw_chunks": [],
        "graded_chunks": [],
        "reranked_chunks": [],
    }