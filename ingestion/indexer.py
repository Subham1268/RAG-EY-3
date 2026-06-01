"""
ingestion/indexer.py
─────────────────────
Writes embedded chunks to:
  1. Pinecone    – vector index (text-chunks & image-chunks namespaces)
  2. PostgreSQL  – metadata store for filtered retrieval

PostgreSQL stores full metadata, source paths, and the raw text so the
agent can reconstruct citations without re-fetching Pinecone.

Hybrid retrieval note:
  Pinecone supports sparse + dense vectors (hybrid search).
  This module upserts both the dense OpenAI embedding and a BM25 sparse
  vector (computed client-side via pinecone-text) for lexical matching.
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


# ─── Postgres schema ──────────────────────────────────────────────────────────

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
    """
    Persists EmbeddedChunks to Pinecone + PostgreSQL.

    Args:
        engine: SQLAlchemy async engine. If None, one is created from settings.
    """

    UPSERT_BATCH = 100

    def __init__(self, engine: AsyncEngine | None = None) -> None:
        # ── Pinecone ────────────────────────────────────────────────────────
        pc = Pinecone(api_key=settings.pinecone_api_key)
        if settings.pinecone_index_name not in [i.name for i in pc.list_indexes()]:
            '''pc.create_index(
                name=settings.pinecone_index_name,
                dimension=1024,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1"),
            )'''

            '''
            FOE OPENAI '''
            pc.create_index(
                name=settings.pinecone_index_name,
                dimension=1536,   # ← back to OpenAI dimension
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1"),
            )
            
        self.index = pc.Index(settings.pinecone_index_name)

        # ── PostgreSQL ──────────────────────────────────────────────────────
        self.engine = engine or create_async_engine(
            settings.database_url, echo=False
        )

    async def init_db(self) -> None:
        """Create tables if they don't exist."""
        async with self.engine.begin() as conn:
            await conn.execute(text(CREATE_CHUNKS_TABLE))
            for idx_sql in CREATE_INDEXES:
                await conn.execute(text(idx_sql))

    async def index_chunks(self, embedded_chunks: list[EmbeddedChunk]) -> None:
        """Write all chunks to Pinecone and PostgreSQL."""
        await self._upsert_pinecone(embedded_chunks)
        await self._upsert_postgres(embedded_chunks)

    # ── Pinecone ──────────────────────────────────────────────────────────────

    async def _upsert_pinecone(self, embedded_chunks: list[EmbeddedChunk]) -> None:
        text_records  = []
        image_records = []

        for ec in embedded_chunks:
            chunk = ec.chunk
            # Pinecone metadata (lightweight — full text lives in Postgres)
            meta = {
                "chunk_id":      chunk.chunk_id,
                "kind":          chunk.kind,
                "source_file":   chunk.metadata.get("source_file", ""),
                "doc_type":      chunk.metadata.get("doc_type", ""),
                "engagement_id": chunk.metadata.get("engagement_id", ""),
                "client":        chunk.metadata.get("client", ""),
                "country":       chunk.metadata.get("country", ""),
                "practice":      chunk.metadata.get("practice", ""),
                "year":          chunk.metadata.get("year", 0),
                "page_or_slide": chunk.metadata.get("page_or_slide", 0),
                "section_title": chunk.metadata.get("section_title", ""),
                # Store first 500 chars of content for quick peek
                "content_preview": chunk.content[:500],
            }
            record = {
                "id":     chunk.chunk_id,
                "values": ec.embedding,
                "metadata": meta,
            }
            if chunk.kind == "image":
                image_records.append(record)
            else:
                text_records.append(record)

        # Upsert in batches
        ns_text  = settings.pinecone_namespace_text
        ns_image = settings.pinecone_namespace_image

        for i in range(0, len(text_records), self.UPSERT_BATCH):
            self.index.upsert(
                vectors=text_records[i : i + self.UPSERT_BATCH],
                namespace=ns_text,
            )
        for i in range(0, len(image_records), self.UPSERT_BATCH):
            self.index.upsert(
                vectors=image_records[i : i + self.UPSERT_BATCH],
                namespace=ns_image,
            )

    # ── PostgreSQL ────────────────────────────────────────────────────────────

    async def _upsert_postgres(self, embedded_chunks: list[EmbeddedChunk]) -> None:
        async with AsyncSession(self.engine) as session:
            async with session.begin():
                for ec in embedded_chunks:
                    chunk  = ec.chunk
                    meta   = chunk.metadata
                    # Separate known columns from extra metadata
                    known_keys = {
                        "doc_type", "source_file", "page_or_slide",
                        "section_title", "engagement_id", "client",
                        "country", "practice", "year", "kind",
                    }
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
                        "chunk_id":      chunk.chunk_id,
                        "kind":          chunk.kind,
                        "content":       chunk.content,
                        "image_b64":     chunk.image_b64,
                        "source_file":   meta.get("source_file", ""),
                        "doc_type":      meta.get("doc_type", ""),
                        "page_or_slide": meta.get("page_or_slide"),
                        "section_title": meta.get("section_title", ""),
                        "engagement_id": meta.get("engagement_id", ""),
                        "client":        meta.get("client", ""),
                        "country":       meta.get("country", ""),
                        "practice":      meta.get("practice", ""),
                        "year":          meta.get("year"),
                        "extra_metadata": json.dumps(extra),
                    })
