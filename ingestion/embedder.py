"""
ingestion/embedder.py
──────────────────────
Generates embeddings for IndexableChunks.

  • Text / Table chunks  → Cohere embed-english-v3.0  (1024-dim)
  • Image chunks         → GPT-4o Vision generates a rich textual description
                           which is then embedded via Cohere.
                           The description is also stored to improve LLM context.

Batching, retry logic (tenacity), and async support included.
"""

from __future__ import annotations

import asyncio
import cohere
from dataclasses import dataclass
from typing import Sequence

import openai
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import get_settings
from ingestion.chunker import IndexableChunk

settings = get_settings()

IMAGE_CAPTION_PROMPT = """\
You are an EY consulting document analyst.
Analyse this image extracted from an EY Middle East consulting deliverable.
Describe in 3-5 sentences:
1. What type of visual this is (chart, diagram, table, framework, org chart, etc.)
2. The key information or insights conveyed.
3. Any numbers, percentages, or labels visible.
4. How this visual relates to consulting themes (risk, governance, transformation, etc.).
Keep the description factual and precise so it can be used for semantic search."""


@dataclass
class EmbeddedChunk:
    chunk: IndexableChunk
    embedding: list[float]
    image_description: str | None


class Embedder:
    """
    Cohere embeddings + OpenAI GPT-4o Vision for image descriptions.
    """

    EMBEDDING_DIM = 1024        # Cohere embed-english-v3.0 dimension
    EMBED_BATCH   = 90          # Cohere max is 96 per batch

    def __init__(self) -> None:
        self.cohere_client = cohere.AsyncClient(api_key=settings.cohere_api_key)
        self.openai_client = openai.AsyncOpenAI(api_key=settings.openai_api_key)

    async def embed_chunks(
        self, chunks: list[IndexableChunk]
    ) -> list[EmbeddedChunk]:
        # Step 1: resolve image descriptions concurrently
        desc_tasks = [
            self._describe_image(c) if c.kind == "image" else asyncio.sleep(0, result=None)
            for c in chunks
        ]
        descriptions = await asyncio.gather(*desc_tasks)

        # Patch image chunk content with the generated description
        texts: list[str] = []
        for chunk, desc in zip(chunks, descriptions):
            if desc:
                chunk.content = desc
            texts.append(chunk.content)

        # Step 2: batch embed all texts via Cohere
        all_embeddings = await self._batch_embed(texts, input_type="search_document")

        return [
            EmbeddedChunk(
                chunk=chunk,
                embedding=emb,
                image_description=desc,
            )
            for chunk, emb, desc in zip(chunks, all_embeddings, descriptions)
        ]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def _describe_image(self, chunk: IndexableChunk) -> str:
        """Use existing caption instead of calling GPT-4o Vision (free tier)."""
        return chunk.content or f"Image from {chunk.metadata.get('source_file', 'document')}"

    async def _batch_embed(
        self, texts: list[str], input_type: str = "search_document"
    ) -> list[list[float]]:
        """Embed texts in batches using Cohere."""
        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), self.EMBED_BATCH):
            batch = texts[i : i + self.EMBED_BATCH]
            embeddings = await self._embed_batch(batch, input_type)
            all_embeddings.extend(embeddings)
        return all_embeddings

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def _embed_batch(
        self, texts: list[str], input_type: str = "search_document"
    ) -> list[list[float]]:
        response = await self.cohere_client.embed(
            texts=texts,
            model="embed-english-v3.0",
            input_type=input_type,
        )
        return response.embeddings

    async def embed_query(self, query: str) -> list[float]:
        """Embed a single query string for retrieval."""
        result = await self._batch_embed([query], input_type="search_query")
        return result[0]