from __future__ import annotations

from typing import Literal

from langgraph.graph import END, START, StateGraph

from .state import REQUIRED_EVIDENCE, WorkflowState
from .tools import invoke_routing_probe


def _evidence(kind: str, detail: str) -> dict[str, str]:
    return {"kind": kind, "detail": detail}


def discover(_: WorkflowState) -> dict:
    return {
        "phase": "DISCOVER",
        "evidence": [_evidence("preconditions_validated", "workflow preconditions accepted")],
    }


def audit(_: WorkflowState) -> dict:
    return {"phase": "AUDIT"}


def plan(_: WorkflowState) -> dict:
    return {"phase": "PLAN"}


def execute(state: WorkflowState) -> dict:
    if state["inputs"].get("inject_failure") == "command":
        return {
            "phase": "EXECUTE",
            "status": "FAILED",
            "errors": ["injected command failure"],
            "evidence": [_evidence("command_failed", "injected command failure")],
        }
    effect = f"execute:{state['task_id']}"
    if effect in state["completed_effects"]:
        return {
            "phase": "EXECUTE",
            "evidence": [_evidence("effect_skipped", f"already completed: {effect}")],
        }
    result = {
        "phase": "EXECUTE",
        "completed_effects": [effect],
        "evidence": [_evidence("effect_recorded", effect)],
    }
    question = state["inputs"].get("question")
    if question:
        result["tool_calls"] = [invoke_routing_probe(str(question))]
    return result


def _after_execute(state: WorkflowState) -> Literal["verify", "failed"]:
    return "failed" if state["status"] == "FAILED" else "verify"


def failed(_: WorkflowState) -> dict:
    return {"status": "FAILED"}


def verify(state: WorkflowState) -> dict:
    result = {
        "phase": "VERIFY",
        "test_results": [{"name": "minimal-verification", "passed": True}],
    }
    if not state["inputs"].get("suppress_verification_evidence"):
        result["evidence"] = [_evidence("verification_passed", "minimal verification passed")]
    return result


def review(_: WorkflowState) -> dict:
    return {
        "phase": "REVIEW",
        "evidence": [_evidence("review_completed", "review gate completed")],
    }


def commit(state: WorkflowState) -> dict:
    kinds = {item["kind"] for item in state["evidence"]}
    if not REQUIRED_EVIDENCE <= kinds:
        return {"phase": "COMMIT", "status": "BLOCKED", "errors": ["mandatory evidence missing"]}
    return {"phase": "DONE", "status": "DONE"}


builder = StateGraph(WorkflowState)
builder.add_node("discover", discover)
builder.add_node("audit", audit)
builder.add_node("plan", plan)
builder.add_node("execute", execute)
builder.add_node("verify", verify)
builder.add_node("review", review)
builder.add_node("commit", commit)
builder.add_node("failed", failed)

builder.add_edge(START, "discover")
builder.add_edge("discover", "audit")
builder.add_edge("audit", "plan")
builder.add_edge("plan", "execute")
builder.add_conditional_edges("execute", _after_execute)
builder.add_edge("verify", "review")
builder.add_edge("review", "commit")
builder.add_edge("commit", END)
builder.add_edge("failed", END)

graph = builder.compile(name="zeitgeist-development-orchestrator")
