"""Topic names used across the PoC."""

AUDIO_METADATA = "audio.metadata"
AUDIO_SEGMENT_READY = "audio.segment.ready"
AUDIO_FEATURES = "audio.features"
SYSTEM_METRICS = "system.metrics"
AUDIO_DLQ = "audio.dlq"

WRITER_INPUT_TOPICS = (
    AUDIO_METADATA,
    AUDIO_FEATURES,
    SYSTEM_METRICS,
)

ALL_TOPICS = (
    AUDIO_METADATA,
    AUDIO_SEGMENT_READY,
    AUDIO_FEATURES,
    SYSTEM_METRICS,
    AUDIO_DLQ,
)
