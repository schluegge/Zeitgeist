from __future__ import annotations

from typing import TypedDict

from .routing import route_tool


class ToolCallRecord(TypedDict):
    tool: str
    selected_tool: str
    input: str
    outcome: str


def invoke_routing_probe(question: str) -> ToolCallRecord:
    return {
        "tool": "routing_probe",
        "selected_tool": route_tool(question),
        "input": question,
        "outcome": "routed",
    }
