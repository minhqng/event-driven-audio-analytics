from __future__ import annotations

import json
from pathlib import Path

import pytest

from event_driven_audio_analytics.smoke import verify_dataset_demo_outputs as module


def _write_bundle(
    datasets_root: Path,
    *,
    run_id: str,
    quality_verdict: str = "pass",
    manifest_paths: list[str] | None = None,
    payload_run_id: str | None = None,
) -> Path:
    output_dir = datasets_root / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    effective_payload_run_id = payload_run_id or run_id

    csv_payload = "column\n"
    for relative_path in sorted(module.REQUIRED_BUNDLE_FILES):
        path = output_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if relative_path.endswith(".csv"):
            path.write_text(csv_payload, encoding="utf-8")
        elif relative_path.endswith(".parquet"):
            path.write_bytes(b"parquet-placeholder")
        elif relative_path == "dataset-card.md":
            path.write_text(f"# {run_id}\n", encoding="utf-8")
        elif relative_path == "quality-verdict.json":
            path.write_text(
                json.dumps(
                    {"run_id": effective_payload_run_id, "verdict": quality_verdict},
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
        elif relative_path == "dataset-build-manifest.json":
            listed_paths = (
                sorted(module.MANIFEST_LISTED_FILES)
                if manifest_paths is None
                else list(manifest_paths)
            )
            path.write_text(
                json.dumps(
                    {
                        "run_id": effective_payload_run_id,
                        "files": [
                            {
                                "path": relative_path,
                                "row_count": 0,
                                "sha256": f"sha256:{relative_path}",
                            }
                            for relative_path in listed_paths
                        ],
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
        else:
            path.write_text(
                json.dumps(
                    {"run_id": effective_payload_run_id},
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
    return output_dir


def _write_all_expected_bundles(datasets_root: Path) -> None:
    _write_bundle(datasets_root, run_id="demo-high-energy", quality_verdict="pass")
    _write_bundle(datasets_root, run_id="demo-silent-oriented", quality_verdict="pass_with_warnings")
    _write_bundle(datasets_root, run_id="demo-validation-failure", quality_verdict="fail")


def test_verify_dataset_demo_outputs_accepts_expected_bundles(tmp_path: Path) -> None:
    _write_all_expected_bundles(tmp_path)

    result = module.verify_dataset_demo_outputs(datasets_root=tmp_path)

    assert result["expected_run_ids"] == module.EXPECTED_RUN_IDS
    assert result["runs"]["demo-high-energy"]["quality_verdict"] == "pass"
    assert result["runs"]["demo-silent-oriented"]["quality_verdict"] == "pass_with_warnings"
    assert result["runs"]["demo-validation-failure"]["quality_verdict"] == "fail"


def test_verify_dataset_demo_outputs_rejects_missing_required_file(tmp_path: Path) -> None:
    _write_all_expected_bundles(tmp_path)
    (tmp_path / "demo-silent-oriented" / "accepted-segments.csv").unlink()

    with pytest.raises(RuntimeError, match="Dataset bundle files mismatch"):
        module.verify_dataset_demo_outputs(datasets_root=tmp_path)


def test_verify_dataset_demo_outputs_rejects_manifest_file_list_mismatch(tmp_path: Path) -> None:
    _write_bundle(
        tmp_path,
        run_id="demo-high-energy",
        manifest_paths=sorted(module.MANIFEST_LISTED_FILES - {"label-map.json"}),
    )
    _write_bundle(tmp_path, run_id="demo-silent-oriented")
    _write_bundle(tmp_path, run_id="demo-validation-failure", quality_verdict="fail")

    with pytest.raises(RuntimeError, match="listed unexpected owned files"):
        module.verify_dataset_demo_outputs(datasets_root=tmp_path)


def test_verify_dataset_demo_outputs_rejects_foreign_bundle_run_id(tmp_path: Path) -> None:
    _write_bundle(tmp_path, run_id="demo-high-energy", payload_run_id="demo-other")
    _write_bundle(tmp_path, run_id="demo-silent-oriented")
    _write_bundle(tmp_path, run_id="demo-validation-failure", quality_verdict="fail")

    with pytest.raises(RuntimeError, match="run_id mismatch"):
        module.verify_dataset_demo_outputs(datasets_root=tmp_path)


def test_verify_dataset_demo_outputs_accepts_validation_failure_bundle_structure(tmp_path: Path) -> None:
    _write_all_expected_bundles(tmp_path)

    result = module.verify_dataset_demo_outputs(datasets_root=tmp_path)

    assert result["runs"]["demo-validation-failure"]["quality_verdict"] == "fail"
