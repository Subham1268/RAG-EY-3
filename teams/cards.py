"""
teams/cards.py
───────────────
Adaptive Card templates for Teams responses.

Adaptive Cards render rich interactive content in Teams.
Docs: https://adaptivecards.io/designer/

Cards:
  build_answer_card   – Main RAG response card with citations
  build_welcome_card  – Onboarding card shown on first interaction
"""

from __future__ import annotations

from botbuilder.schema import Attachment


def build_answer_card(
    answer: str,
    citations: list[dict],
    latency_ms: int = 0,
    chunks: int = 0,
) -> Attachment:
    """
    Build an adaptive card displaying the RAG answer with source citations.
    """
    # Build citation facts
    citation_rows = []
    for c in citations[:5]:   # Show max 5 citations
        doc_name = c.get("source_file", "").split("/")[-1]
        page     = c.get("page", "")
        label    = c.get("page_label", "Page")
        section  = c.get("section", "")
        citation_rows.append({
            "type": "FactSet",
            "facts": [
                {"title": "📄 Source", "value": doc_name},
                {"title": f"📍 {label}", "value": str(page)},
                *([{"title": "§ Section", "value": section}] if section else []),
            ],
        })

    # Separator before citations
    citation_block = []
    if citation_rows:
        citation_block = [
            {
                "type":   "TextBlock",
                "text":   "**📚 Sources**",
                "wrap":   True,
                "spacing": "Medium",
            },
            *citation_rows,
        ]

    card_body = [
        {
            "type":   "TextBlock",
            "text":   "**EY Middle East Knowledge Assistant**",
            "wrap":   True,
            "size":   "Medium",
            "weight": "Bolder",
            "color":  "Accent",
        },
        {
            "type": "TextBlock",
            "text": answer,
            "wrap": True,
        },
        *citation_block,
        {
            "type":      "TextBlock",
            "text":      f"_Retrieved {chunks} chunks · {latency_ms}ms_",
            "wrap":      True,
            "size":      "Small",
            "color":     "Light",
            "spacing":   "Large",
            "isSubtle":  True,
        },
    ]

    card_json = {
        "type":    "AdaptiveCard",
        "version": "1.5",
        "body":    card_body,
        "actions": [
            {
                "type":  "Action.Submit",
                "title": "🔄 Ask a follow-up",
                "data":  {"action": "followup"},
            },
        ],
    }

    return Attachment(
        content_type="application/vnd.microsoft.card.adaptive",
        content=card_json,
    )


def build_welcome_card() -> Attachment:
    """Welcome card shown when a user first opens the bot."""
    card_json = {
        "type":    "AdaptiveCard",
        "version": "1.5",
        "body": [
            {
                "type":   "TextBlock",
                "text":   "👋 Welcome to **EY Middle East Knowledge Assistant**",
                "wrap":   True,
                "size":   "Large",
                "weight": "Bolder",
                "color":  "Accent",
            },
            {
                "type": "TextBlock",
                "text": (
                    "I can help you discover **historical EY Middle East project work** "
                    "including reports, frameworks, presentations, and methodologies "
                    "across Risk & Compliance, Strategy & Operations, Digital Transformation, "
                    "and more.\n\n"
                    "**Try asking:**"
                ),
                "wrap": True,
            },
            {
                "type": "FactSet",
                "facts": [
                    {"title": "🔍", "value": "What AML frameworks has EY ME implemented in UAE banks?"},
                    {"title": "🔍", "value": "Show me ERM frameworks for development finance institutions in the GCC"},
                    {"title": "🔍", "value": "What cybersecurity maturity assessments have been done for telecom operators?"},
                    {"title": "🔍", "value": "What does EY recommend for boards preparing for an IPO in Saudi Arabia?"},
                ],
            },
        ],
        "actions": [
            {
                "type":  "Action.OpenUrl",
                "title": "📖 View Documentation",
                "url":   "https://teams.microsoft.com/ey-me-rag/docs",
            },
        ],
    }

    return Attachment(
        content_type="application/vnd.microsoft.card.adaptive",
        content=card_json,
    )
