"""
ingestion/embedder.py
──────────────────────
Generates embeddings for IndexableChunks.

  • Text / Table chunks  → OpenAI text-embedding-3-large (1536-dim)
  • Image chunks         → GPT-4o-mini Vision generates a rich textual description
                           which is then embedded via text-embedding-3-large.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import openai
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import get_settings
from ingestion.chunker import IndexableChunk

settings = get_settings()

IMAGE_CONCURRENCY = 10   # max parallel GPT-4o-mini Vision calls
EMBED_CONCURRENCY = 5    # max parallel embedding batch calls
EMBED_BATCH       = 100  # chunks per embedding API call
EMBEDDING_DIM     = 1536

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

    def __init__(self) -> None:
        self.client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
        self._image_sem = asyncio.Semaphore(IMAGE_CONCURRENCY)
        self._embed_sem = asyncio.Semaphore(EMBED_CONCURRENCY)

    async def embed_chunks(self, chunks: list[IndexableChunk]) -> list[EmbeddedChunk]:
        """
        1. Describe all image chunks in parallel (semaphore-limited).
        2. Patch image chunk content with generated description.
        3. Embed all text representations in parallel batches.
        4. Return EmbeddedChunk list in the same order as input.
        """
        descriptions: list[str | None] = await asyncio.gather(
            *[self._safe_describe(c) for c in chunks]
        )

        texts: list[str] = []
        for chunk, desc in zip(chunks, descriptions):
            if desc:
                chunk.content = desc
            texts.append(chunk.content)

        all_embeddings: list[list[float]] = await self._parallel_batch_embed(texts)

        return [
            EmbeddedChunk(chunk=c, embedding=emb, image_description=desc)
            for c, emb, desc in zip(chunks, all_embeddings, descriptions)
        ]

    async def embed_query(self, query: str) -> list[float]:
        """Embed a single query string (used at retrieval time)."""
        results = await self._embed_batch([query])
        return results[0]

    async def _safe_describe(self, chunk: IndexableChunk) -> str | None:
        if chunk.kind != "image":
            return None
        async with self._image_sem:
            return await self._describe_image(chunk)

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(min=5, max=60))
    async def _describe_image(self, chunk: IndexableChunk) -> str:
        response = await self.client.chat.completions.create(
            model=settings.openai_vision_model,
            max_tokens=300,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{chunk.image_b64}",
                            "detail": "low",
                        },
                    },
                    {"type": "text", "text": IMAGE_CAPTION_PROMPT},
                ],
            }],
        )
        return response.choices[0].message.content.strip()

    async def _parallel_batch_embed(self, texts: list[str]) -> list[list[float]]:
        batches = [
            texts[i : i + EMBED_BATCH]
            for i in range(0, len(texts), EMBED_BATCH)
        ]
        results: list[list[list[float]]] = await asyncio.gather(
            *[self._sem_embed_batch(batch) for batch in batches]
        )
        all_embeddings: list[list[float]] = []
        for batch_result in results:
            all_embeddings.extend(batch_result)
        return all_embeddings

    async def _sem_embed_batch(self, texts: list[str]) -> list[list[float]]:
        async with self._embed_sem:
            return await self._embed_batch(texts)

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(min=5, max=60))
    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        response = await self.client.embeddings.create(
            model=settings.openai_embedding_model,
            input=texts,
            dimensions=EMBEDDING_DIM,
        )
        return [
            item.embedding
            for item in sorted(response.data, key=lambda x: x.index)
        ]
