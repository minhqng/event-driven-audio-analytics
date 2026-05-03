from __future__ import annotations

from pathlib import Path


EXPECTED_OUTPUTS = (
    "latency-summary.json",
    "throughput-summary.json",
    "resource-usage-summary.json",
    "scaling-summary.json",
    "evaluation-report.md",
)


def test_powershell_evaluation_script_contract() -> None:
    script = Path("scripts/evaluation/run-evaluation.ps1").read_text(encoding="utf-8")

    for expected_output in EXPECTED_OUTPUTS:
        assert expected_output in script or expected_output == "evaluation-report.md"
    assert "event_driven_audio_analytics.evaluation.collect" in script
    assert "event_driven_audio_analytics.evaluation.report" in script
    assert "deterministic-review-demo" in script
    assert "fma-small-burst-5" in script
    assert "fma-small-burst-100" in script
    assert "fma-small-full-local-experiment" in script
    assert "docker stats --no-stream" in script
    assert "Start-ResourceSampler" in script
    assert "Stop-ResourceSampler" in script
    assert "Start-Job" in script
    assert "--include-scaling" in script


def test_bash_evaluation_script_contract() -> None:
    script = Path("scripts/evaluation/run-evaluation.sh").read_text(encoding="utf-8")

    for expected_output in EXPECTED_OUTPUTS:
        assert expected_output in script or expected_output == "evaluation-report.md"
    assert "event_driven_audio_analytics.evaluation.collect" in script
    assert "event_driven_audio_analytics.evaluation.report" in script
    assert "deterministic-review-demo" in script
    assert "fma-small-burst-5" in script
    assert "fma-small-burst-100" in script
    assert "fma-small-full-local-experiment" in script
    assert "docker stats --no-stream" in script
    assert "start_resource_sampler" in script
    assert "stop_active_resource_sampler" in script
    assert "active_sampler_pid" in script
    assert "--include-scaling" in script
