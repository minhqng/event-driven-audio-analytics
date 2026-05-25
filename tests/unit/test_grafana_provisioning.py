from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_DASHBOARD_DIR = PROJECT_ROOT / "infra" / "grafana" / "dashboards"
K3S_DASHBOARD_DIR = PROJECT_ROOT / "deploy" / "k3s" / "grafana" / "config" / "dashboards"


def _load_dashboard(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _panel_by_title(dashboard: dict[str, object], title: str) -> dict[str, object]:
    panels = dashboard["panels"]
    assert isinstance(panels, list)
    for panel in panels:
        assert isinstance(panel, dict)
        if panel.get("title") == title:
            return panel
    raise AssertionError(f"Panel title not found: {title}")


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
    assert "GF_USERS_DEFAULT_THEME: light" in grafana_service


def test_grafana_dashboard_contracts_support_demo_presentation() -> None:
    expected = {
        "audio_quality.json": {
            "uid": "audio-quality",
            "title": "Chất lượng âm thanh (Audio Quality)",
            "panels": [
                "RMS theo thời gian",
                "Tỷ lệ silent segment theo run",
                "Số segment đã persist",
                "Kết quả validation",
                "RMS trung bình theo run",
                "Bảng tổng hợp audio",
            ],
        },
        "system_health.json": {
            "uid": "system-health",
            "title": "Bằng chứng vận hành (System Health)",
            "panels": [
                "Throughput segment đã persist",
                "Độ trễ processing theo thời gian",
                "Độ trễ writer DB theo topic",
                "Độ trễ ghi artifact claim-check",
                "Tỷ lệ lỗi validation theo run",
                "Bảng tổng hợp vận hành",
            ],
        },
    }

    for file_name, contract in expected.items():
        dashboard = _load_dashboard(COMPOSE_DASHBOARD_DIR / file_name)

        assert dashboard["uid"] == contract["uid"]
        assert dashboard["title"] == contract["title"]
        assert dashboard["editable"] is False
        assert dashboard["style"] == "light"

        panels = dashboard["panels"]
        assert isinstance(panels, list)
        assert [panel["title"] for panel in panels] == contract["panels"]

        for title in contract["panels"]:
            panel = _panel_by_title(dashboard, title)
            assert panel["datasource"]["uid"] == "timescaledb"
            assert str(panel.get("description", "")).strip()
            assert panel["gridPos"]["w"] in {12, 24}
            assert panel["gridPos"]["h"] >= 9


def test_grafana_dashboards_keep_compose_and_k3s_json_in_sync() -> None:
    for file_name in ("audio_quality.json", "system_health.json"):
        assert (COMPOSE_DASHBOARD_DIR / file_name).read_text(encoding="utf-8") == (
            K3S_DASHBOARD_DIR / file_name
        ).read_text(encoding="utf-8")


def test_grafana_dashboard_copy_does_not_overclaim_live_infra_health() -> None:
    forbidden_phrases = (
        "kafka healthy",
        "minio healthy",
        "cluster healthy",
        "production ready",
        "production-ready",
    )

    for file_name in ("audio_quality.json", "system_health.json"):
        dashboard_text = (COMPOSE_DASHBOARD_DIR / file_name).read_text(encoding="utf-8").lower()

        for phrase in forbidden_phrases:
            assert phrase not in dashboard_text
