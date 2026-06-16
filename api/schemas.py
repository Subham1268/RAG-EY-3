"""
api/schemas.py
───────────────
Pydantic v2 request/response models for the FastAPI layer.
"""

from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field


# ── Request models ────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    question:   str = Field(..., min_length=1, max_length=2000,
                            description="The consultant's question")
    session_id: str | None = Field(None,
                            description="Session ID for conversation continuity. "
                                        "If omitted, a new session is created.")
    filters: dict[str, Any] | None = Field(None,
                            description="Optional metadata filters: country, practice, year, doc_type")


class IngestRequest(BaseModel):
    file_path: str = Field(..., description="Absolute path to the document on the server")
    metadata:  dict[str, Any] | None = Field(None,
                            description="Project metadata: engagement_id, client, country, practice, year")


# ── Response models ───────────────────────────────────────────────────────────

class Citation(BaseModel):
    label:         str
    source_file:   str
    page_label:    str   # "Page" | "Slide" | "Section"
    page:          Any   # int or str "N/A"
    section:       str
    engagement_id: str
    doc_type:      str


class ChatResponse(BaseModel):
    session_id:       str
    answer:           str
    citations:        list[Citation]
    queries_used:     list[str]
    chunks_retrieved: int
    latency_ms:       int


class ResetResponse(BaseModel):
    session_id: str
    cleared:    bool


class HealthResponse(BaseModel):
    status:  str
    version: str


class DocumentListResponse(BaseModel):
    documents: list[dict[str, Any]]


class IngestResponse(BaseModel):
    file_path:      str
    chunks_indexed: int
    success:        bool
