"""
api/schemas.py
───────────────
Pydantic v2 request/response models for the FastAPI layer.
"""

from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question:   str            = Field(..., min_length=1, max_length=2000)
    session_id: str | None     = Field(None, description="Omit to start a new session.")
    filters:    dict[str, Any] | None = Field(None, description="country, practice, year, doc_type")


class IngestRequest(BaseModel):
    file_path: str             = Field(..., description="Absolute path to the document on the server")
    metadata:  dict[str, Any] | None = Field(None)


class Citation(BaseModel):
    label:         str
    source_file:   str
    page_label:    str
    page:          Any
    section:       str
    engagement_id: str
    doc_type:      str
    kind:          str = "text"   # text | table | image


class ChatResponse(BaseModel):
    session_id:       str
    answer:           str
    citations:        list[Citation]
    tables:           list[str]   # markdown table strings extracted from the answer
    queries_used:     list[str]
    chunks_retrieved: int
    latency_ms:       int


class ResetResponse(BaseModel):
    session_id: str
    cleared:    bool


class HealthResponse(BaseModel):
    status:  str
    version: str


class StatusResponse(BaseModel):
    total_chunks:    int
    total_documents: int
    namespaces:      dict[str, int]


class DocumentListResponse(BaseModel):
    documents: list[dict[str, Any]]


class IngestResponse(BaseModel):
    file_path:      str
    chunks_indexed: int
    success:        bool
