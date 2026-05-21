"""
teams/bot.py
─────────────
Microsoft Teams Bot Framework activity handler.

Handles:
  - message:   User sends a question in Teams → calls RAG API → returns adaptive card
  - conversationUpdate: Welcome message on first join
  - invoke:    Adaptive card button actions (e.g. "See more sources")

The bot does NOT call the RAG agent directly — it calls the FastAPI /chat endpoint
so the Teams layer is fully decoupled from agent logic.

Deployment:
  Register in Azure Bot Service + Teams Toolkit.
  MICROSOFT_APP_ID and MICROSOFT_APP_PASSWORD in .env.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid

import httpx
from botbuilder.core import ActivityHandler, TurnContext
from botbuilder.schema import Activity, ActivityTypes

from teams.cards import build_answer_card, build_welcome_card

AGENT_API_URL = os.getenv("AGENT_API_URL", "http://localhost:8000")
AGENT_API_KEY = os.getenv("AGENT_API_KEY", "")   # Internal service-to-service key


class EYKnowledgeBot(ActivityHandler):
    """
    Teams Bot that acts as a conversational front-end for the Agentic RAG system.
    """

    def __init__(self) -> None:
        super().__init__()
        self._http = httpx.AsyncClient(base_url=AGENT_API_URL, timeout=60.0)

    # ── Incoming message ──────────────────────────────────────────────────────

    async def on_message_activity(self, turn_context: TurnContext) -> None:
        user_text  = turn_context.activity.text or ""
        session_id = self._get_session_id(turn_context)

        # Show typing indicator
        await turn_context.send_activity(Activity(type=ActivityTypes.typing))

        # Call RAG API
        try:
            response = await self._http.post(
                "/chat",
                json={"question": user_text, "session_id": session_id},
                headers={"X-Internal-Key": AGENT_API_KEY},
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            await turn_context.send_activity(
                f"⚠️ I encountered an error retrieving information. "
                f"Please try again. ({exc})"
            )
            return

        # Build adaptive card response
        card = build_answer_card(
            answer=data["answer"],
            citations=data.get("citations", []),
            latency_ms=data.get("latency_ms", 0),
            chunks=data.get("chunks_retrieved", 0),
        )
        await turn_context.send_activity(Activity(
            type=ActivityTypes.message,
            attachments=[card],
        ))

    # ── Conversation update (welcome) ─────────────────────────────────────────

    async def on_members_added_activity(self, members_added, turn_context: TurnContext):
        for member in members_added:
            if member.id != turn_context.activity.recipient.id:
                await turn_context.send_activity(Activity(
                    type=ActivityTypes.message,
                    attachments=[build_welcome_card()],
                ))

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _get_session_id(turn_context: TurnContext) -> str:
        """Derive a stable session ID from the Teams conversation ID."""
        conv_id = turn_context.activity.conversation.id or ""
        user_id = turn_context.activity.from_property.id or ""
        return f"{conv_id}|{user_id}"
