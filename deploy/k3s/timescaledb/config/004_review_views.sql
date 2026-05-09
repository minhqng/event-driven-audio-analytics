CREATE OR REPLACE VIEW vw_review_tracks AS
SELECT
    track_metadata.run_id,
    track_metadata.track_id,
    track_metadata.artist_id,
    track_metadata.genre,
    track_metadata.subset,
    track_metadata.source_audio_uri,
    track_metadata.validation_status,
    track_metadata.duration_s,
    track_metadata.manifest_uri,
    track_metadata.checksum,
    COALESCE(feature_summary.segments_persisted, 0) AS segments_persisted,
    COALESCE(feature_summary.silent_segments, 0) AS silent_segments,
    feature_summary.silent_ratio,
    feature_summary.avg_rms,
    feature_summary.avg_processing_ms,
    CASE
        WHEN COALESCE(feature_summary.segments_persisted, 0) > 0 THEN 'persisted'
        ELSE 'metadata_only'
    END AS track_state
FROM track_metadata
LEFT JOIN LATERAL (
    SELECT
        COUNT(*) AS segments_persisted,
        SUM(CASE WHEN silent_flag THEN 1 ELSE 0 END) AS silent_segments,
        AVG(CASE WHEN silent_flag THEN 1.0 ELSE 0.0 END) AS silent_ratio,
        AVG(rms) AS avg_rms,
        AVG(processing_ms) AS avg_processing_ms
    FROM audio_features
    WHERE audio_features.run_id = track_metadata.run_id
      AND audio_features.track_id = track_metadata.track_id
) AS feature_summary
    ON TRUE;
