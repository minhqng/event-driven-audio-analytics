"""Verify deterministic dataset-export bundles for the final demo runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


DEFAULT_DATASETS_ROOT = Path("/app/artifacts/datasets")
EXPECTED_RUN_IDS = [
    "demo-high-energy",
    "demo-silent-oriented",
    "demo-validation-failure",
]
REQUIRED_BUNDLE_FILES = {
    "dataset-build-manifest.json",
    "run-summary.json",
    "quality-verdict.json",
    "accepted-tracks.csv",
    "rejected-tracks.csv",
    "accepted-segments.csv",
    "rejected-segments.csv",
    "anomaly-summary.json",
    "label-map.json",
    "dataset-card.md",
    "splits/split-manifest.json",
    "splits/train.parquet",
    "splits/validation.parquet",
    "splits/test.parquet",
    "stats/normalization-stats.json",
}
MANIFEST_LISTED_FILES = REQUIRED_BUNDLE_FILES - {"dataset-build-manifest.json"}


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _bundle_file_paths(output_dir: Path) -> set[str]:
    return {
        path.relative_to(output_dir).as_posix()
        for path in output_dir.rglob("*")
        if path.is_file()
    }


def _manifest_paths(manifest_payload: dict[str, object]) -> list[str]:
    files = manifest_payload.get("files")
    if not isinstance(files, list):
        raise RuntimeError("dataset-build-manifest.json must expose a files array.")

    manifest_paths: list[str] = []
    for item in files:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise RuntimeError(
                "dataset-build-manifest.json files entries must be objects with string path values."
            )
        manifest_paths.append(str(item["path"]))
    return manifest_paths


def _assert_payload_run_id(
    *,
    payload: dict[str, object],
    payload_name: str,
    expected_run_id: str,
) -> None:
    actual_run_id = payload.get("run_id")
    if actual_run_id != expected_run_id:
        raise RuntimeError(
            f"{payload_name} run_id mismatch for run_id={expected_run_id}. "
            f"actual={actual_run_id!r}."
        )


def _verify_bundle(*, datasets_root: Path, run_id: str) -> dict[str, object]:
    output_dir = datasets_root / run_id
    if not output_dir.is_dir():
        raise RuntimeError(f"Dataset bundle directory is missing for run_id={run_id}: {output_dir}.")

    actual_files = _bundle_file_paths(output_dir)
    if actual_files != REQUIRED_BUNDLE_FILES:
        missing_files = sorted(REQUIRED_BUNDLE_FILES - actual_files)
        unexpected_files = sorted(actual_files - REQUIRED_BUNDLE_FILES)
        raise RuntimeError(
            f"Dataset bundle files mismatch for run_id={run_id}. "
            f"missing={missing_files} unexpected={unexpected_files}."
        )

    manifest_payload = _read_json(output_dir / "dataset-build-manifest.json")
    _assert_payload_run_id(
        payload=manifest_payload,
        payload_name="dataset-build-manifest.json",
        expected_run_id=run_id,
    )
    manifest_paths = sorted(_manifest_paths(manifest_payload))
    expected_manifest_paths = sorted(MANIFEST_LISTED_FILES)
    if manifest_paths != expected_manifest_paths:
        raise RuntimeError(
            f"dataset-build-manifest.json listed unexpected owned files for run_id={run_id}. "
            f"expected={expected_manifest_paths} actual={manifest_paths}."
        )

    run_summary = _read_json(output_dir / "run-summary.json")
    _assert_payload_run_id(
        payload=run_summary,
        payload_name="run-summary.json",
        expected_run_id=run_id,
    )
    quality_verdict = _read_json(output_dir / "quality-verdict.json")
    _assert_payload_run_id(
        payload=quality_verdict,
        payload_name="quality-verdict.json",
        expected_run_id=run_id,
    )
    verdict = quality_verdict.get("verdict")
    if not isinstance(verdict, str) or verdict == "":
        raise RuntimeError(f"quality-verdict.json is missing a verdict for run_id={run_id}.")

    for payload_name in ("splits/split-manifest.json", "stats/normalization-stats.json"):
        _assert_payload_run_id(
            payload=_read_json(output_dir / payload_name),
            payload_name=payload_name,
            expected_run_id=run_id,
        )

    return {
        "output_dir": output_dir.as_posix(),
        "bundle_files": sorted(actual_files),
        "manifest_listed_files": manifest_paths,
        "quality_verdict": verdict,
    }


def verify_dataset_demo_outputs(*, datasets_root: Path) -> dict[str, object]:
    resolved_root = datasets_root.resolve()
    runs = {
        run_id: _verify_bundle(datasets_root=resolved_root, run_id=run_id)
        for run_id in EXPECTED_RUN_IDS
    }
    return {
        "datasets_root": resolved_root.as_posix(),
        "expected_run_ids": EXPECTED_RUN_IDS,
        "required_bundle_files": sorted(REQUIRED_BUNDLE_FILES),
        "manifest_listed_files": sorted(MANIFEST_LISTED_FILES),
        "runs": runs,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--datasets-root", type=Path, default=DEFAULT_DATASETS_ROOT)
    args = parser.parse_args()
    print(json.dumps(verify_dataset_demo_outputs(datasets_root=args.datasets_root), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
