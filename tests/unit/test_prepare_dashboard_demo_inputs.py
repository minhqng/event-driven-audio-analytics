from __future__ import annotations

import csv
from pathlib import Path
import wave

from event_driven_audio_analytics.smoke.prepare_dashboard_demo_inputs import (
    HIGH_ENERGY_TRACK,
    SAMPLE_RATE_HZ,
    SILENT_ORIENTED_TRACK,
    VALIDATION_FAILURE_TRACK,
    prepare_dashboard_demo_inputs,
)


def _track_path(audio_root: Path, track_id: int) -> Path:
    track_id_str = f"{track_id:06d}"
    return audio_root / track_id_str[:3] / f"{track_id_str}.mp3"


def test_prepare_dashboard_demo_inputs_creates_expected_metadata_and_audio(tmp_path: Path) -> None:
    paths = prepare_dashboard_demo_inputs(tmp_path)

    metadata_csv = Path(paths["metadata_csv"])
    audio_root = Path(paths["audio_root"])

    assert metadata_csv.exists()
    assert audio_root.exists()

    with metadata_csv.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))

    assert rows[:3] == [
        ["", "artist", "set", "track", "track"],
        ["", "id", "subset", "genre_top", "duration"],
        ["track_id", "", "", "", ""],
    ]
    assert rows[3:] == [
        ["910001", "9101", "small", "Synthetic-High-Energy", "6.00"],
        ["910002", "9102", "small", "Synthetic-Silent-Oriented", "6.00"],
        ["910003", "9103", "small", "Synthetic-Validation-Failure", "3.00"],
    ]

    for track in (HIGH_ENERGY_TRACK, SILENT_ORIENTED_TRACK, VALIDATION_FAILURE_TRACK):
        track_path = _track_path(audio_root, track.track_id)
        assert track_path.exists()
        with wave.open(str(track_path), "rb") as handle:
            assert handle.getnchannels() == 1
            assert handle.getsampwidth() == 2
            assert handle.getframerate() == SAMPLE_RATE_HZ
            assert handle.getnframes() == int(round(track.duration_s * SAMPLE_RATE_HZ))

    assert _track_path(audio_root, SILENT_ORIENTED_TRACK.track_id).stat().st_size > _track_path(
        audio_root,
        VALIDATION_FAILURE_TRACK.track_id,
    ).stat().st_size
