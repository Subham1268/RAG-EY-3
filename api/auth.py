"""
api/auth.py
────────────
Open access — no authentication key required.

The knowledge base is embedded ONCE into the shared Pinecone index + Postgres.
Anyone who can reach this API can query that same indexed data. They never
re-embed anything; only the query text is embedded at request time via OpenAI.

The only credential the whole system needs is the OPENAI_API_KEY (server-side).
"""

from __future__ import annotations


async def get_current_user() -> dict:
    """
    No-op auth dependency kept for route compatibility.
    Always returns a public user — the API is open.
    """
    return {"user": "public", "name": "Public User"}
