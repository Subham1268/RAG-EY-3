"""
agent/nodes.py
───────────────
LangGraph node functions — updated for hybrid ColPali + chunk retrieval.

Key changes from previous version:
  1. retriever_node     — calls BOTH hybrid_retrieval (chunks) AND colpali_retrieval (pages),
                          merges results, tags each hit with its source pipeline.
  2. context_builder_node — fetches full chunk text AND ColPali page images.
                            Page images are passed to the generator as vision content.
  3. generator_node     — sends a multimodal message to GPT-4o:
                          text context (from chunks) + page images (from ColPali).
                          This gives GPT-4o both precise text AND visual context.

All other nodes (query_rewriter, retrieval_grader, reranker, reflection) unchanged.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, TypedDict

from langchain_openai import ChatOpenAI

from agent.prompts import (
    AGENT_SYSTEM_PROMPT,
    GENERATION_PROMPT,
    QUERY_REWRITE_PROMPT,
    REFLECTION_PROMPT,
)
from agent.tools import (
    colpali_retrieval,
    fetch_colpali_page,
    fetch_full_chunk,
    hybrid_retrieval,
)
from config.settings import get_settings

settings = get_settings()

# ── LLM instances ─────────────────────────────────────────────────────────────

_llm = ChatOpenAI(
    model=settings.openai_chat_model,
    temperature=0,
    openai_api_key=settings.openai_api_key,
)

_llm_json = ChatOpenAI(
    model=settings.openai_chat_model,
    temperature=0,
    model_kwargs={"response_format": {"type": "json_object"}},
    openai_api_key=settings.openai_api_key,
)

# ── State schema ──────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    question:          str
    chat_history:      list[dict]
    rewritten_queries: list[str]
    raw_chunks:        list[dict]   # chunk hits from hybrid_retrieval
    colpali_pages:     list[dict]   # page hits from colpali_retrieval (NEW)
    graded_chunks:     list[dict]
    reranked_chunks:   list[dict]
    full_chunks:       list[dict]
    page_images:       list[dict]   # fetched ColPali page images (NEW)
    context:           str
    answer:            str
    citations:         list[dict]
    reflection_loops:  int
    reflection_result: dict
    final_answer:      str


# ── Node 1: Query Rewriter ────────────────────────────────────────────────────

async def query_rewriter_node(state: AgentState) -> dict:
    history_str = "\n".join(
        f"{m['role'].upper()}: {m['content']}"
        for m in state["chat_history"][-6:]
    )
    prompt = QUERY_REWRITE_PROMPT.format(
        n=2,
        history=history_str or "None",
        question=state["question"],
    )
    response = await _llm.ainvoke(prompt)
    raw = response.content.strip()

    try:
        queries = json.loads(raw)
        if not isinstance(queries, list):
            queries = [state["question"]]
    except Exception:
        queries = re.findall(r'"([^"]+)"', raw) or [state["question"]]

    if state["question"] not in queries:
        queries.insert(0, state["question"])

    return {"rewritten_queries": queries[:2]}


# ── Node 2: Retriever (UPDATED — hybrid + ColPali) ────────────────────────────

async def retriever_node(state: AgentState) -> dict:
    """
    Run hybrid chunk retrieval AND ColPali page retrieval in parallel.
    
    - hybrid_retrieval  → fine-grained chunk hits (text, tables, image descriptions)
    - colpali_retrieval → page-level visual hits (for GPT-4o image context)
    
    Both use the same query. ColPali degrades gracefully if not installed.
    """
    queries = state["rewritten_queries"]

    # ── Chunk retrieval (parallel across queries) ─────────────────────────────
    chunk_tasks = [
        hybrid_retrieval(q, top_k=settings.max_retrieval_k)
        for q in queries
    ]

    # ── ColPali page retrieval (use first/primary query only) ─────────────────
    # ColPali is slower so we use one query rather than all rewritten variants
    colpali_task = colpali_retrieval(
        queries[0],    # primary query
        top_k=5,       # top 5 pages is enough for visual context
    )

    # Run all in parallel
    *chunk_results_list, colpali_results = await asyncio.gather(
        *chunk_tasks, colpali_task
    )

    # ── Merge + deduplicate chunk results ─────────────────────────────────────
    merged: dict[str, dict] = {}
    for results in chunk_results_list:
        for chunk in results:
            cid = chunk["chunk_id"]
            if cid not in merged or chunk["score"] > merged[cid]["score"]:
                merged[cid] = chunk

    sorted_chunks = sorted(merged.values(), key=lambda x: x["score"], reverse=True)

    return {
        "raw_chunks":    sorted_chunks[:settings.max_retrieval_k],
        "colpali_pages": colpali_results,   # page hits (may be empty if ColPali disabled)
    }


# ── Node 3: Retrieval Grader (pass-through for speed) ────────────────────────

async def retrieval_grader_node(state: AgentState) -> dict:
    return {"graded_chunks": state["raw_chunks"]}


# ── Node 4: Reranker (score-based, no Cohere call) ────────────────────────────

async def reranker_node(state: AgentState) -> dict:
    chunks = state["graded_chunks"]
    if not chunks:
        return {"reranked_chunks": []}
    top_n    = settings.rerank_top_n
    reranked = sorted(chunks, key=lambda x: x.get("score", 0), reverse=True)[:top_n]
    return {"reranked_chunks": reranked}


# ── Node 5: Context Builder (UPDATED — fetches chunks + ColPali page images) ──

async def context_builder_node(state: AgentState) -> dict:
    """
    1. Fetch full chunk text from Postgres for all reranked chunks.
    2. Fetch page images from Postgres for all ColPali page hits.
    3. Build text context string (for prompt).
    4. Store page_images list (passed to generator for GPT-4o vision).
    """
    chunks       = state["reranked_chunks"]
    colpali_hits = state.get("colpali_pages", [])

    if not chunks and not colpali_hits:
        return {
            "context":     "No relevant content found in the EY Middle East knowledge base.",
            "full_chunks": [],
            "citations":   [],
            "page_images": [],
        }

    # ── Fetch full chunk texts ────────────────────────────────────────────────
    full_tasks = [fetch_full_chunk(c["chunk_id"]) for c in chunks]
    full_data  = await asyncio.gather(*full_tasks)
    full_chunks = [f for f in full_data if f is not None]

    citations: list[dict]    = []
    context_parts: list[str] = []

    for i, fc in enumerate(full_chunks, 1):
        source_file   = fc.get("source_file", "Unknown")
        page_or_slide = fc.get("page_or_slide", "N/A")
        section_title = fc.get("section_title", "")
        doc_type      = fc.get("doc_type", "")
        engagement_id = fc.get("engagement_id", "")
        kind          = fc.get("kind", "text")
        content       = fc.get("content", "")[:1500]

        label      = f"Source {i}"
        page_label = "Page" if doc_type == "pdf" else "Slide" if doc_type == "pptx" else "Section"

        # Tag the kind so GPT knows what type of content this is
        kind_tag = f" [{kind.upper()}]" if kind in ("table", "image") else ""

        context_part = (
            f"[{label}]{kind_tag} {source_file} | {page_label} {page_or_slide}"
            + (f" | {section_title}" if section_title else "")
            + f"\n{content}"
        )
        context_parts.append(context_part)

        citations.append({
            "label":        label,
            "source_file":  source_file,
            "page_label":   page_label,
            "page":         page_or_slide,
            "section":      section_title,
            "engagement_id": engagement_id,
            "doc_type":     doc_type,
            "kind":         kind,
        })

    # ── Fetch ColPali page images ─────────────────────────────────────────────
    page_image_tasks = [fetch_colpali_page(hit["page_id"]) for hit in colpali_hits]
    page_image_data  = await asyncio.gather(*page_image_tasks)
    page_images      = [p for p in page_image_data if p is not None]

    context = "\n\n---\n\n".join(context_parts)
    return {
        "context":     context,
        "full_chunks": full_chunks,
        "citations":   citations,
        "page_images": page_images,   # list of {page_image_b64, source_file, page_idx, ...}
    }


# ── Node 6: Generator (UPDATED — multimodal GPT-4o with page images) ──────────

async def generator_node(state: AgentState) -> dict:
    """
    Multimodal generation:
      - System prompt + chat history (as before)
      - Text context from chunks (as before)
      - Page images from ColPali hits passed as vision content (NEW)

    GPT-4o receives both the text descriptions AND the actual page images,
    giving it full visual understanding of charts, tables, and diagrams.

    If no ColPali pages are available, falls back to text-only generation.
    """
    page_images = state.get("page_images", [])

    prompt_text = GENERATION_PROMPT.format(
        question=state["question"],
        context=state["context"],
    )

    # ── Text-only path (no ColPali pages) ────────────────────────────────────
    if not page_images:
        messages = [
            {"role": "system", "content": AGENT_SYSTEM_PROMPT},
            *state["chat_history"][-4:],
            {"role": "user", "content": prompt_text},
        ]
        response = await _llm.ainvoke(messages)
        return {"answer": response.content.strip()}

    # ── Multimodal path (with ColPali page images) ────────────────────────────
    # Build a multimodal user message: text prompt + page images
    # Cap at 3 page images to keep token cost reasonable
    images_to_send = page_images[:3]

    user_content: list[dict] = [
        {"type": "text", "text": prompt_text},
    ]

    for pg in images_to_send:
        img_b64   = pg.get("page_image_b64", "")
        page_idx  = pg.get("page_idx", 0)
        src_file  = pg.get("source_file", "")
        if not img_b64:
            continue
        user_content.append({
            "type": "text",
            "text": f"[Page image: {src_file}, page {page_idx + 1}]",
        })
        user_content.append({
            "type": "image_url",
            "image_url": {
                "url":    f"data:image/png;base64,{img_b64}",
                "detail": "low",   # use "high" for dense data charts if token budget allows
            },
        })

    # Use the raw OpenAI client for multimodal (LangChain handles this too
    # but direct client is cleaner for mixed content lists)
    import openai
    from config.settings import get_settings as _gs
    _settings = _gs()
    client = openai.AsyncOpenAI(api_key=_settings.openai_api_key)

    openai_messages = [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
        *state["chat_history"][-4:],
        {"role": "user", "content": user_content},
    ]

    response = await client.chat.completions.create(
        model=_settings.openai_chat_model,
        messages=openai_messages,
        max_tokens=1500,
        temperature=0,
    )
    return {"answer": response.choices[0].message.content.strip()}


# ── Node 7: Reflection Grader ─────────────────────────────────────────────────

async def reflection_grader_node(state: AgentState) -> dict:
    if settings.max_reflection_loops == 0:
        return {
            "reflection_result": {"quality": "good"},
            "final_answer":      state["answer"],
        }
    prompt = REFLECTION_PROMPT.format(
        question=state["question"],
        answer=state["answer"],
    )
    try:
        response = await _llm_json.ainvoke(prompt)
        result   = json.loads(response.content)
    except Exception:
        result = {"quality": "good", "reason": "Evaluation parse error."}
    return {
        "reflection_result": result,
        "final_answer": state["answer"] if result.get("quality") == "good" else "",
    }


# ── Node 8: Conditional edge ──────────────────────────────────────────────────

def should_retry(state: AgentState) -> str:
    if settings.max_reflection_loops == 0:
        return "end"
    loops  = state.get("reflection_loops", 0)
    result = state.get("reflection_result", {})
    if (
        result.get("quality") == "needs_improvement"
        and loops < settings.max_reflection_loops
        and result.get("suggested_followup_query")
    ):
        return "retry"
    return "end"


# ── Node 9: Retry Prep ────────────────────────────────────────────────────────

async def retry_prep_node(state: AgentState) -> dict:
    followup = state["reflection_result"].get("suggested_followup_query", state["question"])
    return {
        "question":        followup,
        "reflection_loops": state.get("reflection_loops", 0) + 1,
        "raw_chunks":      [],
        "colpali_pages":   [],
        "graded_chunks":   [],
        "reranked_chunks": [],
        "page_images":     [],
    }
