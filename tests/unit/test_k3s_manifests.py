from __future__ import annotations

from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
K3S_ROOT = PROJECT_ROOT / "deploy" / "k3s"


def _load_yaml(path: Path) -> list[dict[str, object]]:
    return [
        document
        for document in yaml.safe_load_all(path.read_text(encoding="utf-8"))
        if document is not None
    ]


def _load_first(path: Path) -> dict[str, object]:
    documents = _load_yaml(path)
    assert len(documents) == 1
    return documents[0]


def _container_env_map(container: dict[str, object]) -> dict[str, str]:
    return {
        str(entry["name"]): str(entry["value"])
        for entry in container.get("env", [])
        if "value" in entry
    }


def test_kustomize_root_lists_expected_resources_and_generators() -> None:
    kustomization = _load_first(K3S_ROOT / "kustomization.yaml")

    assert kustomization["kind"] == "Kustomization"
    assert kustomization["namespace"] == "fma-small-analytics"
    assert set(kustomization["resources"]) == {
        "namespace.yaml",
        "configmap.yaml",
        "artifacts-pvc.yaml",
        "kafka/headless-service.yaml",
        "kafka/service.yaml",
        "kafka/statefulset.yaml",
        "timescaledb/pvc.yaml",
        "timescaledb/service.yaml",
        "timescaledb/statefulset.yaml",
        "minio/pvc.yaml",
        "minio/service.yaml",
        "minio/statefulset.yaml",
        "grafana/service.yaml",
        "grafana/deployment.yaml",
        "processing/deployment.yaml",
        "writer/deployment.yaml",
        "review/service.yaml",
        "review/deployment.yaml",
    }
    assert kustomization["generatorOptions"]["disableNameSuffixHash"] is True

    generators = {
        generator["name"]: generator["files"]
        for generator in kustomization["configMapGenerator"]
    }
    assert generators["timescaledb-init-sql"] == [
        "001_extensions.sql=./timescaledb/config/001_extensions.sql",
        "002_core_tables.sql=./timescaledb/config/002_core_tables.sql",
        "003_operational_views.sql=./timescaledb/config/003_operational_views.sql",
        "004_review_views.sql=./timescaledb/config/004_review_views.sql",
    ]
    assert generators["grafana-datasource-config"] == [
        "timescaledb.yaml=./grafana/config/provisioning/datasources/timescaledb.yaml"
    ]
    assert generators["grafana-dashboard-provider-config"] == [
        "dashboards.yaml=./grafana/config/provisioning/dashboards/dashboards.yaml"
    ]
    assert generators["grafana-dashboard-json"] == [
        "audio_quality.json=./grafana/config/dashboards/audio_quality.json",
        "system_health.json=./grafana/config/dashboards/system_health.json",
    ]


def test_required_component_directories_exist() -> None:
    expected = {
        "dataset-exporter",
        "grafana",
        "ingestion",
        "kafka",
        "minio",
        "processing",
        "review",
        "timescaledb",
        "writer",
    }

    assert expected <= {path.name for path in K3S_ROOT.iterdir() if path.is_dir()}


def test_app_config_defaults_to_minio_private_cloud_variant() -> None:
    config_map = _load_first(K3S_ROOT / "configmap.yaml")

    assert config_map["kind"] == "ConfigMap"
    data = config_map["data"]
    assert data["ARTIFACTS_ROOT"] == "/app/artifacts"
    assert data["DATASET_EXPORT_ROOT"] == "/app/artifacts/datasets"
    assert data["STORAGE_BACKEND"] == "minio"
    assert data["MINIO_ENDPOINT_URL"] == "http://minio:9000"
    assert data["MINIO_BUCKET"] == "fma-small-artifacts"
    assert data["MINIO_CREATE_BUCKET"] == "false"
    assert data["POSTGRES_HOST"] == "timescaledb"
    assert data["POSTGRES_PORT"] == "5432"
    assert data["KAFKA_BOOTSTRAP_SERVERS"] == "kafka:29092"
    assert (
        data["REVIEW_PINNED_RUN_IDS"]
        == "demo-high-energy,demo-silent-oriented,demo-validation-failure"
    )


def test_base_workloads_match_bounded_k3s_mapping() -> None:
    kafka = _load_first(K3S_ROOT / "kafka" / "statefulset.yaml")
    timescaledb = _load_first(K3S_ROOT / "timescaledb" / "statefulset.yaml")
    minio = _load_first(K3S_ROOT / "minio" / "statefulset.yaml")
    grafana = _load_first(K3S_ROOT / "grafana" / "deployment.yaml")
    processing = _load_first(K3S_ROOT / "processing" / "deployment.yaml")
    writer = _load_first(K3S_ROOT / "writer" / "deployment.yaml")
    review = _load_first(K3S_ROOT / "review" / "deployment.yaml")
    review_service = _load_first(K3S_ROOT / "review" / "service.yaml")

    assert kafka["kind"] == "StatefulSet"
    kafka_env = _container_env_map(kafka["spec"]["template"]["spec"]["containers"][0])
    assert kafka["spec"]["serviceName"] == "kafka-headless"
    assert kafka_env["KAFKA_CFG_ADVERTISED_LISTENERS"] == "PLAINTEXT://kafka:29092"
    assert kafka_env["KAFKA_CFG_NUM_PARTITIONS"] == "1"

    assert timescaledb["kind"] == "StatefulSet"
    timescaledb_mounts = {
        mount["name"]
        for mount in timescaledb["spec"]["template"]["spec"]["containers"][0][
            "volumeMounts"
        ]
    }
    assert "timescaledb-data" in timescaledb_mounts
    assert "timescaledb-init-sql" in timescaledb_mounts

    assert minio["kind"] == "StatefulSet"
    minio_container = minio["spec"]["template"]["spec"]["containers"][0]
    assert minio_container["image"] == "minio/minio:RELEASE.2025-04-22T22-12-26Z"
    assert minio_container["args"] == ["server", "/data", "--console-address", ":9001"]

    assert grafana["kind"] == "Deployment"
    grafana_mounts = {
        mount["name"]
        for mount in grafana["spec"]["template"]["spec"]["containers"][0][
            "volumeMounts"
        ]
    }
    assert grafana_mounts == {
        "grafana-datasource-config",
        "grafana-dashboard-provider-config",
        "grafana-dashboard-json",
    }

    assert processing["kind"] == "Deployment"
    assert processing["spec"]["replicas"] == 1
    processing_mounts = processing["spec"]["template"]["spec"]["containers"][0][
        "volumeMounts"
    ]
    assert processing_mounts[0]["mountPath"] == "/app/artifacts"

    assert writer["kind"] == "Deployment"
    writer_env = _container_env_map(writer["spec"]["template"]["spec"]["containers"][0])
    assert writer_env["SERVICE_NAME"] == "writer"

    assert review["kind"] == "Deployment"
    review_env = _container_env_map(review["spec"]["template"]["spec"]["containers"][0])
    assert review_env["SERVICE_NAME"] == "review"
    review_container = review["spec"]["template"]["spec"]["containers"][0]
    assert review_container["readinessProbe"]["exec"]["command"] == [
        "python",
        "-m",
        "event_driven_audio_analytics.review.app",
        "preflight",
    ]
    assert review_container["livenessProbe"]["httpGet"]["path"] == "/healthz"
    review_mounts = review["spec"]["template"]["spec"]["containers"][0]["volumeMounts"]
    assert review_mounts[0]["mountPath"] == "/app/artifacts"

    assert review_service["kind"] == "Service"
    assert review_service["spec"]["ports"][0]["port"] == 8080


def test_job_manifests_cover_demo_burst_and_export_paths() -> None:
    bootstrap = _load_first(K3S_ROOT / "kafka" / "topic-bootstrap.yaml")
    bucket_init = _load_first(K3S_ROOT / "minio" / "bucket-init.yaml")
    review_demo_prep = _load_first(
        K3S_ROOT / "ingestion" / "review-demo-input-prep.yaml"
    )
    demo_high = _load_first(K3S_ROOT / "ingestion" / "demo-high-energy.yaml")
    demo_silent = _load_first(K3S_ROOT / "ingestion" / "demo-silent-oriented.yaml")
    demo_fail = _load_first(
        K3S_ROOT / "ingestion" / "demo-validation-failure.yaml"
    )
    burst_5 = _load_first(K3S_ROOT / "ingestion" / "fma-burst-5.yaml")
    burst_100 = _load_first(K3S_ROOT / "ingestion" / "fma-burst-100.yaml")
    export_live = _load_first(K3S_ROOT / "dataset-exporter" / "fma-small-live.yaml")

    assert bootstrap["kind"] == "Job"
    bootstrap_script = bootstrap["spec"]["template"]["spec"]["containers"][0][
        "command"
    ][2]
    assert "audio.metadata audio.segment.ready audio.features system.metrics audio.dlq" in (
        bootstrap_script
    )

    bucket_init_container = bucket_init["spec"]["template"]["spec"]["containers"][0]
    assert bucket_init["kind"] == "Job"
    assert bucket_init_container["image"] == "minio/mc:RELEASE.2025-04-16T18-13-26Z"
    bucket_init_script = bucket_init_container["command"][2]
    assert 'mc mb --ignore-existing "local/$MINIO_BUCKET"' in bucket_init_script
    assert bucket_init_container["envFrom"] == [
        {"configMapRef": {"name": "app-config"}},
        {"secretRef": {"name": "platform-secrets"}},
    ]

    assert review_demo_prep["kind"] == "Job"
    prep_command = review_demo_prep["spec"]["template"]["spec"]["containers"][0][
        "command"
    ]
    assert prep_command[2] == "event_driven_audio_analytics.smoke.prepare_review_demo_inputs"
    assert prep_command[-1] == "/app/artifacts/demo-inputs/review-demo"

    for manifest, expected_run_id, expected_track_id in (
        (demo_high, "demo-high-energy", "910001"),
        (demo_silent, "demo-silent-oriented", "910002"),
        (demo_fail, "demo-validation-failure", "910003"),
    ):
        env = _container_env_map(manifest["spec"]["template"]["spec"]["containers"][0])
        assert manifest["kind"] == "Job"
        assert env["RUN_ID"] == expected_run_id
        assert env["TRACK_ID_ALLOWLIST"] == expected_track_id
        assert env["METADATA_CSV_PATH"] == "/app/artifacts/demo-inputs/review-demo/metadata.csv"
        assert env["AUDIO_ROOT_PATH"] == "/app/artifacts/demo-inputs/review-demo/fma_small"

    burst_5_env = _container_env_map(burst_5["spec"]["template"]["spec"]["containers"][0])
    burst_100_env = _container_env_map(
        burst_100["spec"]["template"]["spec"]["containers"][0]
    )
    assert burst_5_env["RUN_ID"] == "k3s-fma-5"
    assert burst_5_env["INGESTION_MAX_TRACKS"] == "5"
    assert burst_100_env["RUN_ID"] == "k3s-fma-100"
    assert burst_100_env["INGESTION_MAX_TRACKS"] == "100"
    assert {
        volume["persistentVolumeClaim"]["claimName"]
        for volume in burst_5["spec"]["template"]["spec"]["volumes"]
        if "persistentVolumeClaim" in volume
    } == {"artifacts-pvc", "fma-input-pvc"}

    export_live_container = export_live["spec"]["template"]["spec"]["containers"][0]
    assert export_live["kind"] == "Job"
    assert export_live_container["args"] == ["export", "--run-id", "fma-small-live"]


def test_secret_example_fma_input_pvc_and_docs_reference_component_layout() -> None:
    secret_example = _load_first(K3S_ROOT / "secrets.example.yaml")
    fma_input_pvc = _load_first(K3S_ROOT / "ingestion" / "fma-input-pvc.yaml")

    assert secret_example["kind"] == "Secret"
    assert set(secret_example["stringData"]) == {
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "MINIO_ACCESS_KEY",
        "MINIO_SECRET_KEY",
        "GRAFANA_ADMIN_USER",
        "GRAFANA_ADMIN_PASSWORD",
    }
    assert fma_input_pvc["kind"] == "PersistentVolumeClaim"
    assert fma_input_pvc["metadata"]["name"] == "fma-input-pvc"

    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    docs_index = (PROJECT_ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    validation = (PROJECT_ROOT / "docs" / "runbooks" / "validation.md").read_text(
        encoding="utf-8"
    )
    k3s_readme = (K3S_ROOT / "README.md").read_text(encoding="utf-8")
    k3s_runbook = (PROJECT_ROOT / "docs" / "runbooks" / "k3s.md").read_text(
        encoding="utf-8"
    )

    assert "deploy/k3s/secrets.yaml" in gitignore
    assert "deploy/k3s/" in readme
    assert "docs/runbooks/k3s.md" in readme
    assert "docs/runbooks/k3s.md" in docs_index
    assert "## K3s Private-Cloud Variant" in validation
    assert "kubectl apply -k deploy/k3s" in k3s_readme
    assert "kubectl apply -k deploy/k3s" in k3s_runbook
    assert "review-demo-input-prep.yaml" in k3s_runbook
    assert (
        k3s_runbook.index("kubectl apply -f deploy/k3s/namespace.yaml")
        < k3s_runbook.index("kubectl apply -f deploy/k3s/secrets.yaml")
    )
    assert (
        k3s_runbook.index("kubectl apply -f deploy/k3s/minio/bucket-init.yaml")
        < k3s_runbook.index(
            "kubectl wait -n fma-small-analytics "
            "--for=condition=available deployment/review --timeout=180s"
        )
    )
    assert (
        k3s_runbook.index("kubectl apply -f deploy/k3s/kafka/topic-bootstrap.yaml")
        < k3s_runbook.index(
            "kubectl wait -n fma-small-analytics "
            "--for=condition=available deployment/processing --timeout=180s"
        )
    )
