from __future__ import annotations

from event_driven_audio_analytics.writer.modules.checkpoint_store import RUN_CHECKPOINT_UPSERT


def test_checkpoint_upsert_keeps_run_scoped_evidence() -> None:
    assert "ON CONFLICT (consumer_group, topic_name, partition_id, run_id)" in RUN_CHECKPOINT_UPSERT
    assert "run_id = EXCLUDED.run_id" not in RUN_CHECKPOINT_UPSERT
