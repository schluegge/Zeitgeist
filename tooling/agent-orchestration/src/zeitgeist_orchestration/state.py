from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict
from uuid import uuid4

WorkflowPhase = Literal[
    "DISCOVER", "AUDIT", "PLAN", "EXECUTE", "VERIFY", "REVIEW", "COMMIT", "DONE"
]
WorkflowStatus = Literal[
    "RUNNING", "DONE", "WAITING", "BLOCKED", "FAILED", "RETRYING", "CANCELLED"
]


class EvidenceRecord(TypedDict):
    kind: str
    detail: str


class WorkflowState(TypedDict, total=False):
    run_id: str
    task_id: str
    case_id: str
    repository: str
    branch: str
    worktree: str
    head_before: str
    head_after: str
    objective: str
    preconditions: dict[str, Any]
    inputs: dict[str, Any]
    phase: WorkflowPhase
    status: WorkflowStatus
    tool_calls: Annotated[list[dict[str, Any]], operator.add]
    artifacts: Annotated[list[dict[str, Any]], operator.add]
    evidence: Annotated[list[EvidenceRecord], operator.add]
    test_results: Annotated[list[dict[str, Any]], operator.add]
    errors: Annotated[list[str], operator.add]
    retry_count: int
    review_findings: Annotated[list[str], operator.add]
    approval_state: str
    completed_effects: Annotated[list[str], operator.add]


REQUIRED_EVIDENCE = frozenset(
    {
        "preconditions_validated",
        "effect_recorded",
        "verification_passed",
        "review_completed",
    }
)


def make_initial_state(*, objective: str, **overrides: Any) -> WorkflowState:
    state: WorkflowState = {
        "run_id": str(uuid4()),
        "task_id": "local-calibration",
        "case_id": "manual",
        "repository": "Zeitgeist",
        "branch": "infra/langgraph-orchestration",
        "worktree": r"C:\ZEITGEIST.worktrees\langgraph-orchestration",
        "head_before": "",
        "head_after": "",
        "objective": objective,
        "preconditions": {},
        "inputs": {},
        "phase": "DISCOVER",
        "status": "RUNNING",
        "tool_calls": [],
        "artifacts": [],
        "evidence": [],
        "test_results": [],
        "errors": [],
        "retry_count": 0,
        "review_findings": [],
        "approval_state": "not_required",
        "completed_effects": [],
    }
    state.update(overrides)
    return state
