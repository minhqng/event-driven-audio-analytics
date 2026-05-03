from __future__ import annotations

import json

import pytest

from event_driven_audio_analytics.evaluation.resources import (
    infer_service_name,
    load_resource_samples,
    parse_docker_stats_json_line,
    parse_memory_mb,
    summarize_resource_samples,
)


def test_parse_docker_stats_json_line_normalizes_service_and_units() -> None:
    sample = parse_docker_stats_json_line(
        json.dumps(
            {
                "Name": "event-driven-audio-analytics-processing-1",
                "CPUPerc": "12.50%",
                "MemUsage": "256MiB / 4GiB",
            }
        )
    )

    assert sample.service == "processing"
    assert sample.container == "event-driven-audio-analytics-processing-1"
    assert sample.cpu_percent == pytest.approx(12.5)
    assert sample.memory_mb == pytest.approx(256.0)


def test_memory_parser_supports_common_docker_units() -> None:
    assert parse_memory_mb("1024KiB / 2GiB") == pytest.approx(1.0)
    assert parse_memory_mb("1GiB / 2GiB") == pytest.approx(1024.0)


def test_resource_summary_groups_by_service() -> None:
    first = parse_docker_stats_json_line(
        '{"Name":"event-driven-audio-analytics-writer-1","CPUPerc":"10%","MemUsage":"100MiB / 1GiB"}'
    )
    second = parse_docker_stats_json_line(
        '{"Name":"event-driven-audio-analytics-writer-1","CPUPerc":"30%","MemUsage":"200MiB / 1GiB"}'
    )

    summary = summarize_resource_samples([first, second])

    assert summary["writer"]["samples"] == 2
    assert summary["writer"]["cpu_percent"]["mean"] == 20.0
    assert summary["writer"]["memory_mb"]["max"] == 200.0


def test_unknown_container_name_is_preserved_as_service_name() -> None:
    assert infer_service_name("custom-container") == "custom-container"


def test_load_resource_samples_accepts_power_shell_utf8_bom(tmp_path) -> None:
    samples_path = tmp_path / "resource-samples.jsonl"
    samples_path.write_text(
        '\ufeff{"Name":"event-driven-audio-analytics-kafka-1","CPUPerc":"5%","MemUsage":"64MiB / 1GiB"}\n',
        encoding="utf-8",
    )

    samples = load_resource_samples(str(samples_path))

    assert len(samples) == 1
    assert samples[0].service == "kafka"
    assert samples[0].cpu_percent == 5.0
