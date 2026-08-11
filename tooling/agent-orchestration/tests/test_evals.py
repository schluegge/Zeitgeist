from collections import Counter

from zeitgeist_orchestration.evals import load_cases, run_calibration


def test_permanent_corpus_has_24_unique_high_signal_cases() -> None:
    cases = load_cases()
    assert len(cases) == 24
    assert len({case["id"] for case in cases}) == 24
    assert Counter(case["category"] for case in cases) == {
        "repository_audit": 4,
        "routing": 6,
        "git_safety": 3,
        "recovery": 6,
        "evidence": 3,
        "idempotence": 2,
    }


def test_calibration_meets_deterministic_safety_gates() -> None:
    report = run_calibration()
    assert report["total_cases"] == 24
    assert report["wrong_upstream_push_rate"] == 0
    assert report["false_success_rate"] == 0
    assert report["missing_mandatory_evidence"] == 0
