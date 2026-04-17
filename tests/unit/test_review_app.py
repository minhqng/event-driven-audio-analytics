from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from event_driven_audio_analytics.review.app import create_app
from event_driven_audio_analytics.review.config import ReviewSettings
from event_driven_audio_analytics.shared.settings import BaseServiceSettings, DatabaseSettings


def build_settings(tmp_path: Path) -> ReviewSettings:
    return ReviewSettings(
        base=BaseServiceSettings(
            service_name="review",
            run_id="demo-run",
            kafka_bootstrap_servers="kafka:29092",
            artifacts_root=tmp_path,
        ),
        database=DatabaseSettings(
            host="timescaledb",
            port=5432,
            database="audio_analytics",
            user="audio_analytics",
            password="audio_analytics",
        ),
        host="0.0.0.0",
        port=8080,
        default_limit=8,
        max_limit=25,
        pinned_run_ids=("week7-high-energy",),
    )


def test_api_runs_passes_demo_mode_to_query_layer(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    def fake_list_runs(settings: ReviewSettings, *, limit: int, offset: int, demo_mode: bool) -> dict[str, object]:
        captured["settings"] = settings
        captured["limit"] = limit
        captured["offset"] = offset
        captured["demo_mode"] = demo_mode
        return {
            "items": [],
            "limit": limit,
            "offset": offset,
            "total": 0,
            "has_more": False,
            "mode": {"demo_mode": demo_mode, "pinned_run_ids": [], "provenance": {"source": "derived"}},
        }

    monkeypatch.setattr("event_driven_audio_analytics.review.app.list_runs", fake_list_runs)
    client = TestClient(create_app(build_settings(tmp_path)))

    response = client.get("/api/runs?limit=5&offset=2&demo_mode=true")

    assert response.status_code == 200
    assert captured["limit"] == 5
    assert captured["offset"] == 2
    assert captured["demo_mode"] is True


def test_media_endpoint_streams_existing_segment(
    monkeypatch,
    tmp_path: Path,
) -> None:
    artifact_path = tmp_path / "runs" / "demo-run" / "review-media" / "segment-0.wav"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_bytes(b"RIFF")

    client = TestClient(create_app(build_settings(tmp_path)))
    monkeypatch.setattr(
        "event_driven_audio_analytics.review.app.lookup_segment_artifact_path",
        lambda *args, **kwargs: artifact_path,
    )
    response = client.get("/media/runs/demo-run/segments/2/0.wav")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")


def test_media_endpoint_rejects_run_id_escape(tmp_path: Path) -> None:
    client = TestClient(create_app(build_settings(tmp_path)))
    response = client.get("/media/runs/%2E%2E/segments/2/0.wav")

    assert response.status_code == 404


def test_track_detail_returns_404_when_query_layer_has_no_track(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("event_driven_audio_analytics.review.app.get_track_detail", lambda *args, **kwargs: None)
    client = TestClient(create_app(build_settings(tmp_path)))

    response = client.get("/api/runs/demo-run/tracks/999")

    assert response.status_code == 404


def test_media_endpoint_returns_404_when_artifact_uri_is_unresolvable(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "event_driven_audio_analytics.review.app.lookup_segment_artifact_path",
        lambda *args, **kwargs: None,
    )
    client = TestClient(create_app(build_settings(tmp_path)))

    response = client.get("/media/runs/demo-run/segments/2/0.wav")

    assert response.status_code == 404
