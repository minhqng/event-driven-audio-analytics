"""Verify the Week 7 dashboard demo data after the Compose-backed demo runs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from time import monotonic, sleep

from event_driven_audio_analytics.shared.db import open_database_connection
from event_driven_audio_analytics.shared.settings import load_database_settings


DEFAULT_VERIFY_TIMEOUT_S = 45.0
DEFAULT_VERIFY_POLL_INTERVAL_S = 1.0

HIGH_ENERGY_RUN_ID = "week7-high-energy"
SILENT_ORIENTED_RUN_ID = "week7-silent-oriented"
VALIDATION_FAILURE_RUN_ID = "week7-validation-failure"


@dataclass(frozen=True, slots=True)
class RunSummary:
    run_id: str
    tracks_total: float
    segments_total: float
    validation_failures: float
    artifact_write_ms: float
    segments_persisted: int
    avg_rms: float | None
    avg_processing_ms: float | None
    silent_ratio: float
    processing_error_count: int
    writer_error_count: int
    total_error_events: float
    error_rate: float


@dataclass(frozen=True, slots=True)
class DashboardDemoSummary:
    high_energy: RunSummary
    silent_oriented: RunSummary
    validation_failure: RunSummary
    validation_status_counts: dict[str, dict[str, int]]

    def to_json(self) -> str:
        return json.dumps(
            {
                "high_energy": asdict(self.high_energy),
                "silent_oriented": asdict(self.silent_oriented),
                "validation_failure": asdict(self.validation_failure),
                "validation_status_counts": self.validation_status_counts,
            },
            indent=2,
            sort_keys=True,
        )


def _env_float(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    value = float(raw_value)
    if value <= 0.0:
        raise ValueError(f"{name} must be positive when set.")
    return value


def _query_run_summaries() -> dict[str, RunSummary]:
    database_settings = load_database_settings()
    with open_database_connection(database_settings) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    run_id,
                    tracks_total,
                    segments_total,
                    validation_failures,
                    artifact_write_ms,
                    segments_persisted,
                    avg_rms,
                    avg_processing_ms,
                    silent_ratio,
                    processing_error_count,
                    writer_error_count,
                    total_error_events,
                    error_rate
                FROM vw_dashboard_run_summary
                WHERE run_id = ANY(%s)
                ORDER BY run_id;
                """,
                ([HIGH_ENERGY_RUN_ID, SILENT_ORIENTED_RUN_ID, VALIDATION_FAILURE_RUN_ID],),
            )
            rows = cursor.fetchall()
            return {
                str(row[0]): RunSummary(
                    run_id=str(row[0]),
                    tracks_total=float(row[1]),
                    segments_total=float(row[2]),
                    validation_failures=float(row[3]),
                    artifact_write_ms=float(row[4]),
                    segments_persisted=int(row[5]),
                    avg_rms=float(row[6]) if row[6] is not None else None,
                    avg_processing_ms=float(row[7]) if row[7] is not None else None,
                    silent_ratio=float(row[8]),
                    processing_error_count=int(row[9]),
                    writer_error_count=int(row[10]),
                    total_error_events=float(row[11]),
                    error_rate=float(row[12]),
                )
                for row in rows
            }


def _query_validation_status_counts() -> dict[str, dict[str, int]]:
    database_settings = load_database_settings()
    with open_database_connection(database_settings) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT run_id, validation_status, track_count
                FROM vw_dashboard_run_validation
                WHERE run_id = ANY(%s)
                ORDER BY run_id, validation_status;
                """,
                ([HIGH_ENERGY_RUN_ID, SILENT_ORIENTED_RUN_ID, VALIDATION_FAILURE_RUN_ID],),
            )
            result: dict[str, dict[str, int]] = {}
            for run_id, validation_status, track_count in cursor.fetchall():
                result.setdefault(str(run_id), {})[str(validation_status)] = int(track_count)
            return result


def _assert_dashboard_demo(
    run_summaries: dict[str, RunSummary],
    validation_status_counts: dict[str, dict[str, int]],
) -> DashboardDemoSummary:
    missing_runs = sorted(
        {
            HIGH_ENERGY_RUN_ID,
            SILENT_ORIENTED_RUN_ID,
            VALIDATION_FAILURE_RUN_ID,
        }
        - set(run_summaries)
    )
    if missing_runs:
        raise RuntimeError(f"Week 7 demo is missing expected runs in vw_dashboard_run_summary: {missing_runs}.")

    high_energy = run_summaries[HIGH_ENERGY_RUN_ID]
    silent_oriented = run_summaries[SILENT_ORIENTED_RUN_ID]
    validation_failure = run_summaries[VALIDATION_FAILURE_RUN_ID]

    if high_energy.tracks_total != 1.0 or high_energy.segments_persisted < 3:
        raise RuntimeError(f"{HIGH_ENERGY_RUN_ID} did not persist the expected energetic segments.")
    if high_energy.validation_failures != 0.0 or high_energy.silent_ratio != 0.0:
        raise RuntimeError(f"{HIGH_ENERGY_RUN_ID} should stay validated and non-silent in the dashboard summary.")
    if high_energy.error_rate != 0.0:
        raise RuntimeError(f"{HIGH_ENERGY_RUN_ID} should keep a zero failed-track error_rate.")
    if high_energy.avg_rms is None:
        raise RuntimeError(f"{HIGH_ENERGY_RUN_ID} is missing RMS data in audio_features.")

    if silent_oriented.tracks_total != 1.0 or silent_oriented.segments_persisted < 3:
        raise RuntimeError(f"{SILENT_ORIENTED_RUN_ID} did not persist the expected silent-oriented segments.")
    if silent_oriented.validation_failures != 0.0:
        raise RuntimeError(f"{SILENT_ORIENTED_RUN_ID} should validate successfully before processing.")
    if not (0.0 < silent_oriented.silent_ratio < 1.0):
        raise RuntimeError(f"{SILENT_ORIENTED_RUN_ID} should produce a non-zero silent_ratio.")
    if silent_oriented.error_rate != 0.0:
        raise RuntimeError(f"{SILENT_ORIENTED_RUN_ID} should keep a zero failed-track error_rate.")
    if silent_oriented.avg_rms is None:
        raise RuntimeError(f"{SILENT_ORIENTED_RUN_ID} is missing RMS data in audio_features.")

    if validation_failure.tracks_total != 1.0 or validation_failure.validation_failures != 1.0:
        raise RuntimeError(f"{VALIDATION_FAILURE_RUN_ID} should contain one validation failure.")
    if validation_failure.segments_persisted != 0 or validation_failure.segments_total != 0.0:
        raise RuntimeError(f"{VALIDATION_FAILURE_RUN_ID} must not persist feature rows.")
    if validation_failure.error_rate != 1.0:
        raise RuntimeError(f"{VALIDATION_FAILURE_RUN_ID} should drive a full failed-track error_rate.")

    failure_status_counts = validation_status_counts.get(VALIDATION_FAILURE_RUN_ID, {})
    if failure_status_counts.get("silent", 0) != 1:
        raise RuntimeError(
            f"{VALIDATION_FAILURE_RUN_ID} should appear as validation_status=silent in track_metadata."
        )

    if not (silent_oriented.avg_rms < high_energy.avg_rms):
        raise RuntimeError("The silent-oriented run should have lower average RMS than the energetic baseline.")

    if high_energy.processing_error_count != 0 or high_energy.writer_error_count != 0:
        raise RuntimeError(f"{HIGH_ENERGY_RUN_ID} should stay free of processing/writer errors.")
    if silent_oriented.processing_error_count != 0 or silent_oriented.writer_error_count != 0:
        raise RuntimeError(f"{SILENT_ORIENTED_RUN_ID} should stay free of processing/writer errors.")

    return DashboardDemoSummary(
        high_energy=high_energy,
        silent_oriented=silent_oriented,
        validation_failure=validation_failure,
        validation_status_counts=validation_status_counts,
    )


def verify_dashboard_demo_with_retries(*, timeout_s: float, poll_interval_s: float) -> DashboardDemoSummary:
    deadline = monotonic() + timeout_s
    last_error: RuntimeError | None = None

    while monotonic() <= deadline:
        run_summaries = _query_run_summaries()
        validation_status_counts = _query_validation_status_counts()
        try:
            return _assert_dashboard_demo(run_summaries, validation_status_counts)
        except RuntimeError as exc:
            last_error = exc
            if monotonic() >= deadline:
                raise
            sleep(poll_interval_s)

    if last_error is not None:
        raise last_error
    raise RuntimeError("Dashboard demo verification timed out without producing a summary.")


def main() -> None:
    timeout_s = _env_float("DASHBOARD_DEMO_VERIFY_TIMEOUT_S", DEFAULT_VERIFY_TIMEOUT_S)
    poll_interval_s = _env_float(
        "DASHBOARD_DEMO_VERIFY_POLL_INTERVAL_S",
        DEFAULT_VERIFY_POLL_INTERVAL_S,
    )
    summary = verify_dashboard_demo_with_retries(
        timeout_s=timeout_s,
        poll_interval_s=poll_interval_s,
    )
    print(summary.to_json())


if __name__ == "__main__":
    main()
