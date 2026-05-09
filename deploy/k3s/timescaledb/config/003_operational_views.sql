CREATE OR REPLACE VIEW vw_run_feature_summary AS
SELECT
    run_id,
    COUNT(*) AS segments_persisted,
    AVG(rms) AS avg_rms,
    AVG(processing_ms) AS avg_processing_ms,
    SUM(CASE WHEN silent_flag THEN 1 ELSE 0 END) AS silent_segments,
    AVG(CASE WHEN silent_flag THEN 1.0 ELSE 0.0 END) AS silent_ratio
FROM audio_features
GROUP BY run_id;

CREATE OR REPLACE VIEW vw_latest_run_checkpoints AS
SELECT
    consumer_group,
    topic_name,
    partition_id,
    run_id,
    last_committed_offset,
    updated_at
FROM run_checkpoints;

CREATE OR REPLACE VIEW vw_latest_system_metrics AS
SELECT
    run_id,
    service_name,
    metric_name,
    MAX(ts) AS latest_ts
FROM system_metrics
GROUP BY run_id, service_name, metric_name;

CREATE OR REPLACE VIEW vw_dashboard_metric_events AS
SELECT
    ts,
    run_id,
    service_name,
    metric_name,
    metric_value,
    COALESCE(labels_json ->> 'scope', 'event') AS metric_scope,
    COALESCE(
        labels_json ->> 'status',
        CASE
            WHEN metric_name IN ('feature_errors', 'write_failures') THEN 'error'
            ELSE 'ok'
        END
    ) AS metric_status,
    labels_json ->> 'topic' AS topic_name,
    labels_json ->> 'failure_class' AS failure_class,
    CASE
        WHEN jsonb_typeof(labels_json -> 'partition') = 'number'
            THEN (labels_json ->> 'partition')::INTEGER
        ELSE NULL
    END AS kafka_partition,
    CASE
        WHEN jsonb_typeof(labels_json -> 'offset') = 'number'
            THEN (labels_json ->> 'offset')::BIGINT
        ELSE NULL
    END AS kafka_offset,
    unit,
    labels_json
FROM system_metrics;

CREATE OR REPLACE VIEW vw_dashboard_run_total_metrics AS
SELECT DISTINCT ON (run_id, service_name, metric_name)
    ts,
    run_id,
    service_name,
    metric_name,
    metric_value,
    unit
FROM vw_dashboard_metric_events
WHERE metric_scope = 'run_total'
ORDER BY run_id, service_name, metric_name, ts DESC;

CREATE OR REPLACE VIEW vw_dashboard_run_validation AS
SELECT
    run_id,
    validation_status,
    COUNT(*) AS track_count
FROM track_metadata
GROUP BY run_id, validation_status;

CREATE OR REPLACE VIEW vw_dashboard_run_summary AS
WITH run_ids AS (
    SELECT run_id FROM track_metadata
    UNION
    SELECT run_id FROM audio_features
    UNION
    SELECT run_id FROM system_metrics
),
activity_window AS (
    SELECT
        run_id,
        MIN(observed_at) AS first_seen_at,
        MAX(observed_at) AS last_seen_at
    FROM (
        SELECT run_id, created_at AS observed_at FROM track_metadata
        UNION ALL
        SELECT run_id, ts AS observed_at FROM audio_features
        UNION ALL
        SELECT run_id, ts AS observed_at FROM system_metrics
    ) AS run_activity
    GROUP BY run_id
),
run_totals AS (
    SELECT
        run_id,
        MAX(CASE WHEN service_name = 'ingestion' AND metric_name = 'tracks_total' THEN metric_value END)
            AS tracks_total,
        MAX(CASE WHEN service_name = 'ingestion' AND metric_name = 'segments_total' THEN metric_value END)
            AS segments_total,
        MAX(CASE WHEN service_name = 'ingestion' AND metric_name = 'validation_failures' THEN metric_value END)
            AS validation_failures,
        MAX(CASE WHEN service_name = 'ingestion' AND metric_name = 'artifact_write_ms' THEN metric_value END)
            AS artifact_write_ms,
        MAX(CASE WHEN service_name = 'processing' AND metric_name = 'silent_ratio' THEN metric_value END)
            AS reported_silent_ratio
    FROM vw_dashboard_run_total_metrics
    GROUP BY run_id
),
feature_summary AS (
    SELECT
        run_id,
        COUNT(*) AS segments_persisted,
        AVG(rms) AS avg_rms,
        AVG(processing_ms) AS avg_processing_ms,
        AVG(CASE WHEN silent_flag THEN 1.0 ELSE 0.0 END) AS observed_silent_ratio
    FROM audio_features
    GROUP BY run_id
),
error_summary AS (
    SELECT
        run_id,
        COUNT(*) FILTER (
            WHERE service_name = 'processing'
              AND metric_name = 'feature_errors'
        ) AS processing_error_count,
        COUNT(*) FILTER (
            WHERE service_name = 'writer'
              AND metric_name = 'write_failures'
        ) AS writer_error_count
    FROM system_metrics
    GROUP BY run_id
)
SELECT
    run_ids.run_id,
    activity_window.first_seen_at,
    activity_window.last_seen_at,
    COALESCE(run_totals.tracks_total, 0.0) AS tracks_total,
    COALESCE(run_totals.segments_total, 0.0) AS segments_total,
    COALESCE(run_totals.validation_failures, 0.0) AS validation_failures,
    COALESCE(run_totals.artifact_write_ms, 0.0) AS artifact_write_ms,
    COALESCE(feature_summary.segments_persisted, 0) AS segments_persisted,
    feature_summary.avg_rms,
    feature_summary.avg_processing_ms,
    COALESCE(run_totals.reported_silent_ratio, feature_summary.observed_silent_ratio, 0.0)
        AS silent_ratio,
    COALESCE(error_summary.processing_error_count, 0) AS processing_error_count,
    COALESCE(error_summary.writer_error_count, 0) AS writer_error_count,
    (
        COALESCE(run_totals.validation_failures, 0.0)
        + COALESCE(error_summary.processing_error_count, 0)
        + COALESCE(error_summary.writer_error_count, 0)
    ) AS total_error_events,
    CASE
        WHEN COALESCE(run_totals.tracks_total, 0.0) > 0
        THEN COALESCE(run_totals.validation_failures, 0.0) / COALESCE(run_totals.tracks_total, 0.0)
        ELSE 0.0
    END AS error_rate
FROM run_ids
LEFT JOIN activity_window
    ON activity_window.run_id = run_ids.run_id
LEFT JOIN run_totals
    ON run_totals.run_id = run_ids.run_id
LEFT JOIN feature_summary
    ON feature_summary.run_id = run_ids.run_id
LEFT JOIN error_summary
    ON error_summary.run_id = run_ids.run_id;
