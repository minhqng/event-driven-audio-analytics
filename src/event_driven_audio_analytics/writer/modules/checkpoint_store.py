"""Checkpoint persistence helpers for resumable writer consumption."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from psycopg import Cursor
else:
    Cursor = Any


RUN_CHECKPOINT_UPSERT = """
INSERT INTO run_checkpoints (
    consumer_group,
    topic_name,
    partition_id,
    run_id,
    last_committed_offset
)
VALUES (
    %(consumer_group)s,
    %(topic_name)s,
    %(partition_id)s,
    %(run_id)s,
    %(last_committed_offset)s
)
ON CONFLICT (consumer_group, topic_name, partition_id) DO UPDATE SET
    run_id = EXCLUDED.run_id,
    last_committed_offset = EXCLUDED.last_committed_offset,
    updated_at = NOW();
""".strip()


def build_checkpoint_record(
    consumer_group: str,
    topic_name: str,
    partition_id: int,
    run_id: str,
    last_committed_offset: int,
) -> dict[str, object]:
    """Create a checkpoint payload for the current consumer position."""

    return {
        "consumer_group": consumer_group,
        "topic_name": topic_name,
        "partition_id": partition_id,
        "run_id": run_id,
        "last_committed_offset": last_committed_offset,
    }


def persist_checkpoint(cursor: Cursor, checkpoint_record: dict[str, object]) -> int:
    """Persist the current consumer checkpoint inside the active transaction."""

    cursor.execute(RUN_CHECKPOINT_UPSERT, checkpoint_record)
    return cursor.rowcount
