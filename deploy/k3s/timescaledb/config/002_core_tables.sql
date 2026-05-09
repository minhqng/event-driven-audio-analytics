CREATE TABLE IF NOT EXISTS track_metadata (
    run_id TEXT NOT NULL,
    track_id BIGINT NOT NULL,
    artist_id BIGINT NOT NULL,
    genre TEXT NOT NULL,
    subset TEXT NOT NULL DEFAULT 'small',
    source_audio_uri TEXT NOT NULL,
    validation_status TEXT NOT NULL,
    duration_s DOUBLE PRECISION NOT NULL,
    manifest_uri TEXT,
    checksum TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (run_id, track_id)
);

ALTER TABLE IF EXISTS track_metadata ADD COLUMN IF NOT EXISTS duration_s DOUBLE PRECISION;

CREATE TABLE IF NOT EXISTS audio_features (
    ts TIMESTAMPTZ NOT NULL,
    run_id TEXT NOT NULL,
    track_id BIGINT NOT NULL,
    segment_idx INTEGER NOT NULL,
    artifact_uri TEXT NOT NULL,
    checksum TEXT NOT NULL,
    manifest_uri TEXT,
    rms DOUBLE PRECISION NOT NULL,
    silent_flag BOOLEAN NOT NULL,
    mel_bins INTEGER NOT NULL,
    mel_frames INTEGER NOT NULL,
    processing_ms DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Timescale unique constraints must include the partition column.
    PRIMARY KEY (ts, run_id, track_id, segment_idx)
);

ALTER TABLE IF EXISTS audio_features ALTER COLUMN manifest_uri DROP NOT NULL;

SELECT create_hypertable('audio_features', 'ts', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_audio_features_lookup
ON audio_features (run_id, track_id, segment_idx);

CREATE TABLE IF NOT EXISTS system_metrics (
    ts TIMESTAMPTZ NOT NULL,
    run_id TEXT NOT NULL,
    service_name TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value DOUBLE PRECISION NOT NULL,
    labels_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    unit TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE IF EXISTS system_metrics ADD COLUMN IF NOT EXISTS unit TEXT;

SELECT create_hypertable('system_metrics', 'ts', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS run_checkpoints (
    consumer_group TEXT NOT NULL,
    topic_name TEXT NOT NULL,
    partition_id INTEGER NOT NULL,
    run_id TEXT NOT NULL,
    last_committed_offset BIGINT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (consumer_group, topic_name, partition_id)
);

CREATE TABLE IF NOT EXISTS welford_snapshots (
    run_id TEXT NOT NULL,
    service_name TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    count BIGINT NOT NULL,
    mean DOUBLE PRECISION NOT NULL,
    m2 DOUBLE PRECISION NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (run_id, service_name, metric_name)
);
