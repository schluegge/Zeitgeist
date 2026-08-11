from __future__ import annotations


def route_tool(question: str) -> str:
    text = question.casefold()

    if "gpui" in text and ("documentation" in text or "docs" in text):
        return "grounded_docs"
    if "what calls" in text or "callers" in text:
        return "code_review_graph"
    if "rust symbol" in text and any(term in text for term in ("defined", "definition", "exact type")):
        return "rust_analyzer"
    if ("user-controlled" in text or "taint" in text) and (
        "database" in text or "reach" in text
    ):
        return "code_graph_rag"
    return "blocked_unclassified"
