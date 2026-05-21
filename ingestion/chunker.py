"""
ingestion/chunker.py
─────────────────────
Converts raw ParsedDocument chunks into indexable units.

Strategy:
  • Text → LangChain RecursiveCharacterTextSplitter with semantic
    boundary awareness (headings, paragraphs, sentences).
  • Tables → kept whole (or split at row boundaries if very large).
  • Images → kept as single chunks; text description generated via GPT-4o Vision.

Each output chunk carries a rich metadata dict for Pinecone + Postgres filtering.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Literal

from langchain.text_splitter import RecursiveCharacterTextSplitter

from ingestion.parser import ImageChunk, ParsedDocument, TableChunk, TextChunk


ChunkKind = Literal["text", "table", "image"]


@dataclass
class IndexableChunk:
    chunk_id: str               # Deterministic SHA-256 hash
    kind: ChunkKind
    content: str                # Text to embed (description for images)
    image_b64: str | None       # Only for image chunks
    metadata: dict = field(default_factory=dict)


class DocumentChunker:
    """
    Splits a ParsedDocument into IndexableChunks ready for embedding.

    Args:
        chunk_size:    Target character count per text chunk.
        chunk_overlap: Overlap between consecutive chunks.
        project_metadata: Dict of project-level fields to attach to every chunk
                          (e.g. engagement_id, client, country, practice, year).
    """

    def __init__(
        self,
        chunk_size: int = 800,
        chunk_overlap: int = 150,
        project_metadata: dict | None = None,
    ) -> None:
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
        self.project_metadata = project_metadata or {}

    def chunk_document(self, parsed: ParsedDocument) -> list[IndexableChunk]:
        chunks: list[IndexableChunk] = []

        for tc in parsed.text_chunks:
            chunks.extend(self._chunk_text(tc, parsed))

        for tbl in parsed.table_chunks:
            chunks.append(self._chunk_table(tbl, parsed))

        for img in parsed.image_chunks:
            chunks.append(self._chunk_image(img, parsed))

        return chunks

    # ── Text ───────────────────────────────────────────────────────────────────

    def _chunk_text(
        self, tc: TextChunk, parsed: ParsedDocument
    ) -> list[IndexableChunk]:
        splits = self.splitter.split_text(tc.text)
        result = []
        for i, split in enumerate(splits):
            meta = {
                **self.project_metadata,
                "doc_type":       parsed.doc_type,
                "source_file":    parsed.source_file,
                "page_or_slide":  tc.page_or_slide,
                "section_title":  tc.section_title,
                "chunk_index":    i,
                "kind":           "text",
                **tc.metadata,
            }
            result.append(IndexableChunk(
                chunk_id=self._make_id(parsed.source_file, "text", tc.page_or_slide, i),
                kind="text",
                content=split,
                image_b64=None,
                metadata=meta,
            ))
        return result

    # ── Table ──────────────────────────────────────────────────────────────────

    def _chunk_table(
        self, tbl: TableChunk, parsed: ParsedDocument
    ) -> IndexableChunk:
        # Tables are kept whole; very large ones are truncated at 4000 chars
        content = tbl.markdown[:4000]
        meta = {
            **self.project_metadata,
            "doc_type":      parsed.doc_type,
            "source_file":   parsed.source_file,
            "page_or_slide": tbl.page_or_slide,
            "kind":          "table",
            **tbl.metadata,
        }
        return IndexableChunk(
            chunk_id=self._make_id(parsed.source_file, "table", tbl.page_or_slide, 0),
            kind="table",
            content=content,
            image_b64=None,
            metadata=meta,
        )

    # ── Image ──────────────────────────────────────────────────────────────────

    def _chunk_image(
        self, img: ImageChunk, parsed: ParsedDocument
    ) -> IndexableChunk:
        # The embedding pipeline will call GPT-4o Vision to generate a description.
        # Here we store a placeholder; the embedder fills it in.
        meta = {
            **self.project_metadata,
            "doc_type":      parsed.doc_type,
            "source_file":   parsed.source_file,
            "page_or_slide": img.page_or_slide,
            "kind":          "image",
            "caption":       img.caption,
            **img.metadata,
        }
        return IndexableChunk(
            chunk_id=self._make_id(parsed.source_file, "image", img.page_or_slide, 0),
            kind="image",
            content=img.caption,       # placeholder; replaced by embedder
            image_b64=img.image_b64,
            metadata=meta,
        )

    # ── Util ───────────────────────────────────────────────────────────────────

    @staticmethod
    def _make_id(source: str, kind: str, page: int, idx: int) -> str:
        raw = f"{source}|{kind}|{page}|{idx}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]
