from __future__ import annotations

import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCENARIOS_DOC = (
    PROJECT_ROOT / "docs" / "runbooks" / "final-release-validation-scenarios.md"
)


def test_final_release_scenario_scan_is_complete_and_prioritized() -> None:
    doc = SCENARIOS_DOC.read_text(encoding="utf-8")

    scenario_ids = re.findall(r"^\| (S\d{2}) \|", doc, flags=re.MULTILINE)
    assert scenario_ids == [f"S{index:02d}" for index in range(1, 36)]

    priorities = re.findall(r"^\| S\d{2} \| (P[012]) \|", doc, flags=re.MULTILINE)
    assert priorities.count("P0") == 15
    assert priorities.count("P1") == 15
    assert priorities.count("P2") == 5


def test_final_release_scenario_scan_covers_release_risk_areas() -> None:
    doc = SCENARIOS_DOC.read_text(encoding="utf-8")

    required_phrases = [
        "FMA-Small bundle is complete",
        "accepted tracks and accepted segments",
        "artifact URI and storage backend mismatch",
        "MinIO credential failure",
        "restart/replay idempotency",
        "review console and dataset output consistency",
        "evaluation latency metrics",
        "K3s base manifests",
        "operator run-id mistakes",
        "Grafana remains corroboration only",
    ]

    for phrase in required_phrases:
        assert phrase in doc

    assert "Do not add new datasets" in doc
    assert "not benchmark-scale" in doc


def test_final_release_scenario_scan_is_linked_from_reader_paths() -> None:
    docs_index = (PROJECT_ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    validation = (
        PROJECT_ROOT / "docs" / "runbooks" / "validation.md"
    ).read_text(encoding="utf-8")
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    relative_path = "docs/runbooks/final-release-validation-scenarios.md"
    assert relative_path in docs_index
    assert relative_path in validation
    assert relative_path in readme
