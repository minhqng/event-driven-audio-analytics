"""Metadata loading helpers for the ingestion service."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import polars as pl


@dataclass(slots=True)
class MetadataRecord:
    """Normalized FMA metadata record carried into the ingestion replay path."""

    track_id: int
    artist_id: int
    genre_label: str
    subset: str
    source_path: str
    source_audio_uri: str
    declared_duration_s: float | None = None


def _build_flattened_headers(csv_path: Path) -> list[str]:
    """Flatten the 3-row FMA header into stable dotted column names."""

    with csv_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        row0 = next(reader)
        row1 = next(reader)

    filled_categories: list[str] = []
    current_category = ""
    for raw_category in row0:
        stripped = raw_category.strip()
        if stripped:
            current_category = stripped
        filled_categories.append(current_category)

    headers: list[str] = []
    for index, (raw_category, raw_attribute) in enumerate(zip(filled_categories, row1, strict=True)):
        category = raw_category.strip()
        attribute = raw_attribute.strip()
        if index == 0:
            headers.append("track_id")
        elif category and attribute:
            headers.append(f"{category}.{attribute}")
        elif attribute:
            headers.append(attribute)
        else:
            headers.append(f"_unnamed_{index}")

    return headers


def resolve_audio_path(track_id: int) -> str:
    """Resolve the canonical FMA relative path for one track id."""

    track_id_str = f"{track_id:06d}"
    return f"{track_id_str[:3]}/{track_id_str}.mp3"


def _load_fma_metadata_frame(csv_path: Path) -> pl.DataFrame:
    """Load the raw FMA tracks CSV with flattened headers."""

    flattened_headers = _build_flattened_headers(csv_path)
    frame = pl.read_csv(
        csv_path,
        skip_rows=3,
        has_header=False,
        infer_schema_length=0,
        null_values=[""],
    )
    if len(frame.columns) != len(flattened_headers):
        raise ValueError(
            "FMA tracks.csv column count did not match flattened-header parsing."
        )

    return frame.rename(dict(zip(frame.columns, flattened_headers, strict=True)))


def _select_required_columns(frame: pl.DataFrame, subset: str) -> pl.DataFrame:
    """Select the columns required by the ingestion path."""

    column_by_key: dict[str, str | None] = {
        "track_id": "track_id",
        "artist_id": None,
        "genre_top": None,
        "subset": None,
        "duration": None,
    }

    for column_name in frame.columns:
        lowered = column_name.lower()
        if lowered == "artist.id":
            column_by_key["artist_id"] = column_name
        elif lowered == "set.subset":
            column_by_key["subset"] = column_name
        elif lowered == "track.duration":
            column_by_key["duration"] = column_name
        elif "genre_top" in lowered:
            column_by_key["genre_top"] = column_name

    missing = [key for key, value in column_by_key.items() if value is None]
    if missing:
        missing_names = ", ".join(sorted(missing))
        raise KeyError(f"tracks.csv is missing required FMA columns: {missing_names}.")

    return (
        frame.select(
            [
                pl.col("track_id").cast(pl.Int64).alias("track_id"),
                pl.col(str(column_by_key["artist_id"])).cast(pl.Int64).alias("artist_id"),
                pl.col(str(column_by_key["genre_top"])).str.strip_chars().alias("genre_label"),
                pl.col(str(column_by_key["subset"])).str.strip_chars().alias("subset"),
                pl.col(str(column_by_key["duration"]))
                .cast(pl.Float64, strict=False)
                .alias("declared_duration_s"),
            ]
        )
        .filter(pl.col("subset") == subset)
        .filter(pl.col("genre_label").is_not_null() & (pl.col("genre_label") != ""))
        .sort("track_id")
    )


def load_small_subset_metadata(
    metadata_csv_path: str,
    *,
    audio_root_path: str,
    subset: str = "small",
    track_id_allowlist: tuple[int, ...] = (),
    max_tracks: int | None = None,
) -> list[MetadataRecord]:
    """Load normalized metadata records for the requested FMA subset."""

    if not metadata_csv_path:
        raise ValueError("metadata_csv_path must not be empty")
    if not audio_root_path:
        raise ValueError("audio_root_path must not be empty")

    csv_path = Path(metadata_csv_path)
    frame = _select_required_columns(_load_fma_metadata_frame(csv_path), subset=subset)

    if track_id_allowlist:
        frame = frame.filter(pl.col("track_id").is_in(track_id_allowlist))

    if max_tracks is not None:
        frame = frame.head(max_tracks)

    invalid_duration_frame = frame.filter(
        pl.col("declared_duration_s").is_null() | (pl.col("declared_duration_s") <= 0.0)
    )
    if invalid_duration_frame.height:
        invalid_track_ids = invalid_duration_frame["track_id"].head(5).to_list()
        raise ValueError(
            "tracks.csv must provide positive track.duration values for the selected subset. "
            f"Invalid track_ids include: {invalid_track_ids}."
        )

    audio_root = Path(audio_root_path)
    records: list[MetadataRecord] = []
    for row in frame.iter_rows(named=True):
        track_id = int(row["track_id"])
        source_path = resolve_audio_path(track_id)
        records.append(
            MetadataRecord(
                track_id=track_id,
                artist_id=int(row["artist_id"]),
                genre_label=str(row["genre_label"]),
                subset=str(row["subset"]),
                source_path=source_path,
                source_audio_uri=(audio_root / source_path).as_posix(),
                declared_duration_s=float(row["declared_duration_s"]),
            )
        )

    return records
