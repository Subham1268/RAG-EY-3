"""
scripts/init_db.py
───────────────────
One-time database initialisation: creates PostgreSQL tables and the Pinecone index.

Run before first ingestion:
    python scripts/init_db.py
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion.indexer import DocumentIndexer
import structlog

log = structlog.get_logger()


async def main():
    log.info("Initialising database schema...")
    indexer = DocumentIndexer()
    await indexer.init_db()
    log.info("PostgreSQL tables created successfully.")
    log.info("Pinecone index verified/created.")
    log.info("✅ Database initialisation complete.")


if __name__ == "__main__":
    asyncio.run(main())
