from __future__ import annotations

from pathlib import Path

from event_driven_audio_analytics.review.config import ReviewSettings
from event_driven_audio_analytics.review.runtime import (
    REQUIRED_REVIEW_RELATIONS,
    check_runtime_dependencies,
)
from event_driven_audio_analytics.shared.settings import BaseServiceSettings, DatabaseSettings
from event_driven_audio_analytics.shared.storage import StorageBackendSettings


class FakeCursor:
    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def execute(self, sql: str, params: object = None) -> None:
        return None

    def fetchall(self) -> list[tuple[str]]:
        return [(relation,) for relation in REQUIRED_REVIEW_RELATIONS]


class FakeConnection:
    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def cursor(self) -> FakeCursor:
        return FakeCursor()


class FakeMinioStore:
    def __init__(self) -> None:
        self.check_bucket_called = False
        self.ensure_bucket_called = False

    def check_bucket(self) -> None:
        self.check_bucket_called = True

    def ensure_bucket(self) -> None:
        self.ensure_bucket_called = True


def _settings(tmp_path: Path) -> ReviewSettings:
    return ReviewSettings(
        base=BaseServiceSettings(
            service_name="review",
            run_id="demo-run",
            kafka_bootstrap_servers="kafka:29092",
            artifacts_root=tmp_path,
            storage=StorageBackendSettings(
                backend="minio",
                artifacts_root=tmp_path,
                bucket="fma-small-artifacts",
                create_bucket=True,
            ),
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
        pinned_run_ids=(),
    )


def test_review_minio_readiness_checks_bucket_without_creating_it(
    monkeypatch,
    tmp_path: Path,
) -> None:
    fake_store = FakeMinioStore()
    monkeypatch.setattr(
        "event_driven_audio_analytics.review.runtime.open_database_connection",
        lambda _: FakeConnection(),
    )
    monkeypatch.setattr(
        "event_driven_audio_analytics.review.runtime.build_claim_check_store",
        lambda _: fake_store,
    )

    check_runtime_dependencies(_settings(tmp_path))

    assert fake_store.check_bucket_called is True
    assert fake_store.ensure_bucket_called is False
