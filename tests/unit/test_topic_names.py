from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from event_driven_audio_analytics.shared.contracts.topics import ALL_TOPICS


class TopicNameTests(unittest.TestCase):
    def test_confirmed_topics_are_present(self) -> None:
        self.assertEqual(
            ALL_TOPICS,
            (
                "audio.metadata",
                "audio.segment.ready",
                "audio.features",
                "system.metrics",
            ),
        )


if __name__ == "__main__":
    unittest.main()
