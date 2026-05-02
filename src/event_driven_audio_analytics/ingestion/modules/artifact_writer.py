"""Claim-check artifact writing for ingestion-produced audio segments."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path
import wave

import numpy as np
import polars as pl

from event_driven_audio_analytics.shared.storage import (
    ClaimCheckStore,
    build_claim_check_store,
    run_root,
    storage_settings_for_local,
)

from .segmenter import AudioSegment


MANIFEST_REQUIRED_FIELDS = (
    "run_id",
    "track_id",
    "segment_idx",
    "artifact_uri",
    "checksum",
    "manifest_uri",
    "sample_rate",
    "duration_s",
    "is_last_segment",
)
MANIFEST_OPTIONAL_FIELDS: tuple[str, ...] = ()


@dataclass(slots=True)
class SegmentDescriptor:
    """Claim-check descriptor for one persisted audio segment artifact."""

    run_id: str
    track_id: int
    segment_idx: int
    artifact_uri: str
    checksum: str
    manifest_uri: str
    sample_rate: int
    duration_s: float
    is_last_segment: bool


def ensure_artifact_layout(artifacts_root: Path, run_id: str) -> tuple[Path, Path]:
    """Return segment and manifest directories for a run."""

    run_dir = run_root(artifacts_root, run_id)
    segments_dir = run_dir / "segments"
    manifests_dir = run_dir / "manifests"
    segments_dir.mkdir(parents=True, exist_ok=True)
    manifests_dir.mkdir(parents=True, exist_ok=True)
    return segments_dir, manifests_dir


def _write_wav_mono(path: Path, waveform: np.ndarray, sample_rate: int) -> None:
    """Persist a mono float waveform as a 16-bit PCM WAV artifact."""

    clipped = np.clip(waveform[0], -1.0, 1.0)
    pcm = np.round(clipped * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())


def _encode_wav_mono(waveform: np.ndarray, sample_rate: int) -> bytes:
    """Encode a mono float waveform as 16-bit PCM WAV bytes."""

    buffer = BytesIO()
    clipped = np.clip(waveform[0], -1.0, 1.0)
    pcm = np.round(clipped * 32767.0).astype("<i2")
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())
    return buffer.getvalue()


def _manifest_frame(entries: list[SegmentDescriptor]) -> pl.DataFrame:
    """Convert written segment descriptors into a Parquet-friendly frame."""

    return pl.DataFrame([asdict(entry) for entry in entries])


def read_manifest_frame(manifest_path: Path) -> pl.DataFrame:
    """Load the run manifest and enforce the current required columns."""

    if not manifest_path.exists():
        raise FileNotFoundError(f"Segment manifest does not exist: {manifest_path.as_posix()}")

    frame = pl.read_parquet(manifest_path)
    missing_fields = sorted(set(MANIFEST_REQUIRED_FIELDS) - set(frame.columns))
    if missing_fields:
        raise ValueError(
            "Segment manifest is missing required fields: "
            f"{', '.join(missing_fields)}."
        )
    return frame


def _read_manifest_frame_from_store(store: ClaimCheckStore, manifest_uri: str) -> pl.DataFrame:
    frame = store.read_parquet(manifest_uri)
    missing_fields = sorted(set(MANIFEST_REQUIRED_FIELDS) - set(frame.columns))
    if missing_fields:
        raise ValueError(
            "Segment manifest is missing required fields: "
            f"{', '.join(missing_fields)}."
        )
    return frame


def verify_manifest_consistency(
    descriptors: list[SegmentDescriptor],
    *,
    artifacts_root: Path | None = None,
    store: ClaimCheckStore | None = None,
) -> None:
    """Verify artifact, checksum, and manifest linkage before events are published."""

    if not descriptors:
        return
    if store is None:
        if artifacts_root is None:
            raise ValueError("artifacts_root or store is required for manifest verification.")
        store = build_claim_check_store(storage_settings_for_local(artifacts_root))

    manifest_uris = {descriptor.manifest_uri for descriptor in descriptors}
    if len(manifest_uris) != 1:
        raise ValueError("Segment descriptors must share exactly one manifest_uri.")

    manifest_frame = _read_manifest_frame_from_store(store, next(iter(manifest_uris)))

    for descriptor in descriptors:
        if not store.exists(descriptor.artifact_uri):
            raise FileNotFoundError(
                f"Segment artifact does not exist: {descriptor.artifact_uri}"
            )

        actual_checksum = store.checksum(descriptor.artifact_uri)
        if actual_checksum != descriptor.checksum:
            raise ValueError(
                "Segment artifact checksum does not match its descriptor "
                f"for track_id={descriptor.track_id} segment_idx={descriptor.segment_idx}."
            )

        matches = manifest_frame.filter(
            (pl.col("run_id") == descriptor.run_id)
            & (pl.col("track_id") == descriptor.track_id)
            & (pl.col("segment_idx") == descriptor.segment_idx)
        )
        if matches.height != 1:
            raise ValueError(
                "Segment manifest must contain exactly one row per logical segment "
                f"for track_id={descriptor.track_id} segment_idx={descriptor.segment_idx}."
            )

        manifest_row = matches.to_dicts()[0]
        expected_row = asdict(descriptor)
        for field_name in MANIFEST_REQUIRED_FIELDS:
            if manifest_row[field_name] != expected_row[field_name]:
                raise ValueError(
                    "Segment manifest row does not match the written descriptor "
                    f"for field={field_name} track_id={descriptor.track_id} "
                    f"segment_idx={descriptor.segment_idx}."
                )


def write_segment_artifacts(
    artifacts_root: Path,
    segments: list[AudioSegment],
    *,
    store: ClaimCheckStore | None = None,
) -> list[SegmentDescriptor]:
    """Write WAV artifacts, compute checksums, and update the run manifest."""

    if not segments:
        return []
    if store is None:
        store = build_claim_check_store(storage_settings_for_local(artifacts_root))

    run_id = segments[0].run_id
    manifest_uri_str = store.manifest_uri(run_id)
    if store.settings.normalized_backend() == "local":
        ensure_artifact_layout(artifacts_root, run_id)

    descriptors: list[SegmentDescriptor] = []
    for segment in segments:
        artifact_uri_str = store.segment_uri(
            segment.run_id,
            segment.track_id,
            segment.segment_idx,
        )
        wav_payload = _encode_wav_mono(segment.waveform, segment.sample_rate)
        checksum = store.write_bytes(
            artifact_uri_str,
            wav_payload,
            content_type="audio/wav",
        )
        descriptors.append(
            SegmentDescriptor(
                run_id=segment.run_id,
                track_id=segment.track_id,
                segment_idx=segment.segment_idx,
                artifact_uri=artifact_uri_str,
                checksum=checksum,
                manifest_uri=manifest_uri_str,
                sample_rate=segment.sample_rate,
                duration_s=segment.duration_s,
                is_last_segment=segment.is_last_segment,
            )
        )

    current_frame = _manifest_frame(descriptors)
    if store.exists(manifest_uri_str):
        existing_frame = store.read_parquet(manifest_uri_str)
        current_frame = (
            pl.concat([existing_frame, current_frame], how="vertical_relaxed")
            .unique(subset=["run_id", "track_id", "segment_idx"], keep="last")
            .sort(["run_id", "track_id", "segment_idx"])
        )

    store.write_parquet(manifest_uri_str, current_frame)
    verify_manifest_consistency(descriptors, artifacts_root=artifacts_root, store=store)
    return descriptors
