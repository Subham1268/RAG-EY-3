"""
scripts/ingest.py
──────────────────
Batch ingestion pipeline — runs TWO parallel pipelines per document:

  Pipeline A (existing): Parse → Chunk → [Deduplicate] → Embed (OpenAI) → Index (Pinecone text/image + Postgres chunks)
  Pipeline B (ColPali):  Render pages → Embed (ColPali) → Index (Pinecone colpali + Postgres colpali_pages)

Pipeline A gives fine-grained chunk retrieval + granular citations.
Pipeline B gives superior page-level retrieval for visually rich content.

At query time both indexes are searched and results merged.

DEDUPLICATION:
  Before calling embed_chunks, we query Postgres for which chunk_ids already
  exist. Only genuinely new chunks are embedded and indexed — re-ingesting the
  same document is safe and cheap.

  Note: chunk_id is a hash of (source_file, kind, page, index) — NOT content.
  So if a document's content changes but the filename stays the same, those
  chunks will NOT be re-embedded. Delete the document from the DB first if you
  need a full re-ingest of modified content.

Usage:
    # Inside the Docker container (recommended — see README):
    docker compose exec ingest python scripts/ingest.py

    # Or with the manifest + path flags:
    docker compose exec ingest python scripts/ingest.py \
        --manifest scripts/ey_documents_manifest.json \
        --path /data
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from ingestion.parser import DocumentParser
from ingestion.chunker import DocumentChunker
from ingestion.embedder import Embedder
from ingestion.indexer import DocumentIndexer
from ingestion.metadata_extractor import extract_metadata_from_document
from config.settings import get_settings

settings = get_settings()

# ColPali — optional, degrades gracefully if byaldi not installed
try:
    from ingestion.colpali_embedder import ColPaliEmbedder
    from ingestion.colpali_indexer import ColPaliIndexer
    COLPALI_ENABLED = settings.colpali_enabled
    if not COLPALI_ENABLED:
        print("ℹ️  ColPali disabled by configuration.")
except ImportError:
    COLPALI_ENABLED = False
    print("⚠️  ColPali not available. Running chunk pipeline only.")

parser   = DocumentParser()


# ── Deduplication helper ──────────────────────────────────────────────────────

async def filter_new_chunks(
    chunks: list,
    indexer: DocumentIndexer,
) -> tuple[list, int]:
    """
    Query Postgres for chunk_ids that already exist, then return only the
    chunks whose IDs are NOT in the database yet.

    Returns:
        (new_chunks, skipped_count)
    """
    if not chunks:
        return [], 0

    candidate_ids = [c.chunk_id for c in chunks]

    # Single query — fetch all existing IDs from this candidate set
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    # Build a parameterised IN clause
    placeholders = ", ".join(f":id_{i}" for i in range(len(candidate_ids)))
    params       = {f"id_{i}": cid for i, cid in enumerate(candidate_ids)}

    async with AsyncSession(indexer.engine) as session:
        result = await session.execute(
            text(f"SELECT chunk_id FROM chunks WHERE chunk_id IN ({placeholders})"),
            params,
        )
        existing_ids = {row[0] for row in result.fetchall()}

    new_chunks = [c for c in chunks if c.chunk_id not in existing_ids]
    skipped    = len(chunks) - len(new_chunks)
    return new_chunks, skipped


# ── Pipeline A: chunk ingestion ───────────────────────────────────────────────

async def ingest_file_chunks(
    file_path: Path,
    metadata: dict,
    indexer: DocumentIndexer,
) -> dict:
    """
    Parse → Chunk → Deduplicate → Embed → Index.
    Returns {"indexed": n, "skipped": n}.
    """
    parsed = parser.parse(file_path)

    chunker = DocumentChunker(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        project_metadata=metadata,
    )
    all_chunks = chunker.chunk_document(parsed)

    # ── Deduplication ─────────────────────────────────────────────────────────
    new_chunks, skipped = await filter_new_chunks(all_chunks, indexer)

    if not new_chunks:
        return {"indexed": 0, "skipped": skipped}

    embedder = Embedder()
    embedded = await embedder.embed_chunks(new_chunks)
    await indexer.index_chunks(embedded)

    return {"indexed": len(new_chunks), "skipped": skipped}


# ── Pipeline B: ColPali ingestion ─────────────────────────────────────────────

def ingest_file_colpali(
    file_path: Path,
    metadata: dict,
    colpali_embedder: "ColPaliEmbedder",
    colpali_indexer: "ColPaliIndexer",
) -> list:
    """
    ColPali page-level ingestion (sync — model is not async).
    Returns page_vectors list for async indexing.
    """
    pages        = colpali_embedder.extract_pages(file_path, metadata)
    page_vectors = colpali_embedder.embed_pages(pages)
    return page_vectors


# ── Per-file orchestration ────────────────────────────────────────────────────

async def ingest_file(
    file_path: Path,
    indexer: DocumentIndexer,
    colpali_embedder: "ColPaliEmbedder | None",
    colpali_indexer: "ColPaliIndexer | None",
) -> dict:
    """
    Ingest a single document through both pipelines.
    Returns summary dict with chunk and page counts.
    """
    print(f"\n📄 Ingesting: {file_path.name}")

    # ── Step 1: Extract metadata ──────────────────────────────────────────────
    try:
        parsed_preview = parser.parse(file_path)
        first_text = ""
        for tc in parsed_preview.text_chunks:
            first_text += tc.text[:500]
            if len(first_text) > 3000:
                break
        metadata = await extract_metadata_from_document(first_text, file_path)
        print(f"   Metadata: {metadata}")
    except Exception as e:
        print(f"   ⚠️  Metadata extraction failed: {e}. Using defaults.")
        metadata = {
            "engagement_id": "ME-AUTO-2024-001",
            "client":        "Unknown",
            "country":       "GCC",
            "practice":      "General",
            "year":          2024,
        }

    results = {"file": file_path.name, "chunks": 0, "skipped": 0, "pages": 0, "errors": []}

    # ── Pipeline A: Chunk ingestion (with dedup) ──────────────────────────────
    try:
        chunk_result = await ingest_file_chunks(file_path, metadata, indexer)
        results["chunks"]  = chunk_result["indexed"]
        results["skipped"] = chunk_result["skipped"]
        if chunk_result["skipped"]:
            print(f"   ✅ Chunk pipeline: {chunk_result['indexed']} new chunks indexed "
                  f"({chunk_result['skipped']} duplicates skipped)")
        else:
            print(f"   ✅ Chunk pipeline: {chunk_result['indexed']} chunks indexed")
    except Exception as e:
        results["errors"].append(f"Chunk pipeline: {e}")
        print(f"   ❌ Chunk pipeline failed: {e}")

    # ── Pipeline B: ColPali ingestion ─────────────────────────────────────────
    if COLPALI_ENABLED and colpali_embedder and colpali_indexer:
        try:
            loop = asyncio.get_event_loop()
            page_vectors = await loop.run_in_executor(
                None,
                ingest_file_colpali,
                file_path, metadata, colpali_embedder, colpali_indexer,
            )
            colpali_indexer._upsert_pinecone(page_vectors)
            await colpali_indexer._upsert_postgres(page_vectors)
            results["pages"] = len(page_vectors)
            print(f"   ✅ ColPali pipeline: {len(page_vectors)} pages indexed")
        except Exception as e:
            results["errors"].append(f"ColPali pipeline: {e}")
            print(f"   ❌ ColPali pipeline failed: {e}")
    else:
        print("   ⏭️  ColPali pipeline skipped (not enabled)")

    return results


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    ap = argparse.ArgumentParser(description="EY RAG ingestion pipeline")
    ap.add_argument("--path",     default="data",   help="Folder containing documents")
    ap.add_argument("--manifest", default=None,     help="Optional JSON manifest file")
    args = ap.parse_args()

    data_dir = Path(args.path)
    if not data_dir.exists():
        print(f"❌ Directory not found: {data_dir}")
        return

    supported = {".pdf", ".pptx", ".docx", ".xlsx"}
    files = [f for f in data_dir.iterdir() if f.suffix.lower() in supported]

    # If a manifest is provided, restrict to files listed there
    if args.manifest:
        import json
        manifest_path = Path(args.manifest)
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text())
            manifest_names = {Path(entry["file_path"]).name for entry in manifest}
            files = [f for f in files if f.name in manifest_names]
            print(f"📋 Manifest loaded — restricting to {len(files)} file(s)")
        else:
            print(f"⚠️  Manifest not found: {manifest_path}. Processing all files.")

    if not files:
        print(f"❌ No supported files found in {data_dir}")
        return

    print(f"📚 Found {len(files)} document(s) to ingest")
    print(f"   ColPali enabled: {COLPALI_ENABLED}")

    # ── Initialise indexers ───────────────────────────────────────────────────
    indexer = DocumentIndexer()
    await indexer.init_db()

    colpali_embedder = None
    colpali_indexer  = None

    if COLPALI_ENABLED:
        try:
            colpali_embedder = ColPaliEmbedder()
            colpali_indexer  = ColPaliIndexer()
            await colpali_indexer.init_db()
            print("✅ ColPali indexer ready")
        except Exception as e:
            print(f"⚠️  ColPali init failed: {e}. Chunk pipeline only.")
            colpali_embedder = None
            colpali_indexer  = None

    # ── Ingest each file ──────────────────────────────────────────────────────
    all_results = []
    for f in files:
        result = await ingest_file(f, indexer, colpali_embedder, colpali_indexer)
        all_results.append(result)

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 55)
    print("INGESTION SUMMARY")
    print("=" * 55)
    total_chunks  = sum(r["chunks"]  for r in all_results)
    total_skipped = sum(r["skipped"] for r in all_results)
    total_pages   = sum(r["pages"]   for r in all_results)

    for r in all_results:
        status = "✅" if not r["errors"] else "⚠️"
        print(f"  {status} {r['file']}: "
              f"{r['chunks']} new chunks, "
              f"{r['skipped']} skipped, "
              f"{r['pages']} ColPali pages")
        for err in r["errors"]:
            print(f"      ❌ {err}")

    print(f"\n  Total: {total_chunks} new chunks indexed  |  "
          f"{total_skipped} duplicates skipped  |  "
          f"{total_pages} ColPali pages")
    print("=" * 55)


if __name__ == "__main__":
    asyncio.run(main())