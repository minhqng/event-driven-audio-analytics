"""Persistence placeholders for idempotent writer behavior."""

from __future__ import annotations

from dataclasses import dataclass


AUDIO_FEATURES_LOGICAL_KEY = ("run_id", "track_id", "segment_idx")


@dataclass(slots=True)
class PersistenceResult:
    """Summarize placeholder persistence work."""

    rows_written: int
    checkpoints_ready: bool


TRACK_METADATA_UPSERT = """
INSERT INTO track_metadata (
    run_id,
    track_id,
    artist_id,
    genre,
    subset,
    source_audio_uri,
    validation_status,
    manifest_uri,
    checksum
)
VALUES (
    %(run_id)s,
    %(track_id)s,
    %(artist_id)s,
    %(genre)s,
    %(subset)s,
    %(source_audio_uri)s,
    %(validation_status)s,
    %(manifest_uri)s,
    %(checksum)s
)
ON CONFLICT (run_id, track_id) DO UPDATE SET
    artist_id = EXCLUDED.artist_id,
    genre = EXCLUDED.genre,
    subset = EXCLUDED.subset,
    source_audio_uri = EXCLUDED.source_audio_uri,
    validation_status = EXCLUDED.validation_status,
    manifest_uri = EXCLUDED.manifest_uri,
    checksum = EXCLUDED.checksum;
""".strip()


AUDIO_FEATURES_UPSERT = """
INSERT INTO audio_features (
    ts,
    run_id,
    track_id,
    segment_idx,
    artifact_uri,
    checksum,
    manifest_uri,
    rms,
    silent_flag,
    mel_bins,
    mel_frames,
    processing_ms
)
VALUES (
    %(ts)s,
    %(run_id)s,
    %(track_id)s,
    %(segment_idx)s,
    %(artifact_uri)s,
    %(checksum)s,
    %(manifest_uri)s,
    %(rms)s,
    %(silent_flag)s,
    %(mel_bins)s,
    %(mel_frames)s,
    %(processing_ms)s
)
ON CONFLICT (ts, run_id, track_id, segment_idx) DO UPDATE SET
    artifact_uri = EXCLUDED.artifact_uri,
    checksum = EXCLUDED.checksum,
    manifest_uri = EXCLUDED.manifest_uri,
    rms = EXCLUDED.rms,
    silent_flag = EXCLUDED.silent_flag,
    mel_bins = EXCLUDED.mel_bins,
    mel_frames = EXCLUDED.mel_frames,
    processing_ms = EXCLUDED.processing_ms;
""".strip()


SYSTEM_METRICS_INSERT = """
INSERT INTO system_metrics (
    ts,
    run_id,
    service_name,
    metric_name,
    metric_value,
    labels_json
)
VALUES (
    %(ts)s,
    %(run_id)s,
    %(service_name)s,
    %(metric_name)s,
    %(metric_value)s,
    %(labels_json)s
);
""".strip()


def persist_batch(_: list[dict[str, object]]) -> PersistenceResult:
    """Return a placeholder persistence result until database writes are implemented."""

    # TODO: persist metadata/features/metrics to TimescaleDB with idempotent semantics.
    return PersistenceResult(rows_written=0, checkpoints_ready=True)
