"""
tests/test_agent.py
────────────────────
Unit and integration tests for the Agentic RAG pipeline.

Run with:
    pytest tests/test_agent.py -v
    pytest tests/test_agent.py -v -k "unit"   # fast tests only
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.nodes import (
    AgentState,
    context_builder_node,
    generator_node,
    query_rewriter_node,
    retrieval_grader_node,
    reranker_node,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def base_state(**overrides) -> AgentState:
    state: AgentState = {
        "question":          "What AML frameworks has EY ME implemented in UAE?",
        "chat_history":      [],
        "rewritten_queries": [],
        "raw_chunks":        [],
        "graded_chunks":     [],
        "reranked_chunks":   [],
        "full_chunks":       [],
        "citations":         [],
        "context":           "",
        "answer":            "",
        "final_answer":      "",
        "reflection_loops":  0,
        "reflection_result": {},
    }
    state.update(overrides)
    return state


MOCK_CHUNK = {
    "chunk_id":        "abc123",
    "score":           0.87,
    "namespace":       "text",
    "content_preview": "The AML assessment covered five pillars: Governance, CDD, Transaction Monitoring...",
    "metadata": {
        "source_file":   "02_EY_ME_AML_Framework_Assessment_UAE_Bank.pdf",
        "doc_type":      "pdf",
        "page_or_slide": 1,
        "section_title": "Executive Summary",
        "country":       "UAE",
        "practice":      "Risk & Compliance",
        "engagement_id": "ME-RC-2023-0089",
    },
}

MOCK_FULL_CHUNK = {
    **MOCK_CHUNK,
    "content": (
        "EY Middle East was engaged to assess the AML/CTF framework of a major UAE bank. "
        "Across 47 assessed controls, 12 critical gaps and 18 significant gaps were identified. "
        "The remediation investment is estimated at AED 47-62 million over 18 months."
    ),
    "kind": "text",
}


# ── Unit tests ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.unit
async def test_query_rewriter_generates_queries():
    """Query rewriter should produce multiple diverse queries."""
    mock_response = MagicMock()
    mock_response.content = '["AML framework UAE bank", "anti-money laundering GCC compliance", "CTF assessment Middle East"]'

    with patch("agent.nodes._llm") as mock_llm:
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        state  = base_state()
        result = await query_rewriter_node(state)

    assert "rewritten_queries" in result
    assert len(result["rewritten_queries"]) >= 2
    assert state["question"] in result["rewritten_queries"]


@pytest.mark.asyncio
@pytest.mark.unit
async def test_query_rewriter_falls_back_on_bad_json():
    """Query rewriter should include original question if LLM returns bad JSON."""
    mock_response = MagicMock()
    mock_response.content = "Some non-JSON response from LLM"

    with patch("agent.nodes._llm") as mock_llm:
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        result = await query_rewriter_node(base_state())

    assert base_state()["question"] in result["rewritten_queries"]


@pytest.mark.asyncio
@pytest.mark.unit
async def test_retrieval_grader_filters_irrelevant():
    """Retrieval grader should remove chunks marked as not relevant."""
    irrelevant_chunk = {**MOCK_CHUNK, "chunk_id": "irrelevant_001",
                        "content_preview": "Quarterly earnings report for a fashion brand"}
    chunks = [MOCK_CHUNK, irrelevant_chunk]

    mock_response_relevant   = MagicMock()
    mock_response_relevant.content = '{"relevant": true, "reason": "directly about AML"}'
    mock_response_irrelevant = MagicMock()
    mock_response_irrelevant.content = '{"relevant": false, "reason": "unrelated topic"}'

    call_count = 0

    async def mock_ainvoke(prompt):
        nonlocal call_count
        call_count += 1
        return mock_response_relevant if call_count == 1 else mock_response_irrelevant

    with patch("agent.nodes._llm_json") as mock_llm:
        mock_llm.ainvoke = mock_ainvoke
        result = await retrieval_grader_node(base_state(raw_chunks=chunks))

    assert any(c["chunk_id"] == "abc123" for c in result["graded_chunks"])
    assert all(c["chunk_id"] != "irrelevant_001" for c in result["graded_chunks"])


@pytest.mark.asyncio
@pytest.mark.unit
async def test_context_builder_assembles_context():
    """Context builder should format chunks into a readable context string."""
    with patch("agent.tools.fetch_full_chunk", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = MOCK_FULL_CHUNK
        result = await context_builder_node(
            base_state(reranked_chunks=[MOCK_CHUNK])
        )

    assert "context" in result
    assert "AML" in result["context"]
    assert len(result["citations"]) == 1
    assert result["citations"][0]["source_file"] == MOCK_FULL_CHUNK["source_file"]


@pytest.mark.asyncio
@pytest.mark.unit
async def test_generator_uses_context():
    """Generator should produce a non-empty answer using the provided context."""
    mock_response = MagicMock()
    mock_response.content = (
        "EY Middle East conducted an AML assessment identifying 12 critical gaps. "
        "[Source: 02_EY_ME_AML_Framework_Assessment_UAE_Bank.pdf, Page 1]"
    )

    with patch("agent.nodes._llm") as mock_llm:
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        result = await generator_node(
            base_state(context="AML assessment context here...")
        )

    assert result["answer"]
    assert "AML" in result["answer"]


# ── Integration tests (require real API keys) ─────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.integration
async def test_full_pipeline_aml_query():
    """
    End-to-end test of the full LangGraph pipeline.
    Requires real Pinecone, OpenAI, and Cohere API keys.
    Run with: pytest -m integration
    """
    from agent.graph import build_graph

    graph = build_graph()
    result = await graph.ainvoke(base_state(
        question="What AML gaps did EY identify in the UAE bank assessment?"
    ))

    assert result.get("final_answer") or result.get("answer")
    print("\n=== Integration Test Answer ===")
    print(result.get("final_answer") or result.get("answer"))
    print("=== Citations ===")
    for c in result.get("citations", []):
        print(f"  - {c['source_file']} {c['page_label']} {c['page']}")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_full_pipeline_governance_query():
    """Test governance / IPO readiness query."""
    from agent.graph import build_graph

    graph  = build_graph()
    result = await graph.ainvoke(base_state(
        question="What corporate governance improvements does EY recommend for Saudi companies preparing for IPO?"
    ))
    assert result.get("final_answer") or result.get("answer")
