from zeitgeist_orchestration.graph import graph
from zeitgeist_orchestration.state import make_initial_state


def test_second_completed_run_does_not_duplicate_effect() -> None:
    first = graph.invoke(make_initial_state(objective="idempotence", task_id="same-task"))
    second = graph.invoke(first)

    assert first["completed_effects"] == ["execute:same-task"]
    assert second["completed_effects"] == ["execute:same-task"]
