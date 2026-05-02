from __future__ import annotations

from pathlib import Path

import pytest

from event_driven_audio_analytics.dataset_exporter.config import DatasetExporterSettings
from event_driven_audio_analytics.shared.settings import load_storage_backend_settings


def test_load_storage_backend_settings_accepts_prompt_aliases(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MINIO_ENDPOINT", "http://minio-alias:9000")
    monkeypatch.setenv("ARTIFACT_BUCKET", "audio-artifacts")

    settings = load_storage_backend_settings(artifacts_root=tmp_path)

    assert settings.endpoint_url == "http://minio-alias:9000"
    assert settings.bucket == "audio-artifacts"


def test_load_storage_backend_settings_rejects_conflicting_alias_values(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MINIO_ENDPOINT_URL", "http://minio-canonical:9000")
    monkeypatch.setenv("MINIO_ENDPOINT", "http://minio-alias:9000")

    with pytest.raises(ValueError, match="Conflicting storage environment variables"):
        load_storage_backend_settings(artifacts_root=tmp_path)


def test_dataset_exporter_settings_reads_storage_aliases(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("ARTIFACTS_ROOT", tmp_path.as_posix())
    monkeypatch.setenv("DATASET_EXPORT_ROOT", (tmp_path / "datasets").as_posix())
    monkeypatch.setenv("MINIO_ENDPOINT", "http://minio-alias:9000")
    monkeypatch.setenv("ARTIFACT_BUCKET", "audio-artifacts")

    settings = DatasetExporterSettings.from_env()

    assert settings.artifacts_root == tmp_path
    assert settings.storage.endpoint_url == "http://minio-alias:9000"
    assert settings.storage.bucket == "audio-artifacts"


def test_load_storage_backend_settings_uses_https_default_when_secure_enabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MINIO_SECURE", "true")

    settings = load_storage_backend_settings(artifacts_root=tmp_path)

    assert settings.secure is True
    assert settings.endpoint_url == "https://minio:9000"
