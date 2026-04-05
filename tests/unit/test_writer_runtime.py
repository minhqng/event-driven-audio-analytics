from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from event_driven_audio_analytics.shared.db import close_database_pool, open_database_pool
from event_driven_audio_analytics.shared.settings import DatabaseSettings
from event_driven_audio_analytics.writer.config import WriterSettings
from event_driven_audio_analytics.writer.modules.runtime import (
    WriterReadinessError,
    check_runtime_dependencies,
)


def _database_settings() -> DatabaseSettings:
    return DatabaseSettings(
        host="timescaledb",
        port=5432,
        database="audio_analytics",
        user="audio_analytics",
        password="audio_analytics",
    )


def test_writer_settings_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ARTIFACTS_ROOT", tmp_path.as_posix())
    monkeypatch.setenv("WRITER_CONSUMER_GROUP", "writer-group")
    monkeypatch.setenv("WRITER_AUTO_OFFSET_RESET", "latest")
    monkeypatch.setenv("WRITER_POLL_TIMEOUT_S", "2.5")
    monkeypatch.setenv("WRITER_SESSION_TIMEOUT_MS", "60000")
    monkeypatch.setenv("WRITER_MAX_POLL_INTERVAL_MS", "400000")
    monkeypatch.setenv("WRITER_CONSUMER_RETRY_BACKOFF_MS", "333")
    monkeypatch.setenv("WRITER_CONSUMER_RETRY_BACKOFF_MAX_MS", "7777")
    monkeypatch.setenv("WRITER_DB_POOL_MIN_SIZE", "2")
    monkeypatch.setenv("WRITER_DB_POOL_MAX_SIZE", "5")
    monkeypatch.setenv("WRITER_DB_POOL_TIMEOUT_S", "12.5")

    settings = WriterSettings.from_env()

    assert settings.consumer_group == "writer-group"
    assert settings.auto_offset_reset == "latest"
    assert settings.poll_timeout_s == 2.5
    assert settings.session_timeout_ms == 60000
    assert settings.max_poll_interval_ms == 400000
    assert settings.consumer_retry_backoff_ms == 333
    assert settings.consumer_retry_backoff_max_ms == 7777
    assert settings.db_pool_min_size == 2
    assert settings.db_pool_max_size == 5
    assert settings.db_pool_timeout_s == 12.5


def test_open_database_pool_uses_requested_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakePool:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        def wait(self, timeout: float) -> None:
            captured["wait_timeout"] = timeout

        def close(self) -> None:
            captured["closed"] = True

    monkeypatch.setitem(
        sys.modules,
        "psycopg_pool",
        SimpleNamespace(ConnectionPool=FakePool),
    )

    pool = open_database_pool(
        _database_settings(),
        min_size=2,
        max_size=5,
        timeout_s=12.5,
    )
    close_database_pool(pool)

    assert captured["min_size"] == 2
    assert captured["max_size"] == 5
    assert captured["timeout"] == 12.5
    assert captured["kwargs"] == {"autocommit": False}
    assert captured["wait_timeout"] == 12.5
    assert captured["closed"] is True


def test_check_runtime_dependencies_fails_on_missing_topics(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = WriterSettings.from_env()
    monkeypatch.setattr(
        "event_driven_audio_analytics.writer.modules.runtime._list_kafka_topics",
        lambda _: {"audio.metadata"},
    )
    monkeypatch.setattr(
        "event_driven_audio_analytics.writer.modules.runtime._list_database_tables",
        lambda _: {"track_metadata", "audio_features", "system_metrics", "run_checkpoints"},
    )

    with pytest.raises(WriterReadinessError, match="missing required writer topics"):
        check_runtime_dependencies(settings)


def test_check_runtime_dependencies_fails_on_missing_tables(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = WriterSettings.from_env()
    monkeypatch.setattr(
        "event_driven_audio_analytics.writer.modules.runtime._list_kafka_topics",
        lambda _: {"audio.metadata", "audio.features", "system.metrics"},
    )
    monkeypatch.setattr(
        "event_driven_audio_analytics.writer.modules.runtime._list_database_tables",
        lambda _: {"track_metadata", "audio_features"},
    )

    with pytest.raises(WriterReadinessError, match="missing required writer tables"):
        check_runtime_dependencies(settings)


def test_check_runtime_dependencies_passes_when_kafka_and_db_are_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = WriterSettings.from_env()
    monkeypatch.setattr(
        "event_driven_audio_analytics.writer.modules.runtime._list_kafka_topics",
        lambda _: {"audio.metadata", "audio.features", "system.metrics"},
    )
    monkeypatch.setattr(
        "event_driven_audio_analytics.writer.modules.runtime._list_database_tables",
        lambda _: {"track_metadata", "audio_features", "system_metrics", "run_checkpoints"},
    )

    check_runtime_dependencies(settings)
