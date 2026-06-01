import argparse, asyncio, sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from ingestion.parser import DocumentParser
from ingestion.chunker import DocumentChunker
from ingestion.embedder import Embedder
from ingestion.indexer import DocumentIndexer
from ingestion.metadata_extractor import extract_metadata_from_document
from config.settings import get_settings

settings = get_settings()
parser = DocumentParser()

async def ingest_file(file_path: Path, indexer: DocumentIndexer):
    # 1. Parse document
    parsed = parser.parse(file_path)
    # 2. Extract first ~3000 chars for metadata
    first_text = ""
    for chunk in parsed.text_chunks:
        first_text += chunk.text[:500]
        if len(first_text) > 3000:
            break
    metadata = await extract_metadata_from_document(first_text, file_path)
    print(f"Metadata for {file_path.name}: {metadata}")

    # 3. Chunk + embed + index
    chunker = DocumentChunker(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        project_metadata=metadata
    )
    chunks = chunker.chunk_document(parsed)
    embedder = Embedder()
    embedded = await embedder.embed_chunks(chunks)
    await indexer.index_chunks(embedded)
    return len(chunks)

async def main():
    data_dir = Path("data")
    if not data_dir.exists():
        print("Create a 'data' folder and place documents there.")
        return
    files = list(data_dir.glob("*.pdf")) + list(data_dir.glob("*.pptx")) + list(data_dir.glob("*.docx")) + list(data_dir.glob("*.xlsx"))
    if not files:
        print("No supported files found in ./data")
        return

    indexer = DocumentIndexer()
    await indexer.init_db()
    total = 0
    for f in files:
        n = await ingest_file(f, indexer)
        total += n
        print(f"Ingested {f.name} -> {n} chunks")
    print(f"Done. Total chunks: {total}")

if __name__ == "__main__":
    asyncio.run(main())