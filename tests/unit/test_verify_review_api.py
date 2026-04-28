from __future__ import annotations

import pytest

from event_driven_audio_analytics.smoke import verify_review_api as module


def _build_payload(*, run_ids: list[str]) -> dict[str, dict[str, object]]:
    return {
        "/healthz": {"status": "ok"},
        "/api/runs?demo_mode=true&limit=10": {
            "items": [{"run_id": run_id} for run_id in run_ids],
            "mode": {"pinned_run_ids": list(module.EXPECTED_RUN_IDS)},
        },
        "/api/runs/demo-high-energy": {
            "run": {"segments_persisted": 4},
        },
        "/api/runs/demo-high-energy/tracks?limit=10": {
            "total": 1,
        },
        "/api/runs/demo-high-energy/tracks/910001?segments_limit=10": {
            "segments": {
                "total": 4,
                "items": [
                    {"segment_idx": 0, "silent_flag": False},
                    {"segment_idx": 1, "silent_flag": False},
                    {"segment_idx": 2, "silent_flag": False},
                    {"segment_idx": 3, "silent_flag": False},
                ],
            },
        },
        "/api/runs/demo-silent-oriented/tracks/910002?segments_limit=10": {
            "track": {"track_state": {"value": "persisted"}},
            "segments": {
                "total": 4,
                "items": [
                    {"segment_idx": 0, "silent_flag": False},
                    {"segment_idx": 1, "silent_flag": True},
                    {"segment_idx": 2, "silent_flag": False},
                    {"segment_idx": 3, "silent_flag": False},
                ],
            },
        },
        "/api/runs/demo-validation-failure/tracks/910003?segments_limit=10": {
            "track": {
                "track_state": {"value": "metadata_only"},
                "validation_status": "silent",
            },
            "segments": {"total": 0, "items": []},
        },
    }


def test_verify_review_api_accepts_expected_demo_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _build_payload(run_ids=list(module.EXPECTED_RUN_IDS))
    streamed_urls: list[tuple[str, str]] = []

    def fake_read_json(url: str) -> dict[str, object]:
        return payload[url.removeprefix("http://localhost:8080")]

    def fake_verify_wav_stream(url: str, *, label: str) -> None:
        streamed_urls.append((url, label))

    monkeypatch.setattr(module, "_read_json", fake_read_json)
    monkeypatch.setattr(module, "_verify_wav_stream", fake_verify_wav_stream)

    result = module.verify_review_api(base_url="http://localhost:8080")

    assert result["expected_run_ids"] == module.EXPECTED_RUN_IDS
    assert [label for _, label in streamed_urls] == [
        "High-energy segment artifact",
        "Silent-oriented segment artifact",
    ]


def test_verify_review_api_rejects_out_of_order_demo_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _build_payload(
        run_ids=[
            "demo-silent-oriented",
            "demo-high-energy",
            "demo-validation-failure",
        ]
    )

    def fake_read_json(url: str) -> dict[str, object]:
        return payload[url.removeprefix("http://localhost:8080")]

    monkeypatch.setattr(module, "_read_json", fake_read_json)
    monkeypatch.setattr(module, "_verify_wav_stream", lambda *args, **kwargs: None)

    with pytest.raises(RuntimeError, match="pinned demo ordering"):
        module.verify_review_api(base_url="http://localhost:8080")
