from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .state import REQUIRED_EVIDENCE


def mandatory_evidence_complete(evidence: Iterable[Mapping[str, Any]]) -> bool:
    kinds = {str(item.get("kind", "")) for item in evidence}
    return REQUIRED_EVIDENCE <= kinds


def write_evidence_artifact(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    path.write_text(serialized, encoding="utf-8")
