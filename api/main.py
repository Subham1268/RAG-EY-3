"""
api/main.py
────────────
FastAPI application entry point.

Endpoints:
  POST /chat              – Main conversational RAG endpoint
  POST /chat/reset        – Clear session memory
  GET  /health            – Liveness probe
  GET  /documents         – List indexed documents (with filters)
  POST /ingest            – Trigger ingestion for a new file (admin)
  GET  /metrics           – Basic retrieval quality metrics

Auth:
  All endpoints (except /health) require a valid Azure AD JWT bearer token.
  The token is validated via the AzureADAuth dependency.

CORS:
  Configured to allow requests from the Teams client origin.
"""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from agent.graph import get_graph
from agent.memory import get_memory
from api.auth import AzureADAuth, get_current_user
from api.schemas import (
    ChatRequest,
    ChatResponse,
    Citation,
    DocumentListResponse,
    HealthResponse,
    IngestRequest,
    IngestResponse,
    ResetResponse,
)
from config.settings import get_settings

log      = structlog.get_logger()
settings = get_settings()
auth     = AzureADAuth()


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting EY ME Agentic RAG API")
    # Pre-warm the LangGraph agent
    get_graph()
    get_memory()
    yield
    log.info("Shutting down")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="EY Middle East Knowledge Agent",
    description="Multimodal Agentic RAG for EY consulting knowledge retrieval",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://teams.microsoft.com", "https://*.teams.microsoft.com"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health():
    return HealthResponse(status="healthy", version="1.0.0")


@app.post("/chat", response_model=ChatResponse, tags=["Agent"])
async def chat(
    request:      ChatRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Main conversational endpoint.
    Runs the full LangGraph Agentic RAG pipeline and returns a structured response.
    """
    session_id = request.session_id or str(uuid.uuid4())
    start_time = time.perf_counter()

    log.info("chat_request", session_id=session_id, user=current_user.get("upn"))

    memory  = get_memory()
    history = await memory.get_history(session_id)

    # Add current user message to memory
    await memory.add(session_id, "user", request.question)

    # Run agent
    graph = get_graph()
    try:
        state = await graph.ainvoke({
            "question":          request.question,
            "chat_history":      history,
            "reflection_loops":  0,
            "raw_chunks":        [],
            "colpali_pages":     [],   # ColPali page-level hits
            "graded_chunks":     [],
            "reranked_chunks":   [],
            "full_chunks":       [],
            "page_images":       [],   # Fetched ColPali page images for GPT-4o
            "citations":         [],
            "rewritten_queries": [],
            "context":           "",
            "answer":            "",
            "final_answer":      "",
            "reflection_result": {},
        })
    except Exception as exc:
        import traceback
        tb = traceback.format_exc()
        print("=== AGENT ERROR ===")
        print(tb)
        print("===================")
        raise HTTPException(status_code=500, detail=f"Agent error: {exc}")

    answer    = state.get("final_answer") or state.get("answer", "")
    citations = state.get("citations", [])

    # Store assistant reply in memory
    await memory.add(session_id, "assistant", answer)

    latency_ms = int((time.perf_counter() - start_time) * 1000)
    log.info("chat_response", session_id=session_id, latency_ms=latency_ms,
             chunks_retrieved=len(state.get("reranked_chunks", [])))

    return ChatResponse(
        session_id=session_id,
        answer=answer,
        citations=[Citation(**c) for c in citations],
        queries_used=state.get("rewritten_queries", []),
        chunks_retrieved=len(state.get("reranked_chunks", [])),
        latency_ms=latency_ms,
    )


@app.post("/chat/reset", response_model=ResetResponse, tags=["Agent"])
async def reset_session(
    session_id:   str,
    current_user: dict = Depends(get_current_user),
):
    """Clear the conversation history for a session."""
    await get_memory().clear(session_id)
    return ResetResponse(session_id=session_id, cleared=True)


@app.get("/documents", response_model=DocumentListResponse, tags=["Knowledge Base"])
async def list_documents(
    country:      str | None = None,
    practice:     str | None = None,
    doc_type:     str | None = None,
    year:         int | None = None,
    current_user: dict = Depends(get_current_user),
):
    """List documents in the knowledge base with optional filters."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy import text

    engine = create_async_engine(settings.database_url)
    conditions = ["1=1"]
    params: dict = {}

    if country:
        conditions.append("country ILIKE :country")
        params["country"] = f"%{country}%"
    if practice:
        conditions.append("practice ILIKE :practice")
        params["practice"] = f"%{practice}%"
    if doc_type:
        conditions.append("doc_type = :doc_type")
        params["doc_type"] = doc_type
    if year:
        conditions.append("year = :year")
        params["year"] = year

    where = " AND ".join(conditions)
    async with AsyncSession(engine) as session:
        result = await session.execute(text(f"""
            SELECT DISTINCT source_file, doc_type, client, country,
                   practice, year, engagement_id
            FROM chunks
            WHERE {where}
            ORDER BY year DESC, source_file
            LIMIT 100
        """), params)
        rows = result.mappings().all()

    return DocumentListResponse(documents=[dict(r) for r in rows])


@app.post("/ingest", response_model=IngestResponse, tags=["Admin"])
async def ingest_document(
    request:      IngestRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Trigger ingestion pipeline for a new document.
    The file must be accessible at the provided path on the server.
    """
    from ingestion.chunker import DocumentChunker
    from ingestion.embedder import Embedder
    from ingestion.indexer import DocumentIndexer
    from ingestion.parser import DocumentParser

    import asyncio

    async def run_ingestion():
        parser  = DocumentParser()
        chunker = DocumentChunker(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            project_metadata=request.metadata or {},
        )
        embedder = Embedder()
        indexer  = DocumentIndexer()

        parsed   = parser.parse(request.file_path)
        chunks   = chunker.chunk_document(parsed)
        embedded = await embedder.embed_chunks(chunks)
        await indexer.index_chunks(embedded)
        return len(chunks)

    try:
        n_chunks = await run_ingestion()
        return IngestResponse(
            file_path=request.file_path,
            chunks_indexed=n_chunks,
            success=True,
        )
    except Exception as exc:
        log.error("ingest_error", file=request.file_path, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))
