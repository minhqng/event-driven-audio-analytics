from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_grafana_datasource_uses_postgres_environment_references() -> None:
    datasource_config = (
        PROJECT_ROOT
        / "infra"
        / "grafana"
        / "provisioning"
        / "datasources"
        / "timescaledb.yaml"
    ).read_text(encoding="utf-8")

    assert 'url: "$POSTGRES_HOST:$POSTGRES_PORT"' in datasource_config
    assert 'database: "$POSTGRES_DB"' in datasource_config
    assert 'user: "$POSTGRES_USER"' in datasource_config
    assert 'password: "$POSTGRES_PASSWORD"' in datasource_config
    assert "database: audio_analytics" not in datasource_config
    assert "user: audio_analytics" not in datasource_config


def test_compose_passes_postgres_environment_to_grafana() -> None:
    compose_config = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    grafana_service = compose_config.split("  grafana:", maxsplit=1)[1].split(
        "\n  ingestion:",
        maxsplit=1,
    )[0]

    assert 'POSTGRES_DB: "${POSTGRES_DB:-audio_analytics}"' in grafana_service
    assert 'POSTGRES_USER: "${POSTGRES_USER:-audio_analytics}"' in grafana_service
    assert 'POSTGRES_PASSWORD: "${POSTGRES_PASSWORD:-audio_analytics}"' in grafana_service
    assert "POSTGRES_HOST: timescaledb" in grafana_service
    assert 'POSTGRES_PORT: "5432"' in grafana_service
