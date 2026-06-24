"""
ingestion/indexer.py
─────────────────────
Writes embedded chunks to:
  1. Pinecone    – vector index (text-chunks & image-chunks namespaces)
  2. PostgreSQL  – metadata store for filtered retrieval
"""

from __future__ import annotations

import json
from typing import Sequence

from pinecone import Pinecone, ServerlessSpec
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from config.settings import get_settings
from ingestion.embedder import EmbeddedChunk

settings = get_settings()

CREATE_CHUNKS_TABLE = """
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id        TEXT PRIMARY KEY,
    kind            TEXT NOT NULL,
    content         TEXT NOT NULL,
    image_b64       TEXT,
    source_file     TEXT NOT NULL,
    doc_type        TEXT NOT NULL,
    page_or_slide   INTEGER,
    section_title   TEXT,
    engagement_id   TEXT,
    client          TEXT,
    country         TEXT,
    practice        TEXT,
    year            INTEGER,
    extra_metadata  JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW()
)
"""

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_chunks_engagement ON chunks(engagement_id)",
    "CREATE INDEX IF NOT EXISTS idx_chunks_client ON chunks(client)",
    "CREATE INDEX IF NOT EXISTS idx_chunks_country ON chunks(country)",
    "CREATE INDEX IF NOT EXISTS idx_chunks_doc_type ON chunks(doc_type)",
]


class DocumentIndexer:
    """Persists EmbeddedChunks to Pinecone + PostgreSQL."""

    UPSERT_BATCH = 100

    def __init__(self, engine: AsyncEngine | None = None) -> None:
        pc = Pinecone(api_key=settings.pinecone_api_key)
        if settings.pinecone_index_name not in [i.name for i in pc.list_indexes()]:
            pc.create_index(
                name=settings.pinecone_index_name,
                dimension=1536,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1"),
            )
        self.index = pc.Index(settings.pinecone_index_name)
        self.engine = engine or create_async_engine(settings.database_url, echo=False)

    async def init_db(self) -> None:
        async with self.engine.begin() as conn:
            await conn.execute(text(CREATE_CHUNKS_TABLE))
            for idx_sql in CREATE_INDEXES:
                await conn.execute(text(idx_sql))

    async def index_chunks(self, embedded_chunks: list[EmbeddedChunk]) -> None:
        await self._upsert_pinecone(embedded_chunks)
        await self._upsert_postgres(embedded_chunks)

    async def _upsert_pinecone(self, embedded_chunks: list[EmbeddedChunk]) -> None:
        text_records:  list[dict] = []
        image_records: list[dict] = []

        for ec in embedded_chunks:
            chunk = ec.chunk
            meta = {
                "chunk_id":        chunk.chunk_id,
                "kind":            chunk.kind,
                "source_file":     chunk.metadata.get("source_file", ""),
                "doc_type":        chunk.metadata.get("doc_type", ""),
                "engagement_id":   chunk.metadata.get("engagement_id", ""),
                "client":          chunk.metadata.get("client", ""),
                "country":         chunk.metadata.get("country", ""),
                "practice":        chunk.metadata.get("practice", ""),
                "year":            chunk.metadata.get("year", 0),
                "page_or_slide":   chunk.metadata.get("page_or_slide", 0),
                "section_title":   chunk.metadata.get("section_title", ""),
                "content_preview": chunk.content[:500],
            }
            record = {"id": chunk.chunk_id, "values": ec.embedding, "metadata": meta}
            if chunk.kind == "image":
                image_records.append(record)
            else:
                text_records.append(record)

        ns_text  = settings.pinecone_namespace_text
        ns_image = settings.pinecone_namespace_image

        for i in range(0, len(text_records), self.UPSERT_BATCH):
            self.index.upsert(vectors=text_records[i : i + self.UPSERT_BATCH], namespace=ns_text)
        for i in range(0, len(image_records), self.UPSERT_BATCH):
            self.index.upsert(vectors=image_records[i : i + self.UPSERT_BATCH], namespace=ns_image)

    @staticmethod
    def _as_text(value) -> str:
        """Coerce metadata values to a TEXT-safe string.

        The LLM metadata extractor sometimes returns lists (e.g. country=['UAE'])
        or non-string scalars. Postgres TEXT columns need a plain string.
        """
        if value is None:
            return ""
        if isinstance(value, (list, tuple, set)):
            return ", ".join(str(v) for v in value)
        return str(value)

    @staticmethod
    def _as_int(value) -> int | None:
        """Coerce a year-like value to int, or None if it isn't numeric."""
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    async def _upsert_postgres(self, embedded_chunks: list[EmbeddedChunk]) -> None:
        known_keys = {
            "doc_type", "source_file", "page_or_slide", "section_title",
            "engagement_id", "client", "country", "practice", "year", "kind",
        }
        async with AsyncSession(self.engine) as session:
            async with session.begin():
                for ec in embedded_chunks:
                    chunk = ec.chunk
                    meta  = chunk.metadata
                    extra = {k: v for k, v in meta.items() if k not in known_keys}

                    await session.execute(text("""
                        INSERT INTO chunks (
                            chunk_id, kind, content, image_b64,
                            source_file, doc_type, page_or_slide, section_title,
                            engagement_id, client, country, practice, year,
                            extra_metadata
                        ) VALUES (
                            :chunk_id, :kind, :content, :image_b64,
                            :source_file, :doc_type, :page_or_slide, :section_title,
                            :engagement_id, :client, :country, :practice, :year,
                            :extra_metadata
                        )
                        ON CONFLICT (chunk_id) DO UPDATE SET
                            content        = EXCLUDED.content,
                            extra_metadata = EXCLUDED.extra_metadata
                    """), {
                        "chunk_id":       chunk.chunk_id,
                        "kind":           chunk.kind,
                        "content":        chunk.content,
                        "image_b64":      chunk.image_b64,
                        "source_file":    self._as_text(meta.get("source_file", "")),
                        "doc_type":       self._as_text(meta.get("doc_type", "")),
                        "page_or_slide":  self._as_int(meta.get("page_or_slide")),
                        "section_title":  self._as_text(meta.get("section_title", "")),
                        "engagement_id":  self._as_text(meta.get("engagement_id", "")),
                        "client":         self._as_text(meta.get("client", "")),
                        "country":        self._as_text(meta.get("country", "")),
                        "practice":       self._as_text(meta.get("practice", "")),
                        "year":           self._as_int(meta.get("year")),
                        "extra_metadata": json.dumps(extra),
                    })
