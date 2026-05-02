"""Runtime readiness checks for the review service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from event_driven_audio_analytics.shared.db import open_database_connection
from event_driven_audio_analytics.shared.storage import build_claim_check_store

if TYPE_CHECKING:
    from event_driven_audio_analytics.review.config import ReviewSettings


REQUIRED_REVIEW_RELATIONS = (
    "audio_features",
    "run_checkpoints",
    "track_metadata",
    "vw_dashboard_run_summary",
    "vw_dashboard_run_validation",
    "vw_review_tracks",
)


@dataclass(slots=True)
class ReviewReadinessError(RuntimeError):
    """Raised when review runtime dependencies are not ready."""

    reason: str

    def __str__(self) -> str:
        return self.reason


def _list_database_relations(settings: "ReviewSettings") -> set[str]:
    with open_database_connection(settings.database) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT relname
                FROM pg_catalog.pg_class
                WHERE relnamespace = 'public'::regnamespace
                  AND relkind IN ('r', 'v', 'm')
                  AND relname = ANY(%s)
                ORDER BY relname;
                """,
                (list(REQUIRED_REVIEW_RELATIONS),),
            )
            return {str(row[0]) for row in cursor.fetchall()}


def check_runtime_dependencies(settings: "ReviewSettings") -> None:
    if not settings.base.artifacts_root.exists():
        raise ReviewReadinessError(
            "Artifacts root does not exist: "
            f"{settings.base.artifacts_root.as_posix()}."
        )
    if not settings.base.artifacts_root.is_dir():
        raise ReviewReadinessError(
            "Artifacts root is not a directory: "
            f"{settings.base.artifacts_root.as_posix()}."
        )

    if settings.base.storage.normalized_backend() != "local":
        store = build_claim_check_store(settings.base.storage)
        check_bucket = getattr(store, "check_bucket")
        check_bucket()

    visible_relations = _list_database_relations(settings)
    missing_relations = sorted(set(REQUIRED_REVIEW_RELATIONS) - visible_relations)
    if missing_relations:
        raise ReviewReadinessError(
            "TimescaleDB is reachable but missing required review relations: "
            f"{', '.join(missing_relations)}."
        )
