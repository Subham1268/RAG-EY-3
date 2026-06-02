"""
# agent/nodes.py
# ───────────────
# Individual node functions for the LangGraph state machine.

# Nodes (in execution order):
#   1. query_rewriter       – Multi-query generation for diverse retrieval
#   2. retriever            – Hybrid Pinecone search (parallel multi-query)
#   3. retrieval_grader     – Filter out irrelevant chunks (self-RAG)
#   4. reranker             – Cohere cross-encoder reranking
#   5. context_builder      – Fetch full texts and build LLM context
#   6. generator            – GPT-4o answer generation
#   7. reflection_grader    – CRAG self-evaluation
#   8. should_retry         – Conditional edge: retry or end

# State schema defined at top. All nodes are async.
agent/nodes.py – Optimized for speed (faster LLM, fewer calls, pass-through grader)
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Annotated, Any, TypedDict
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
# from agent.tools import (
#     fetch_full_chunk,
#     hybrid_retrieval,
#     rerank_chunks,
# )
# from config.settings import get_settings

# settings = get_settings()

# # ── State schema ──────────────────────────────────────────────────────────────

# class AgentState(TypedDict):
#     # Conversation
#     question:         str
#     chat_history:     list[dict]          # [{"role": "user"|"assistant", "content": "..."}]

#     # Retrieval
#     rewritten_queries: list[str]
#     raw_chunks:        list[dict]
#     graded_chunks:     list[dict]
#     reranked_chunks:   list[dict]
#     full_chunks:       list[dict]

#     # Generation
#     context:           str
#     answer:            str
#     citations:         list[dict]

#     # Reflection
#     reflection_loops:  int
#     reflection_result: dict
#     final_answer:      str

# '''
# FOR OPEN-AI'''

# _llm      = ChatOpenAI(model=settings.openai_chat_model, temperature=0)
# _llm_json = ChatOpenAI(model=settings.openai_chat_model, temperature=0,
#                         model_kwargs={"response_format": {"type": "json_object"}})


# # ── LLM instances ─────────────────────────────────────────────────────────────

# '''from langchain_cohere import ChatCohere
# _llm      = ChatCohere(model="command-r7b-12-2024", temperature=0,
#                        cohere_api_key=settings.cohere_api_key)
# _llm_json = ChatCohere(model="command-r7b-12-2024", temperature=0,
#                        cohere_api_key=settings.cohere_api_key)
# '''
# # ── Node 1: Query Rewriter ─────────────────────────────────────────────────────

# async def query_rewriter_node(state: AgentState) -> dict:
#     """
#     Expand the user's question into N diverse search queries using GPT-4o.
#     Implements the Multi-Query Retrieval pattern.
#     """
#     history_str = "\n".join(
#         f"{m['role'].upper()}: {m['content']}"
#         for m in state["chat_history"][-6:]   # last 3 turns
#     )
#     prompt = QUERY_REWRITE_PROMPT.format(
#         n=3,
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

    # Parse JSON array
    try:
        queries = json.loads(raw)
        if not isinstance(queries, list):
            queries = [state["question"]]
#     except json.JSONDecodeError:
#         # Fallback: extract quoted strings
#         queries = re.findall(r'"([^"]+)"', raw) or [state["question"]]

#     # Always include the original question
#     if state["question"] not in queries:
#         queries.insert(0, state["question"])

#     return {"rewritten_queries": queries[:4]}  # cap at 4


# # ── Node 2: Retriever ──────────────────────────────────────────────────────────

# async def retriever_node(state: AgentState) -> dict:
#     """
#     Execute all rewritten queries in parallel against Pinecone.
#     Merge and deduplicate results.
#     """
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

    # Merge + deduplicate (keep highest score per chunk_id)
    merged: dict[str, dict] = {}
    for results in results_per_query:
        for chunk in results:
            cid = chunk["chunk_id"]
            if cid not in merged or chunk["score"] > merged[cid]["score"]:
                merged[cid] = chunk

    sorted_chunks = sorted(merged.values(), key=lambda x: x["score"], reverse=True)
    return {"raw_chunks": sorted_chunks[:settings.max_retrieval_k]}


# # ── Node 3: Retrieval Grader ───────────────────────────────────────────────────

# async def retrieval_grader_node(state: AgentState) -> dict:
#     """
#     Filter out irrelevant chunks using LLM-based relevance grading.
#     Implements the Self-RAG / CRAG pattern.
#     """
#     question = state["question"]
#     chunks   = state["raw_chunks"]

#     # Grade chunks concurrently (batch to avoid rate limits)
#     async def grade_one(chunk: dict) -> dict | None:
#         content = chunk.get("content_preview", "")[:400]
#         prompt  = RETRIEVAL_GRADE_PROMPT.format(
#             question=question, chunk=content
#         )
#         try:
#             response = await _llm_json.ainvoke(prompt)
#             result   = json.loads(response.content)
#             if result.get("relevant", False):
#                 return chunk
#         except Exception:
#             return chunk   # Include on parse failure (fail open)
#         return None

#     batch_size = 10
#     graded: list[dict] = []
#     for i in range(0, len(chunks), batch_size):
#         batch   = chunks[i : i + batch_size]
#         results = await asyncio.gather(*[grade_one(c) for c in batch])
#         graded.extend([r for r in results if r is not None])

#     # If too few graded, keep top raw chunks as fallback
#     if len(graded) < 3 and chunks:
#         graded = chunks[:5]

#     return {"graded_chunks": graded}


# # ── Node 4: Reranker ───────────────────────────────────────────────────────────

# async def reranker_node(state: AgentState) -> dict:
#     """
#     Apply Cohere Rerank v3 cross-encoder to select top-N most relevant chunks.
#     """
#     question = state["question"]
#     chunks   = state["graded_chunks"]

#     if not chunks:
#         return {"reranked_chunks": []}

#     # Cohere rerank is synchronous — run in thread pool
#     reranked = await asyncio.get_event_loop().run_in_executor(
#         None,
#         rerank_chunks,
#         question,
#         chunks,
#         settings.rerank_top_n,
#     )
#     return {"reranked_chunks": reranked}


# # ── Node 5: Context Builder ────────────────────────────────────────────────────

# async def context_builder_node(state: AgentState) -> dict:
#     """
#     Fetch full chunk content from PostgreSQL and assemble the LLM context string.
#     Also extracts citation metadata for the response.
#     """
#     chunks = state["reranked_chunks"]
#     if not chunks:
#         return {
#             "context": "No relevant content found in the EY Middle East knowledge base.",
#             "full_chunks": [],
#             "citations": [],
#         }

#     # Fetch full texts concurrently
#     full_tasks = [fetch_full_chunk(c["chunk_id"]) for c in chunks]
#     full_data  = await asyncio.gather(*full_tasks)

#     full_chunks = [f for f in full_data if f is not None]
#     citations: list[dict] = []
#     context_parts: list[str] = []

#     for i, fc in enumerate(full_chunks, 1):
#         source_file    = fc.get("source_file", "Unknown")
#         page_or_slide  = fc.get("page_or_slide", "N/A")
#         section_title  = fc.get("section_title", "")
#         doc_type       = fc.get("doc_type", "")
#         engagement_id  = fc.get("engagement_id", "")
#         content        = fc.get("content", "")[:1500]  # cap per chunk

#         label = f"Source {i}"
#         page_label = "Page" if doc_type == "pdf" else "Slide" if doc_type == "pptx" else "Section"

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

        # citations.append({
        #     "label":        label,
        #     "source_file":  source_file,
        #     "page_label":   page_label,
        #     "page":         page_or_slide,
        #     "section":      section_title,
        #     "engagement_id": engagement_id,
        #     "doc_type":     doc_type,
        # })

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


# # ── Node 6: Generator ─────────────────────────────────────────────────────────

# async def generator_node(state: AgentState) -> dict:
#     """
#     Generate the final answer using GPT-4o with retrieved context.
#     Implements citation-aware generation.
#     """
# 6. Generator (unchanged)
async def generator_node(state: AgentState) -> dict:
    prompt = GENERATION_PROMPT.format(
        question=state["question"],
        context=state["context"],
    )
    messages = [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
        # *state["chat_history"][-4:],    # Last 2 turns for coherence
        *state["chat_history"][-4:],
        {"role": "user", "content": prompt},
    ]
    response = await _llm.ainvoke(messages)
    return {"answer": response.content.strip()}


# # ── Node 7: Reflection Grader ─────────────────────────────────────────────────

# async def reflection_grader_node(state: AgentState) -> dict:
#     """
#     Self-evaluate the generated answer (CRAG pattern).
#     Returns quality assessment and optional retry query.
#     """
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
    #     result   = json.loads(response.content)
    # except Exception:
    #     result = {"quality": "good", "reason": "Evaluation parse error — accepting answer."}

        result = json.loads(response.content)
    except Exception:
        result = {"quality": "good", "reason": "Evaluation parse error."}
    return {
        "reflection_result": result,
        "final_answer": state["answer"] if result.get("quality") == "good" else "",
    }


# # ── Node 8: Conditional edge ──────────────────────────────────────────────────

# def should_retry(state: AgentState) -> str:
#     """
#     Conditional edge: if reflection says 'needs_improvement' AND we haven't
#     exceeded max loops, re-enter from query rewriting with a refined query.
#     """
#     loops  = state.get("reflection_loops", 0)
#     result = state.get("reflection_result", {})

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

#     return "end"


# # ── Retry prep node ────────────────────────────────────────────────────────────

# async def retry_prep_node(state: AgentState) -> dict:
#     """Inject the reflection's suggested query and increment loop counter."""
#     followup = state["reflection_result"].get("suggested_followup_query", state["question"])
#     return {
#         "question":         followup,
#         "reflection_loops": state.get("reflection_loops", 0) + 1,
#         "raw_chunks":       [],
#         "graded_chunks":    [],
#         "reranked_chunks":  [],
#     }
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
