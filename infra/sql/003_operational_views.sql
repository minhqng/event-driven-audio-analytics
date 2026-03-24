CREATE OR REPLACE VIEW vw_run_feature_summary AS
SELECT
    run_id,
    COUNT(*) AS segments_persisted,
    AVG(rms) AS avg_rms,
    AVG(processing_ms) AS avg_processing_ms,
    SUM(CASE WHEN silent_flag THEN 1 ELSE 0 END) AS silent_segments
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
