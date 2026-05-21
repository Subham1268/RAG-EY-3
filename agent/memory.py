"""
agent/memory.py
────────────────
Session-level conversation memory for the Agentic RAG agent.

Design:
  • In-memory store (dict of session_id → history) for development.
  • In production, swap the backend to Redis or PostgreSQL for persistence
    across restarts and horizontal scaling.
  • Implements a sliding window of the last N turns to manage context length.
  • Thread-safe via asyncio.Lock per session.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Literal

Role = Literal["user", "assistant", "system"]

MAX_HISTORY_TURNS = 10   # Keep last 10 user+assistant pairs = 20 messages


@dataclass
class Message:
    role:    Role
    content: str


class SessionMemory:
    """
    Per-session conversation buffer with windowed history.

    Usage:
        memory = SessionMemory()
        await memory.add("session-123", "user", "What AML frameworks...")
        await memory.add("session-123", "assistant", "EY Middle East has...")
        history = await memory.get_history("session-123")
    """

    def __init__(self, max_turns: int = MAX_HISTORY_TURNS) -> None:
        self._store:  dict[str, list[Message]] = defaultdict(list)
        self._locks:  dict[str, asyncio.Lock]  = defaultdict(asyncio.Lock)
        self.max_turns = max_turns

    async def add(self, session_id: str, role: Role, content: str) -> None:
        async with self._locks[session_id]:
            self._store[session_id].append(Message(role=role, content=content))
            # Trim to window (keep last max_turns * 2 messages)
            max_msgs = self.max_turns * 2
            if len(self._store[session_id]) > max_msgs:
                self._store[session_id] = self._store[session_id][-max_msgs:]

    async def get_history(self, session_id: str) -> list[dict]:
        """Returns history as list of {"role": ..., "content": ...} dicts."""
        async with self._locks[session_id]:
            return [
                {"role": m.role, "content": m.content}
                for m in self._store[session_id]
            ]

    async def clear(self, session_id: str) -> None:
        async with self._locks[session_id]:
            self._store[session_id] = []

    async def get_summary_context(self, session_id: str) -> str:
        """Returns a compact string representation of recent history."""
        history = await self.get_history(session_id)
        if not history:
            return ""
        lines = [f"{m['role'].upper()}: {m['content'][:200]}" for m in history[-6:]]
        return "\n".join(lines)


# ── Global singleton ──────────────────────────────────────────────────────────
_session_memory: SessionMemory | None = None


def get_memory() -> SessionMemory:
    global _session_memory
    if _session_memory is None:
        _session_memory = SessionMemory()
    return _session_memory
