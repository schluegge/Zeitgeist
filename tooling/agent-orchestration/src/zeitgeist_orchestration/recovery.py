from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RecoveryStatus = Literal["RETRYING", "BLOCKED", "FAILED"]


@dataclass(frozen=True)
class RecoveryDecision:
    status: RecoveryStatus
    reason: str


def classify_failure(failure: str, *, retry_count: int, max_retries: int) -> RecoveryDecision:
    if failure == "changed_head":
        return RecoveryDecision("BLOCKED", "repository HEAD changed")
    if failure == "missing_documentation":
        return RecoveryDecision("BLOCKED", "required documentation unavailable")
    if failure == "test_failure":
        return RecoveryDecision("FAILED", "verification test failed")
    if failure in {"command_failure", "stale_graph", "tool_timeout"}:
        if retry_count < max_retries:
            return RecoveryDecision("RETRYING", f"recoverable failure: {failure}")
        return RecoveryDecision("FAILED", f"retry budget exhausted: {failure}")
    return RecoveryDecision("FAILED", f"unclassified failure: {failure}")
