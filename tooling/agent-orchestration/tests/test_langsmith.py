from zeitgeist_orchestration.evals import load_cases, run_langsmith_offline


def test_langsmith_offline_runs_without_tracing_or_api_key(monkeypatch) -> None:
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)

    result = run_langsmith_offline(load_cases()[:2])

    assert result == {
        "total_cases": 2,
        "passed_cases": 2,
        "upload_results": False,
    }
