import json

from zeitgeist_orchestration.evidence import mandatory_evidence_complete, write_evidence_artifact


def test_evidence_artifact_is_written_and_readable(tmp_path) -> None:
    target = tmp_path / "evidence.json"
    payload = {"run_id": "run-1", "status": "DONE"}

    write_evidence_artifact(target, payload)

    assert json.loads(target.read_text(encoding="utf-8")) == payload


def test_mandatory_evidence_requires_all_kinds() -> None:
    evidence = [
        {"kind": "preconditions_validated", "detail": "ok"},
        {"kind": "effect_recorded", "detail": "ok"},
        {"kind": "verification_passed", "detail": "ok"},
        {"kind": "review_completed", "detail": "ok"},
    ]
    assert mandatory_evidence_complete(evidence)
    assert not mandatory_evidence_complete(evidence[:-1])
