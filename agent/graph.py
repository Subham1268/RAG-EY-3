"""
agent/graph.py
───────────────
Assembles the LangGraph state machine for the Agentic RAG pipeline.

Topology:
  START → query_rewriter → retriever → retrieval_grader → reranker
        → context_builder → generator → reflection_grader
        → "retry" (loop back) | "end" → END
"""

from langgraph.graph import END, START, StateGraph

from agent.nodes import (
    AgentState,
    context_builder_node,
    generator_node,
    query_rewriter_node,
    reranker_node,
    reflection_grader_node,
    retrieval_grader_node,
    retriever_node,
    retry_prep_node,
    should_retry,
)


def build_graph() -> StateGraph:
    """Build and compile the LangGraph agentic RAG graph."""

    builder = StateGraph(AgentState)

    # ── Register nodes ────────────────────────────────────────────────────────
    builder.add_node("query_rewriter",    query_rewriter_node)
    builder.add_node("retriever",         retriever_node)
    builder.add_node("retrieval_grader",  retrieval_grader_node)
    builder.add_node("reranker",          reranker_node)
    builder.add_node("context_builder",   context_builder_node)
    builder.add_node("generator",         generator_node)
    builder.add_node("reflection_grader", reflection_grader_node)
    builder.add_node("retry_prep",        retry_prep_node)

    # ── Edges ─────────────────────────────────────────────────────────────────
    builder.add_edge(START,               "query_rewriter")
    builder.add_edge("query_rewriter",    "retriever")
    builder.add_edge("retriever",         "retrieval_grader")
    builder.add_edge("retrieval_grader",  "reranker")
    builder.add_edge("reranker",          "context_builder")
    builder.add_edge("context_builder",   "generator")
    builder.add_edge("generator",         "reflection_grader")

    # ── Conditional edge: retry or end ────────────────────────────────────────
    builder.add_conditional_edges(
        "reflection_grader",
        should_retry,
        {
            "retry": "retry_prep",
            "end":   END,
        },
    )
    builder.add_edge("retry_prep", "query_rewriter")   # Loop back

    return builder.compile()


# Module-level singleton for import convenience
_compiled_graph = None


def get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph
