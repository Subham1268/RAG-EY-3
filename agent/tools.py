"""
agent/tools.py
───────────────
LangChain-compatible tools that the LangGraph agent can invoke.

Tools:
  1. hybrid_retrieval_tool   – semantic + keyword search via Pinecone
  2. metadata_filter_tool    – SQL filter on Postgres for structured facets
  3. rerank_tool             – Cohere Rerank v3 cross-encoder
  4. fetch_full_chunk_tool   – Retrieve full chunk text from Postgres by chunk_id
"""

from __future__ import annotations

import json
from typing import Any

import cohere
from langchain_core.tools import tool
from pinecone import Pinecone
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from config.settings import get_settings
from ingestion.embedder import Embedder

settings = get_settings()

# ── Singletons (initialised lazily) ───────────────────────────────────────────
_pinecone_index = None
_cohere_client  = None
_engine         = None
_embedder       = None


def _get_pinecone():
    global _pinecone_index
    if _pinecone_index is None:
        pc = Pinecone(api_key=settings.pinecone_api_key)
        _pinecone_index = pc.Index(settings.pinecone_index_name)
    return _pinecone_index


def _get_cohere():
    global _cohere_client
    if _cohere_client is None:
        _cohere_client = cohere.Client(settings.cohere_api_key)
    return _cohere_client


def _get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(settings.database_url)
    return _engine


def _get_embedder():
    global _embedder
    if _embedder is None:
        _embedder = Embedder()
    return _embedder


# ── Tool 1: Hybrid Retrieval ──────────────────────────────────────────────────

async def hybrid_retrieval(
    query: str,
    top_k: int = 20,
    filters: dict | None = None,
    include_images: bool = True,
) -> list[dict]:
    """
    Perform semantic similarity search across Pinecone namespaces.

    Args:
        query:          The search query string.
        top_k:          Number of results to retrieve per namespace.
        filters:        Pinecone metadata filters dict.
        include_images: Whether to also search the image namespace.

    Returns:
        List of chunk dicts with chunk_id, score, metadata, content_preview.
    """
    embedder = _get_embedder()
    index    = _get_pinecone()

    query_embedding = await embedder.embed_query(query)

    results = []

    # ─ Text namespace ─────────────────────────────────────────────────────────
    text_response = index.query(
        vector=query_embedding,
        top_k=top_k,
        namespace=settings.pinecone_namespace_text,
        filter=filters or {},
        include_metadata=True,
    )
    for match in text_response.matches:
        results.append({
            "chunk_id":        match.id,
            "score":           match.score,
            "namespace":       "text",
            "metadata":        match.metadata,
            "content_preview": match.metadata.get("content_preview", ""),
        })

    # ─ Image namespace ────────────────────────────────────────────────────────
    if include_images:
        img_response = index.query(
            vector=query_embedding,
            top_k=top_k // 2,
            namespace=settings.pinecone_namespace_image,
            filter=filters or {},
            include_metadata=True,
        )
        for match in img_response.matches:
            results.append({
                "chunk_id":        match.id,
                "score":           match.score,
                "namespace":       "image",
                "metadata":        match.metadata,
                "content_preview": match.metadata.get("content_preview", ""),
            })

    # Deduplicate by chunk_id (keep highest score)
    seen: dict[str, dict] = {}
    for r in results:
        cid = r["chunk_id"]
        if cid not in seen or r["score"] > seen[cid]["score"]:
            seen[cid] = r

    return sorted(seen.values(), key=lambda x: x["score"], reverse=True)


# ── Tool 2: Metadata Filter ───────────────────────────────────────────────────

async def metadata_filter_search(
    query_text: str,
    country: str | None = None,
    practice: str | None = None,
    doc_type: str | None = None,
    year: int | None = None,
    engagement_id: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """
    Full-text search + metadata filter on PostgreSQL.
    Complements Pinecone with structured faceted search.
    """
    engine = _get_engine()

    conditions = ["content ILIKE :query_pattern"]
    params: dict[str, Any] = {"query_pattern": f"%{query_text}%", "limit": limit}

    if country:
        conditions.append("country ILIKE :country")
        params["country"] = country
    if practice:
        conditions.append("practice ILIKE :practice")
        params["practice"] = practice
    if doc_type:
        conditions.append("doc_type = :doc_type")
        params["doc_type"] = doc_type
    if year:
        conditions.append("year = :year")
        params["year"] = year
    if engagement_id:
        conditions.append("engagement_id = :engagement_id")
        params["engagement_id"] = engagement_id

    where = " AND ".join(conditions)
    sql = f"""
        SELECT chunk_id, kind, content, source_file, doc_type,
               page_or_slide, section_title, engagement_id,
               client, country, practice, year
        FROM chunks
        WHERE {where}
        ORDER BY created_at DESC
        LIMIT :limit
    """

    async with AsyncSession(engine) as session:
        result = await session.execute(text(sql), params)
        rows   = result.mappings().all()

    return [dict(row) for row in rows]


# ── Tool 3: Cohere Reranker ───────────────────────────────────────────────────

def rerank_chunks(
    query: str,
    chunks: list[dict],
    top_n: int = 5,
) -> list[dict]:
    """
    Re-rank retrieved chunks using Cohere cross-encoder.

    Args:
        query:   The user query.
        chunks:  List of chunk dicts (must have 'content_preview' or 'content').
        top_n:   Number of chunks to return after reranking.

    Returns:
        Top-N chunks sorted by Cohere relevance score.
    """
    if not chunks:
        return []

    co = _get_cohere()
    documents = [
        c.get("content_preview") or c.get("content", "")[:500]
        for c in chunks
    ]

    response = co.rerank(
        model=settings.cohere_rerank_model,
        query=query,
        documents=documents,
        top_n=min(top_n, len(chunks)),
    )

    reranked = []
    for result in response.results:
        chunk = chunks[result.index].copy()
        chunk["rerank_score"] = result.relevance_score
        reranked.append(chunk)

    return reranked


# ── Tool 4: Fetch Full Chunk ──────────────────────────────────────────────────

async def fetch_full_chunk(chunk_id: str) -> dict | None:
    """
    Retrieve the full content of a chunk from PostgreSQL by chunk_id.
    Used after reranking to get complete text for generation.
    """
    engine = _get_engine()
    async with AsyncSession(engine) as session:
        result = await session.execute(
            text("SELECT * FROM chunks WHERE chunk_id = :cid"),
            {"cid": chunk_id},
        )
        row = result.mappings().first()
    return dict(row) if row else None
