import pytest

from zeitgeist_orchestration.recovery import classify_failure


@pytest.mark.parametrize(
    ("failure", "retry_count", "expected"),
    [
        ("command_failure", 0, "RETRYING"),
        ("stale_graph", 0, "RETRYING"),
        ("changed_head", 0, "BLOCKED"),
        ("test_failure", 0, "FAILED"),
        ("missing_documentation", 0, "BLOCKED"),
        ("tool_timeout", 0, "RETRYING"),
        ("tool_timeout", 2, "FAILED"),
    ],
)
def test_failure_classification(failure: str, retry_count: int, expected: str) -> None:
    decision = classify_failure(failure, retry_count=retry_count, max_retries=2)
    assert decision.status == expected
