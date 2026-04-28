"""Verify the read-only review API after the demo inputs have run."""

from __future__ import annotations

import argparse
import json
from urllib.error import HTTPError
from urllib.request import urlopen


DEFAULT_BASE_URL = "http://localhost:8080"
EXPECTED_RUN_IDS = [
    "demo-high-energy",
    "demo-silent-oriented",
    "demo-validation-failure",
]


def _read_json(url: str) -> dict[str, object]:
    with urlopen(url) as response:  # noqa: S310 - trusted local demo endpoint
        return json.loads(response.read().decode("utf-8"))


def _verify_wav_stream(url: str, *, label: str) -> None:
    try:
        with urlopen(url) as response:  # noqa: S310 - trusted local demo endpoint
            if response.status != 200:
                raise RuntimeError(f"{label} did not stream successfully.")
            content_type = response.headers.get_content_type()
            if content_type not in {"audio/wav", "audio/x-wav"}:
                raise RuntimeError(
                    f"{label} returned unexpected content-type {content_type!r}."
                )
            if not response.read(16):
                raise RuntimeError(f"{label} returned an empty body.")
    except HTTPError as exc:  # pragma: no cover - defensive path
        raise RuntimeError(f"{label} did not stream successfully.") from exc


def verify_review_api(*, base_url: str) -> dict[str, object]:
    healthz = _read_json(f"{base_url}/healthz")
    runs = _read_json(f"{base_url}/api/runs?demo_mode=true&limit=10")
    run_ids = [str(item["run_id"]) for item in runs["items"]]

    missing_run_ids = [run_id for run_id in EXPECTED_RUN_IDS if run_id not in run_ids]
    if missing_run_ids:
        raise RuntimeError(f"Review API is missing expected demo runs: {missing_run_ids}.")
    if run_ids[: len(EXPECTED_RUN_IDS)] != EXPECTED_RUN_IDS:
        raise RuntimeError(
            "Review API did not preserve the pinned demo ordering: "
            f"expected {EXPECTED_RUN_IDS} but received {run_ids[: len(EXPECTED_RUN_IDS)]}."
        )
    if runs["mode"]["pinned_run_ids"] != EXPECTED_RUN_IDS:
        raise RuntimeError("Review API did not expose the configured pinned demo run IDs.")

    high_energy = _read_json(f"{base_url}/api/runs/demo-high-energy")
    high_energy_tracks = _read_json(f"{base_url}/api/runs/demo-high-energy/tracks?limit=10")
    high_energy_track = _read_json(
        f"{base_url}/api/runs/demo-high-energy/tracks/910001?segments_limit=10"
    )
    silent_oriented_track = _read_json(
        f"{base_url}/api/runs/demo-silent-oriented/tracks/910002?segments_limit=10"
    )
    validation_failure_track = _read_json(
        f"{base_url}/api/runs/demo-validation-failure/tracks/910003?segments_limit=10"
    )

    if high_energy["run"]["segments_persisted"] < 3:
        raise RuntimeError("High-energy review summary is missing persisted segments.")
    if high_energy_tracks["total"] != 1:
        raise RuntimeError("High-energy run should expose exactly one review track.")
    if high_energy_track["segments"]["total"] < 3:
        raise RuntimeError("High-energy track detail should expose persisted segment rows.")
    if any(item["silent_flag"] for item in high_energy_track["segments"]["items"]):
        raise RuntimeError("High-energy track should not expose silent persisted segments.")
    if silent_oriented_track["track"]["track_state"]["value"] != "persisted":
        raise RuntimeError("Silent-oriented track should stay persisted in the review API.")
    if silent_oriented_track["segments"]["total"] < 3:
        raise RuntimeError("Silent-oriented track detail should expose persisted segment rows.")
    if not any(item["silent_flag"] for item in silent_oriented_track["segments"]["items"]):
        raise RuntimeError("Silent-oriented track should expose at least one silent segment.")
    if validation_failure_track["track"]["track_state"]["value"] != "metadata_only":
        raise RuntimeError("Validation-failure track must stay metadata-only in the review API.")
    if validation_failure_track["track"]["validation_status"] != "silent":
        raise RuntimeError("Validation-failure track must preserve validation_status=silent.")
    if validation_failure_track["segments"]["total"] != 0:
        raise RuntimeError("Validation-failure track must not expose persisted segments.")

    high_energy_artifact_url = (
        f"{base_url}/media/runs/demo-high-energy/segments/910001/"
        f"{high_energy_track['segments']['items'][0]['segment_idx']}.wav"
    )
    silent_oriented_artifact_url = (
        f"{base_url}/media/runs/demo-silent-oriented/segments/910002/"
        f"{silent_oriented_track['segments']['items'][0]['segment_idx']}.wav"
    )
    _verify_wav_stream(high_energy_artifact_url, label="High-energy segment artifact")
    _verify_wav_stream(
        silent_oriented_artifact_url,
        label="Silent-oriented segment artifact",
    )

    return {
        "healthz": healthz,
        "runs": runs,
        "expected_run_ids": EXPECTED_RUN_IDS,
        "high_energy": high_energy,
        "high_energy_tracks": high_energy_tracks,
        "high_energy_track_detail": high_energy_track,
        "silent_oriented_track_detail": silent_oriented_track,
        "validation_failure_track_detail": validation_failure_track,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    args = parser.parse_args()
    print(json.dumps(verify_review_api(base_url=args.base_url), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
