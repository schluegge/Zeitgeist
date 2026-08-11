from zeitgeist_orchestration.graph import graph
from zeitgeist_orchestration.state import make_initial_state


def test_successful_workflow_reaches_done_with_mandatory_evidence() -> None:
    result = graph.invoke(make_initial_state(objective="audit repository"))

    assert result["status"] == "DONE"
    evidence_kinds = {item["kind"] for item in result["evidence"]}
    assert {
        "preconditions_validated",
        "effect_recorded",
        "verification_passed",
        "review_completed",
    } <= evidence_kinds


def test_command_failure_stops_before_verification() -> None:
    state = make_initial_state(
        objective="execute failing command",
        inputs={"inject_failure": "command"},
    )
    result = graph.invoke(state)

    assert result["status"] == "FAILED"
    assert "injected command failure" in result["errors"]
    assert "verification_passed" not in {item["kind"] for item in result["evidence"]}


def test_missing_verification_evidence_blocks_done() -> None:
    state = make_initial_state(
        objective="verify evidence gate",
        inputs={"suppress_verification_evidence": True},
    )
    result = graph.invoke(state)

    assert result["status"] == "BLOCKED"
    assert "mandatory evidence missing" in result["errors"]


def test_graph_records_deterministic_tool_adapter_call() -> None:
    state = make_initial_state(
        objective="route documentation question",
        inputs={"question": "What does the current GPUI documentation say about X?"},
    )
    result = graph.invoke(state)

    assert result["status"] == "DONE"
    assert result["tool_calls"] == [
        {
            "tool": "routing_probe",
            "selected_tool": "grounded_docs",
            "input": "What does the current GPUI documentation say about X?",
            "outcome": "routed",
        }
    ]
