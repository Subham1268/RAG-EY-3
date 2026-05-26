"""
scripts/ingest.py
──────────────────
Batch ingestion pipeline for EY Middle East project documents.

Usage:
    # Ingest a single file
    python scripts/ingest.py --file path/to/report.pdf \
        --engagement-id ME-RC-2023-0089 \
        --client "UAE Commercial Bank" \
        --country UAE \
        --practice "Risk & Compliance" \
        --year 2023

    # Ingest an entire directory
    python scripts/ingest.py --path ./documents/ \
        --practice "Risk & Compliance" \
        --year 2023

    # Ingest with a JSON metadata file (one entry per document)
    python scripts/ingest.py --manifest ./documents/manifest.json

Manifest format (manifest.json):
    [
      {
        "file_path": "path/to/doc.pdf",
        "engagement_id": "ME-RC-2023-0089",
        "client": "UAE Bank",
        "country": "UAE",
        "practice": "Risk & Compliance",
        "year": 2023
      },
      ...
    ]
    
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog
from tqdm.asyncio import tqdm

from config.settings import get_settings
from ingestion.chunker import DocumentChunker
from ingestion.embedder import Embedder
from ingestion.indexer import DocumentIndexer
from ingestion.parser import DocumentParser

log      = structlog.get_logger()
settings = get_settings()

SUPPORTED_EXTENSIONS = {".pdf", ".pptx", ".docx", ".xlsx"}


async def ingest_file(
    file_path: Path,
    metadata:  dict,
    parser:    DocumentParser,
    chunker:   DocumentChunker,
    embedder:  Embedder,
    indexer:   DocumentIndexer,
) -> int:
    """Ingest a single document. Returns number of chunks indexed."""
    log.info("ingesting", file=str(file_path))
    try:
        parsed   = parser.parse(file_path)
        chunks   = chunker.chunk_document(parsed)
        if not chunks:
            log.warning("no_chunks", file=str(file_path))
            return 0
        embedded = await embedder.embed_chunks(chunks)
        await indexer.index_chunks(embedded)
        log.info("ingested", file=str(file_path), chunks=len(chunks))
        return len(chunks)
    except Exception as exc:
        log.error("ingest_failed", file=str(file_path), error=str(exc))
        return 0


async def main() -> None:
    parser_arg = argparse.ArgumentParser(description="EY ME Agentic RAG — Document Ingestion")
    parser_arg.add_argument("--file",          type=str, help="Single file to ingest")
    parser_arg.add_argument("--path",          type=str, help="Directory to ingest recursively")
    parser_arg.add_argument("--manifest",      type=str, help="JSON manifest file")
    parser_arg.add_argument("--engagement-id", type=str, default="")
    parser_arg.add_argument("--client",        type=str, default="")
    parser_arg.add_argument("--country",       type=str, default="")
    parser_arg.add_argument("--practice",      type=str, default="")
    parser_arg.add_argument("--year",          type=int, default=0)
    args = parser_arg.parse_args()

    # ── Build job list ────────────────────────────────────────────────────────
    jobs: list[tuple[Path, dict]] = []

    base_meta = {
        "engagement_id": args.engagement_id,
        "client":        args.client,
        "country":       args.country,
        "practice":      args.practice,
        "year":          args.year,
    }

    if args.manifest:
        with open(args.manifest) as f:
            entries = json.load(f)
        for entry in entries:
            fp = Path(entry.pop("file_path"))
            # If --path is provided, prepend it to the filename
            if args.path:
                fp = Path(args.path) / fp
            meta = {**base_meta, **entry}
            jobs.append((fp, meta))

    elif args.file:
        jobs.append((Path(args.file), base_meta))

    elif args.path:
        root = Path(args.path)
        for ext in SUPPORTED_EXTENSIONS:
            for fp in root.rglob(f"*{ext}"):
                jobs.append((fp, base_meta))

    else:
        parser_arg.print_help()
        sys.exit(1)

    log.info("ingestion_start", total_files=len(jobs))

    # ── Initialise pipeline components ────────────────────────────────────────
    doc_parser  = DocumentParser()
    embedder    = Embedder()
    indexer     = DocumentIndexer()
    await indexer.init_db()

    total_chunks = 0
    for file_path, metadata in tqdm(jobs, desc="Ingesting documents"):
        if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            log.warning("unsupported_extension", file=str(file_path))
            continue

        chunker = DocumentChunker(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            project_metadata=metadata,
        )
        n = await ingest_file(file_path, metadata, doc_parser, chunker, embedder, indexer)
        total_chunks += n
        await asyncio.sleep(10)  # wait 10 seconds between files

    log.info("ingestion_complete", total_chunks=total_chunks, total_files=len(jobs))
    print(f"\n✅ Ingested {len(jobs)} documents → {total_chunks} chunks indexed.")


if __name__ == "__main__":
    asyncio.run(main())
