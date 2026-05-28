

"""
ingestion/embedder.py
──────────────────────
Generates embeddings for IndexableChunks.

  • Text / Table chunks  → OpenAI text-embedding-3-large (1536-dim)
  • Image chunks         → GPT-4o Vision generates a rich textual description
                           which is then embedded via text-embedding-3-large.
"""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass

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
    EMBEDDING_DIM = 1536
    EMBED_BATCH   = 10          # ← was 100, drop to 10 for free tier

    def __init__(self) -> None:
        self.client = openai.AsyncOpenAI(api_key=settings.openai_api_key)

    async def embed_chunks(
        self, chunks: list[IndexableChunk]
    ) -> list[EmbeddedChunk]:
        # Step 1: describe images ONE AT A TIME with delay
        descriptions = []
        for c in chunks:
            if c.kind == "image":
                desc = await self._describe_image(c)
                descriptions.append(desc)
                await asyncio.sleep(3)   # 3s between each image vision call
            else:
                descriptions.append(None)

        # Patch image chunk content
        texts: list[str] = []
        for chunk, desc in zip(chunks, descriptions):
            if desc:
                chunk.content = desc
            texts.append(chunk.content)

        # Step 2: embed in small batches with delays
        all_embeddings = await self._batch_embed(texts)

        return [
            EmbeddedChunk(chunk=chunk, embedding=emb, image_description=desc)
            for chunk, emb, desc in zip(chunks, all_embeddings, descriptions)
        ]

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(min=10, max=60))
    async def _describe_image(self, chunk: IndexableChunk) -> str:
        """GPT-4o Vision — with retry on rate limit."""
        response = await self.client.chat.completions.create(
            model=settings.openai_vision_model,
            max_tokens=300,             # ← was 400, reduce to save tokens
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{chunk.image_b64}",
                                "detail": "low",   # ← was "high", use "low" = fewer tokens
                            },
                        },
                        {"type": "text", "text": IMAGE_CAPTION_PROMPT},
                    ],
                }
            ],
        )
        return response.choices[0].message.content.strip()

    async def _batch_embed(self, texts: list[str]) -> list[list[float]]:
        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), self.EMBED_BATCH):
            batch = texts[i : i + self.EMBED_BATCH]
            embeddings = await self._embed_batch(batch)
            all_embeddings.extend(embeddings)
            await asyncio.sleep(60)      # ← 5s between every batch of 10
        return all_embeddings

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(min=10, max=60))
    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        response = await self.client.embeddings.create(
            model=settings.openai_embedding_model,
            input=texts,
        )
        return [item.embedding for item in sorted(response.data, key=lambda x: x.index)]

    async def embed_query(self, query: str) -> list[float]:
        result = await self._embed_batch([query])
        return result[0]

'''"""
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

    
    
    # @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    # async def _describe_image(self, chunk: IndexableChunk) -> str:
    #     """Use existing caption instead of calling GPT-4o Vision (free tier)."""
    #     return chunk.content or f"Image from {chunk.metadata.get('source_file', 'document')}"
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def _describe_image(self, chunk: IndexableChunk) -> str:
        """Call GPT-4o Vision to generate a searchable description of an image."""
        response = await self.openai_client.chat.completions.create(
            model=settings.openai_vision_model,
            max_tokens=400,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{chunk.image_b64}",
                                "detail": "high",
                            },
                        },
                        {"type": "text", "text": IMAGE_CAPTION_PROMPT},
                    ],
                }
            ],
        )
        return response.choices[0].message.content.strip()

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
    
'''