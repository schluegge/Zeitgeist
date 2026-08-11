from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GuardResult:
    allowed: bool
    reason: str


def validate_git_effect(*, remote: str, expected_head: str, actual_head: str) -> GuardResult:
    if remote in {"glass", "zed"}:
        return GuardResult(False, "protected upstream remote")
    if remote != "origin":
        return GuardResult(False, "unowned remote")
    if expected_head != actual_head:
        return GuardResult(False, "stale HEAD")
    return GuardResult(True, "preconditions satisfied")
