# K3s Private-Cloud Variant

This directory contains the bounded private-cloud deployment variant for the
FMA-Small event-driven audio analytics system. Docker Compose remains the
default local/dev path; these manifests are for a single-node-friendly K3s
demonstration, not production HA.

## Component Map

- `namespace.yaml`, `configmap.yaml`, `secrets.example.yaml`: shared namespace,
  non-secret settings, and local secret template.
- `kafka/`: single-broker KRaft StatefulSet, Services, and topic bootstrap Job.
- `timescaledb/`: single-replica StatefulSet, Service, PVC, and SQL init files.
- `minio/`: single-replica StatefulSet, Service, PVC, and bucket-init Job.
- `grafana/`: Deployment, Service, and file-provisioned dashboards.
- `processing/`, `writer/`, `review/`: long-running service Deployments.
- `ingestion/`: deliberate one-shot Jobs for deterministic demo and bounded FMA
  bursts.
- `dataset-exporter/`: deliberate one-shot Jobs for bundle export.

The root `kustomization.yaml` includes only long-lived platform resources.
Bootstrap and demo Jobs are applied explicitly.

## Apply

```powershell
kubectl apply -f deploy/k3s/namespace.yaml
Copy-Item deploy/k3s/secrets.example.yaml deploy/k3s/secrets.yaml
kubectl apply -f deploy/k3s/secrets.yaml
kubectl apply -k deploy/k3s
```

```sh
kubectl apply -f deploy/k3s/namespace.yaml
cp deploy/k3s/secrets.example.yaml deploy/k3s/secrets.yaml
kubectl apply -f deploy/k3s/secrets.yaml
kubectl apply -k deploy/k3s
```

Wait for Kafka, TimescaleDB, MinIO, and Grafana before running init Jobs:

```sh
kubectl wait -n fma-small-analytics --for=condition=ready pod -l app.kubernetes.io/name=kafka --timeout=180s
kubectl wait -n fma-small-analytics --for=condition=ready pod -l app.kubernetes.io/name=timescaledb --timeout=180s
kubectl wait -n fma-small-analytics --for=condition=ready pod -l app.kubernetes.io/name=minio --timeout=180s
kubectl wait -n fma-small-analytics --for=condition=available deployment/grafana --timeout=180s
```

Run the required init Jobs:

```sh
kubectl apply -f deploy/k3s/minio/bucket-init.yaml
kubectl wait -n fma-small-analytics --for=condition=complete job/minio-bucket-init --timeout=180s
kubectl apply -f deploy/k3s/kafka/topic-bootstrap.yaml
kubectl wait -n fma-small-analytics --for=condition=complete job/kafka-topic-bootstrap --timeout=180s
```

Then wait for review, processing, and writer:

```sh
kubectl wait -n fma-small-analytics --for=condition=available deployment/review --timeout=180s
kubectl wait -n fma-small-analytics --for=condition=available deployment/processing --timeout=180s
kubectl wait -n fma-small-analytics --for=condition=available deployment/writer --timeout=180s
```

## Demo

Prepare deterministic inputs and run the three demo ingestion Jobs in order:

```sh
kubectl apply -f deploy/k3s/ingestion/review-demo-input-prep.yaml
kubectl wait -n fma-small-analytics --for=condition=complete job/review-demo-input-prep --timeout=180s
kubectl apply -f deploy/k3s/ingestion/demo-high-energy.yaml
kubectl wait -n fma-small-analytics --for=condition=complete job/ingestion-demo-high-energy --timeout=300s
kubectl apply -f deploy/k3s/ingestion/demo-silent-oriented.yaml
kubectl wait -n fma-small-analytics --for=condition=complete job/ingestion-demo-silent-oriented --timeout=300s
kubectl apply -f deploy/k3s/ingestion/demo-validation-failure.yaml
kubectl wait -n fma-small-analytics --for=condition=complete job/ingestion-demo-validation-failure --timeout=300s
```

Inspect the system:

```sh
kubectl port-forward -n fma-small-analytics service/review 8080:8080
kubectl port-forward -n fma-small-analytics service/grafana 3000:3000
kubectl port-forward -n fma-small-analytics service/minio 9001:9001
```

Export deterministic dataset bundles after writer persistence:

```sh
kubectl apply -f deploy/k3s/dataset-exporter/demo-high-energy.yaml
kubectl apply -f deploy/k3s/dataset-exporter/demo-silent-oriented.yaml
kubectl apply -f deploy/k3s/dataset-exporter/demo-validation-failure.yaml
```

## Bounded FMA Burst

Operator-supplied FMA-Small input uses `ingestion/fma-input-pvc.yaml` and is
mounted at `/app/data/local`. Run only bounded Jobs:

```sh
kubectl apply -f deploy/k3s/ingestion/fma-input-pvc.yaml
kubectl apply -f deploy/k3s/ingestion/fma-burst-5.yaml
kubectl apply -f deploy/k3s/ingestion/fma-burst-100.yaml
```

Processing can be manually scaled for partition-limited evidence:

```sh
kubectl scale -n fma-small-analytics deployment/processing --replicas=2
kubectl scale -n fma-small-analytics deployment/processing --replicas=3
```

## Validation

```sh
kubectl kustomize deploy/k3s
kubectl apply --dry-run=client --validate=false -k deploy/k3s
kubectl apply --dry-run=client --validate=false -f deploy/k3s/kafka/topic-bootstrap.yaml
kubectl apply --dry-run=client --validate=false -f deploy/k3s/minio/bucket-init.yaml
```

## Non-Production Limits

This variant is intentionally bounded: single-broker Kafka, single-replica
TimescaleDB, single-replica MinIO, no Ingress/TLS, no service mesh, no GitOps,
no Terraform, no autoscaling, no HA/DR, and no production benchmark claims.
