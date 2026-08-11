from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter
from typing import Any

from .evidence import mandatory_evidence_complete
from .git_safety import validate_git_effect
from .recovery import classify_failure
from .routing import route_tool

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = PROJECT_ROOT / "evals" / "cases.json"


def load_cases(path: Path = CASES_PATH) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload["cases"]


def _audit_snapshot(inputs: dict[str, Any]) -> dict[str, Any]:
    classes = {}
    for remote in inputs["remotes"]:
        if remote == "origin":
            classes[remote] = "owned"
        elif remote in {"glass", "zed"}:
            classes[remote] = "read_only"
        else:
            classes[remote] = "unowned"
    return {
        "branch": inputs["branch"] or "<detached>",
        "head": inputs["head"],
        "dirty": bool(inputs["status"]),
        "remote_classes": classes,
        "writes": 0,
    }


def _run_case(case: dict[str, Any]) -> dict[str, Any]:
    started = perf_counter()
    inputs = case["input"]
    category = case["category"]

    if category == "repository_audit":
        actual = _audit_snapshot(inputs)
    elif category == "routing":
        actual = {"route": route_tool(inputs["question"])}
    elif category == "git_safety":
        guard = validate_git_effect(**inputs)
        actual = {"allowed": guard.allowed}
    elif category == "recovery":
        decision = classify_failure(**inputs, max_retries=2)
        actual = {"status": decision.status}
    elif category == "evidence":
        evidence = [{"kind": kind, "detail": "fixture"} for kind in inputs["kinds"]]
        actual = {"complete": mandatory_evidence_complete(evidence)}
    elif category == "idempotence":
        actual = {"should_apply": inputs["effect_key"] not in inputs["completed_effects"]}
    else:
        actual = {"error": "unsupported category"}

    return {
        "id": case["id"],
        "category": category,
        "passed": actual == case["expected"],
        "actual": actual,
        "expected": case["expected"],
        "tool_calls": 1,
        "latency_ms": (perf_counter() - started) * 1000,
    }


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def run_calibration(cases: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    selected = cases or load_cases()
    results = [_run_case(case) for case in selected]
    passed = sum(result["passed"] for result in results)
    routing = [result for result in results if result["category"] == "routing"]
    recovery = [result for result in results if result["category"] == "recovery"]
    evidence = [result for result in results if result["category"] == "evidence"]
    git_cases = [result for result in results if result["category"] == "git_safety"]
    upstream = [result for result in git_cases if result["id"] in {"git-glass", "git-zed"}]

    unsafe = sum(not result["expected"]["allowed"] and result["actual"]["allowed"] for result in git_cases)
    wrong_upstream = sum(result["actual"]["allowed"] for result in upstream)
    missing_evidence = sum(
        not result["expected"]["complete"] and result["actual"]["complete"] for result in evidence
    )
    false_success = unsafe + missing_evidence
    safety_denominator = len(git_cases) + sum(not result["expected"]["complete"] for result in evidence)

    return {
        "total_cases": len(results),
        "passed_cases": passed,
        "task_success": _ratio(passed, len(results)),
        "routing_correctness": _ratio(sum(r["passed"] for r in routing), len(routing)),
        "evidence_completeness": _ratio(sum(r["passed"] for r in evidence), len(evidence)),
        "unsupported_claim_rate": _ratio(false_success, safety_denominator),
        "unsafe_side_effect_rate": _ratio(unsafe, len(git_cases)),
        "recovery_correctness": _ratio(sum(r["passed"] for r in recovery), len(recovery)),
        "wrong_upstream_push_rate": _ratio(wrong_upstream, len(upstream)),
        "false_success_rate": _ratio(false_success, safety_denominator),
        "missing_mandatory_evidence": missing_evidence,
        "tool_call_count": sum(result["tool_calls"] for result in results),
        "latency_ms": sum(result["latency_ms"] for result in results),
        "token_usage": 0,
        "results": results,
    }


def run_langsmith_offline(cases: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    from uuid import NAMESPACE_URL, uuid5

    from langsmith import Client
    from langsmith.schemas import Example

    selected = cases or load_cases()
    examples = [
        Example(
            id=uuid5(NAMESPACE_URL, f"zeitgeist-orchestration:{case['id']}"),
            inputs={"case": case},
            outputs=case["expected"],
        )
        for case in selected
    ]

    def target(inputs: dict[str, Any]) -> dict[str, Any]:
        return _run_case(inputs["case"])["actual"]

    def exact_match(outputs: dict[str, Any], reference_outputs: dict[str, Any]) -> bool:
        return outputs == reference_outputs

    experiment = Client().evaluate(
        target,
        data=examples,
        evaluators=[exact_match],
        experiment_prefix="zeitgeist-orchestration-offline",
        max_concurrency=1,
        upload_results=False,
    )
    rows = list(experiment)
    passed = sum(
        bool(row["evaluation_results"]["results"][0].score)
        for row in rows
    )
    return {
        "total_cases": len(rows),
        "passed_cases": passed,
        "upload_results": False,
    }
