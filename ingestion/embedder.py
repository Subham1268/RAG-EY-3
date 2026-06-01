import asyncio
import openai
from dataclasses import dataclass
from tenacity import retry, stop_after_attempt, wait_exponential
from config.settings import get_settings
from ingestion.chunker import IndexableChunk

settings = get_settings()

IMAGE_CAPTION_PROMPT = """You are an EY analyst. Describe this image extracted from a consulting deliverable in 3-5 sentences: type of visual, key insights, numbers/labels, and how it relates to consulting themes (risk, governance, transformation)."""

# ── Add this dataclass ────────────────────────────────────────────────────────
@dataclass
class EmbeddedChunk:
    chunk: IndexableChunk
    embedding: list[float]
    image_description: str | None


class Embedder:
    EMBEDDING_DIM = 1536   # text-embedding-3-large
    EMBED_BATCH = 10

    def __init__(self):
        self.client = openai.AsyncOpenAI(api_key=settings.openai_api_key)

    async def embed_chunks(self, chunks: list[IndexableChunk]):
        # 1. Describe images one by one (respect rate limits)
        descriptions = []
        for c in chunks:
            if c.kind == "image":
                desc = await self._describe_image(c)
                await asyncio.sleep(2)
            else:
                desc = None
            descriptions.append(desc)

        # Patch image content with description
        texts = []
        for chunk, desc in zip(chunks, descriptions):
            if desc:
                chunk.content = desc
            texts.append(chunk.content)

        # 2. Embed in batches
        all_embeddings = await self._batch_embed(texts)
        # Now EmbeddedChunk is defined
        return [EmbeddedChunk(chunk=c, embedding=emb, image_description=desc)
                for c, emb, desc in zip(chunks, all_embeddings, descriptions)]

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(min=10, max=60))
    async def _describe_image(self, chunk: IndexableChunk) -> str:
        response = await self.client.chat.completions.create(
            model=settings.openai_vision_model,
            max_tokens=300,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{chunk.image_b64}", "detail": "low"}},
                    {"type": "text", "text": IMAGE_CAPTION_PROMPT}
                ]
            }]
        )
        return response.choices[0].message.content.strip()

    async def _batch_embed(self, texts: list[str]) -> list[list[float]]:
        all_emb = []
        for i in range(0, len(texts), self.EMBED_BATCH):
            batch = texts[i:i+self.EMBED_BATCH]
            emb = await self._embed_batch(batch)
            all_emb.extend(emb)
            await asyncio.sleep(5)   # avoid rate limit
        return all_emb

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(min=10, max=60))
    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        response = await self.client.embeddings.create(
            model=settings.openai_embedding_model,
            input=texts,
            dimensions=1536   # <── ADD THIS LINE to match Pinecone index dimension
        )
        return [item.embedding for item in sorted(response.data, key=lambda x: x.index)]

    async def embed_query(self, query: str) -> list[float]:
        return (await self._embed_batch([query]))[0]