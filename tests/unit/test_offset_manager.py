from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from event_driven_audio_analytics.writer.modules.offset_manager import build_commit_decision


class OffsetManagerTests(unittest.TestCase):
    def test_commit_requires_positive_rows_written(self) -> None:
        decision = build_commit_decision(rows_written=0, checkpoints_ready=True)

        self.assertFalse(decision.commit_allowed)
        self.assertEqual(decision.reason, "invalid persistence result")
        self.assertEqual(decision.failure_class, "invalid_persistence_result")

    def test_commit_requires_checkpoint_success(self) -> None:
        decision = build_commit_decision(rows_written=1, checkpoints_ready=False)

        self.assertFalse(decision.commit_allowed)
        self.assertEqual(decision.reason, "checkpoint update not complete")
        self.assertEqual(decision.failure_class, "checkpoint_failed")

    def test_commit_allowed_after_persistence_and_checkpoint(self) -> None:
        decision = build_commit_decision(rows_written=1, checkpoints_ready=True)

        self.assertTrue(decision.commit_allowed)
        self.assertEqual(decision.reason, "persistence and checkpoints complete")
        self.assertIsNone(decision.failure_class)


if __name__ == "__main__":
    unittest.main()
