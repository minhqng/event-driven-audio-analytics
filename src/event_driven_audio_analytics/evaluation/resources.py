"""Docker resource sample parsing for bounded evaluation evidence."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import json
import re

from event_driven_audio_analytics.evaluation.stats import summarize_distribution


RESOURCE_SERVICE_NAMES = (
    "ingestion",
    "processing",
    "writer",
    "timescaledb",
    "kafka",
    "minio",
    "review",
    "dataset-exporter",
)

_MEMORY_UNITS = {
    "b": 1.0 / (1024.0 * 1024.0),
    "kb": 1000.0 / (1024.0 * 1024.0),
    "kib": 1.0 / 1024.0,
    "mb": 1000.0 * 1000.0 / (1024.0 * 1024.0),
    "mib": 1.0,
    "gb": 1000.0 * 1000.0 * 1000.0 / (1024.0 * 1024.0),
    "gib": 1024.0,
}


@dataclass(frozen=True, slots=True)
class ResourceSample:
    """One normalized Docker stats sample."""

    service: str
    container: str
    cpu_percent: float
    memory_mb: float


def _parse_percent(raw_value: object) -> float:
    return float(str(raw_value).strip().removesuffix("%"))


def parse_memory_mb(raw_value: object) -> float:
    """Parse Docker memory strings such as ``12.5MiB / 2GiB``."""

    first_part = str(raw_value).split("/", 1)[0].strip()
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]+)", first_part)
    if match is None:
        raise ValueError(f"Unsupported Docker memory value: {raw_value!r}.")
    magnitude = float(match.group(1))
    unit = match.group(2).lower()
    if unit not in _MEMORY_UNITS:
        raise ValueError(f"Unsupported Docker memory unit: {unit!r}.")
    return magnitude * _MEMORY_UNITS[unit]


def infer_service_name(container_name: str) -> str:
    """Infer the Compose service from a Docker stats container name."""

    lowered = container_name.lower()
    for service_name in RESOURCE_SERVICE_NAMES:
        normalized_service = service_name.replace("-", "_")
        if f"-{service_name}-" in lowered or f"_{normalized_service}_" in lowered:
            return service_name
        if lowered == service_name:
            return service_name
    return container_name


def parse_docker_stats_json_line(raw_line: str) -> ResourceSample:
    """Parse one ``docker stats --format '{{json .}}'`` line."""

    payload = json.loads(raw_line)
    container_name = str(payload.get("Name") or payload.get("Container") or "unknown")
    return ResourceSample(
        service=infer_service_name(container_name),
        container=container_name,
        cpu_percent=_parse_percent(payload.get("CPUPerc", "0%")),
        memory_mb=parse_memory_mb(payload.get("MemUsage", "0B / 0B")),
    )


def load_resource_samples(path: str | None) -> list[ResourceSample]:
    """Load Docker stats JSONL samples from a file if provided."""

    if path is None:
        return []

    samples: list[ResourceSample] = []
    with open(path, encoding="utf-8-sig") as handle:
        for raw_line in handle:
            line = raw_line.strip().lstrip("\ufeff")
            if line:
                samples.append(parse_docker_stats_json_line(line))
    return samples


def summarize_resource_samples(samples: Iterable[ResourceSample]) -> dict[str, object]:
    """Group resource samples by service."""

    grouped: dict[str, list[ResourceSample]] = {}
    for sample in samples:
        grouped.setdefault(sample.service, []).append(sample)

    return {
        service_name: {
            "samples": len(service_samples),
            "cpu_percent": summarize_distribution(
                sample.cpu_percent for sample in service_samples
            ),
            "memory_mb": summarize_distribution(sample.memory_mb for sample in service_samples),
        }
        for service_name, service_samples in sorted(grouped.items())
    }
