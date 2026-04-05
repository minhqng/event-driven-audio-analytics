"""System-metrics persistence helpers for the writer service."""

from __future__ import annotations

from dataclasses import asdict
import json
from typing import TYPE_CHECKING, Any

from event_driven_audio_analytics.shared.db import acquire_transaction_advisory_lock
from event_driven_audio_analytics.shared.models.system_metrics import SystemMetricsPayload

if TYPE_CHECKING:
    from psycopg import Cursor
else:
    Cursor = Any


SYSTEM_METRICS_INSERT = """
INSERT INTO system_metrics (
    ts,
    run_id,
    service_name,
    metric_name,
    metric_value,
    labels_json,
    unit
)
VALUES (
    %(ts)s,
    %(run_id)s,
    %(service_name)s,
    %(metric_name)s,
    %(metric_value)s,
    %(labels_json)s,
    %(unit)s
);
""".strip()


SYSTEM_METRICS_RUN_TOTAL_SELECT = """
SELECT
    tableoid::oid,
    ctid::text
FROM system_metrics
WHERE run_id = %(run_id)s
  AND service_name = %(service_name)s
  AND metric_name = %(metric_name)s
  AND labels_json = %(labels_json)s
ORDER BY ts DESC, tableoid::oid DESC, ctid DESC;
""".strip()


SYSTEM_METRICS_RUN_TOTAL_DELETE_DUPLICATES = """
DELETE FROM system_metrics
WHERE run_id = %(run_id)s
  AND service_name = %(service_name)s
  AND metric_name = %(metric_name)s
  AND labels_json = %(labels_json)s
  AND NOT (
      tableoid = %(survivor_tableoid)s::oid
      AND ctid = %(survivor_ctid)s::tid
  );
""".strip()


SYSTEM_METRICS_RUN_TOTAL_DELETE_SURVIVOR = """
DELETE FROM system_metrics
WHERE tableoid = %(survivor_tableoid)s::oid
  AND ctid = %(survivor_ctid)s::tid;
""".strip()


def persist_system_metrics(cursor: Cursor, payload: SystemMetricsPayload) -> int:
    """Persist one operational metric row with replay-safe run_total snapshot handling."""

    try:
        from psycopg.types.json import Jsonb
    except ModuleNotFoundError:
        Jsonb = lambda value: value

    params = asdict(payload)
    params["labels_json"] = Jsonb(payload.labels_json)
    if payload.labels_json.get("scope") != "run_total":
        cursor.execute(SYSTEM_METRICS_INSERT, params)
        return cursor.rowcount

    logical_key = json.dumps(payload.labels_json, separators=(",", ":"), sort_keys=True)
    acquire_transaction_advisory_lock(
        cursor,
        payload.run_id,
        payload.service_name,
        payload.metric_name,
        logical_key,
    )
    cursor.execute(SYSTEM_METRICS_RUN_TOTAL_SELECT, params)
    matches = cursor.fetchall()
    if len(matches) >= 1:
        params["survivor_tableoid"] = matches[0][0]
        params["survivor_ctid"] = matches[0][1]
        if len(matches) > 1:
            cursor.execute(SYSTEM_METRICS_RUN_TOTAL_DELETE_DUPLICATES, params)
        cursor.execute(SYSTEM_METRICS_RUN_TOTAL_DELETE_SURVIVOR, params)
        cursor.execute(SYSTEM_METRICS_INSERT, params)
        return cursor.rowcount

    cursor.execute(SYSTEM_METRICS_INSERT, params)
    return cursor.rowcount
