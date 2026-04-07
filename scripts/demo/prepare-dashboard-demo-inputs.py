"""Wrapper for the dashboard demo-input helper."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from event_driven_audio_analytics.smoke.prepare_dashboard_demo_inputs import main


if __name__ == "__main__":
    main()
