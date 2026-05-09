# K3s / Kubernetes Variant

Run commands from the repository root.

This variant is a bounded private-cloud-style mapping of the existing
FMA-Small event-driven audio analytics system onto Kubernetes primitives. It
supports the thesis private-cloud deployment narrative while remaining
single-node-friendly K3s demonstration only. Docker Compose remains the default
local path.

## Boundaries

- Keep the current `ingestion -> processing -> writer -> review/Grafana` shape.
- Keep Kafka as small-event transport only.
- Keep the review console read-only.
- Keep Grafana as corroboration, not the front door.
- Do not treat this as HA, production, or benchmark-scale infrastructure.

## Manifest Layout

- `deploy/k8s/`: root Kustomize entrypoint, namespace, shared ConfigMap, Secret example, and artifacts PVC.
- `deploy/k8s/kafka/`: single-broker KRaft StatefulSet, Services, and topic bootstrap Job.
- `deploy/k8s/timescaledb/`: single-replica StatefulSet, Service, PVC, and SQL init assets.
- `deploy/k8s/minio/`: single-replica StatefulSet, Service, PVC, and bucket-init Job.
- `deploy/k8s/grafana/`: Deployment, Service, and file-provisioned dashboards.
- `deploy/k8s/processing/`, `deploy/k8s/writer/`, `deploy/k8s/review/`: long-running service Deployments.
- `deploy/k8s/ingestion/`: deterministic demo prep, demo ingestion Jobs, FMA burst Jobs, and FMA input PVC.
- `deploy/k8s/dataset-exporter/`: one-shot dataset bundle export Jobs.

The root `deploy/k8s/kustomization.yaml` includes only long-lived platform
resources. One-shot Jobs stay outside the root apply set so demo and evaluation
actions remain deliberate.

## Image Preparation

Build the repo-owned images first:

```powershell
docker compose build ingestion processing writer review dataset-exporter
```

```sh
docker compose build ingestion processing writer review dataset-exporter
```

If K3s uses its own containerd, import the images after building:

```powershell
docker save `
  event-driven-audio-analytics-ingestion:latest `
  event-driven-audio-analytics-processing:latest `
  event-driven-audio-analytics-writer:latest `
  event-driven-audio-analytics-review:latest `
  event-driven-audio-analytics-dataset-exporter:latest | `
  sudo k3s ctr images import -
```

```sh
docker save \
  event-driven-audio-analytics-ingestion:latest \
  event-driven-audio-analytics-processing:latest \
  event-driven-audio-analytics-writer:latest \
  event-driven-audio-analytics-review:latest \
  event-driven-audio-analytics-dataset-exporter:latest | \
  sudo k3s ctr images import -
```

If you prefer a registry-based path, push the same image names to a registry
reachable by K3s and update the manifests before apply.

## Platform Bootstrap

1. Create the namespace first so namespaced examples can be applied cleanly:

```powershell
kubectl apply -f deploy/k8s/namespace.yaml
```

```sh
kubectl apply -f deploy/k8s/namespace.yaml
```

2. Copy and edit the tracked Secret example:

```powershell
Copy-Item deploy/k8s/secrets.example.yaml deploy/k8s/secrets.yaml
kubectl apply -f deploy/k8s/secrets.yaml
```

```sh
cp deploy/k8s/secrets.example.yaml deploy/k8s/secrets.yaml
kubectl apply -f deploy/k8s/secrets.yaml
```

3. Apply the bounded base stack:

```powershell
kubectl apply -k deploy/k8s
```

```sh
kubectl apply -k deploy/k8s
```

4. Wait for the platform dependencies that must be ready before bucket and topic bootstrap:

```powershell
kubectl wait -n fma-small-analytics --for=condition=ready pod -l app.kubernetes.io/name=kafka --timeout=180s
kubectl wait -n fma-small-analytics --for=condition=ready pod -l app.kubernetes.io/name=timescaledb --timeout=180s
kubectl wait -n fma-small-analytics --for=condition=ready pod -l app.kubernetes.io/name=minio --timeout=180s
kubectl wait -n fma-small-analytics --for=condition=available deployment/grafana --timeout=180s
```

```sh
kubectl wait -n fma-small-analytics --for=condition=ready pod -l app.kubernetes.io/name=kafka --timeout=180s
kubectl wait -n fma-small-analytics --for=condition=ready pod -l app.kubernetes.io/name=timescaledb --timeout=180s
kubectl wait -n fma-small-analytics --for=condition=ready pod -l app.kubernetes.io/name=minio --timeout=180s
kubectl wait -n fma-small-analytics --for=condition=available deployment/grafana --timeout=180s
```

5. Create the MinIO artifact bucket before waiting on `review`. Review remains
   read-only, so bucket creation is handled by this bounded init Job.

```powershell
kubectl apply -f deploy/k8s/minio/bucket-init.yaml
kubectl wait -n fma-small-analytics --for=condition=complete job/minio-bucket-init --timeout=180s
kubectl logs -n fma-small-analytics job/minio-bucket-init
kubectl wait -n fma-small-analytics --for=condition=available deployment/review --timeout=180s
```

```sh
kubectl apply -f deploy/k8s/minio/bucket-init.yaml
kubectl wait -n fma-small-analytics --for=condition=complete job/minio-bucket-init --timeout=180s
kubectl logs -n fma-small-analytics job/minio-bucket-init
kubectl wait -n fma-small-analytics --for=condition=available deployment/review --timeout=180s
```

6. Bootstrap the Kafka topics before waiting on `processing` and `writer`.
   Their readiness probes call service preflight, which requires the bounded
   topic set to already exist.

```powershell
kubectl apply -f deploy/k8s/kafka/topic-bootstrap.yaml
kubectl wait -n fma-small-analytics --for=condition=complete job/kafka-topic-bootstrap --timeout=180s
kubectl logs -n fma-small-analytics job/kafka-topic-bootstrap
```

```sh
kubectl apply -f deploy/k8s/kafka/topic-bootstrap.yaml
kubectl wait -n fma-small-analytics --for=condition=complete job/kafka-topic-bootstrap --timeout=180s
kubectl logs -n fma-small-analytics job/kafka-topic-bootstrap
```

7. Wait for the topic-dependent services after bootstrap:

```powershell
kubectl wait -n fma-small-analytics --for=condition=available deployment/processing --timeout=180s
kubectl wait -n fma-small-analytics --for=condition=available deployment/writer --timeout=180s
```

```sh
kubectl wait -n fma-small-analytics --for=condition=available deployment/processing --timeout=180s
kubectl wait -n fma-small-analytics --for=condition=available deployment/writer --timeout=180s
```

## Deterministic Review Demo

Prepare the in-cluster deterministic review inputs:

```powershell
kubectl apply -f deploy/k8s/ingestion/review-demo-input-prep.yaml
kubectl wait -n fma-small-analytics --for=condition=complete job/review-demo-input-prep --timeout=180s
```

```sh
kubectl apply -f deploy/k8s/ingestion/review-demo-input-prep.yaml
kubectl wait -n fma-small-analytics --for=condition=complete job/review-demo-input-prep --timeout=180s
```

Run the bounded ingestion Jobs in order:

```powershell
kubectl apply -f deploy/k8s/ingestion/demo-high-energy.yaml
kubectl wait -n fma-small-analytics --for=condition=complete job/ingestion-demo-high-energy --timeout=300s
kubectl apply -f deploy/k8s/ingestion/demo-silent-oriented.yaml
kubectl wait -n fma-small-analytics --for=condition=complete job/ingestion-demo-silent-oriented --timeout=300s
kubectl apply -f deploy/k8s/ingestion/demo-validation-failure.yaml
kubectl wait -n fma-small-analytics --for=condition=complete job/ingestion-demo-validation-failure --timeout=300s
```

```sh
kubectl apply -f deploy/k8s/ingestion/demo-high-energy.yaml
kubectl wait -n fma-small-analytics --for=condition=complete job/ingestion-demo-high-energy --timeout=300s
kubectl apply -f deploy/k8s/ingestion/demo-silent-oriented.yaml
kubectl wait -n fma-small-analytics --for=condition=complete job/ingestion-demo-silent-oriented --timeout=300s
kubectl apply -f deploy/k8s/ingestion/demo-validation-failure.yaml
kubectl wait -n fma-small-analytics --for=condition=complete job/ingestion-demo-validation-failure --timeout=300s
```

The shared review pinned order stays:

```text
demo-high-energy,demo-silent-oriented,demo-validation-failure
```

## Access Paths

Open the read-only review surface first:

```powershell
kubectl port-forward -n fma-small-analytics service/review 8080:8080
```

```sh
kubectl port-forward -n fma-small-analytics service/review 8080:8080
```

Use Grafana as corroboration after the review story is clear:

```powershell
kubectl port-forward -n fma-small-analytics service/grafana 3000:3000
```

```sh
kubectl port-forward -n fma-small-analytics service/grafana 3000:3000
```

Optional MinIO console:

```powershell
kubectl port-forward -n fma-small-analytics service/minio 9001:9001
```

```sh
kubectl port-forward -n fma-small-analytics service/minio 9001:9001
```

## Dataset Export Jobs

Export the deterministic demo bundles after the demo runs have persisted:

```powershell
kubectl apply -f deploy/k8s/dataset-exporter/demo-high-energy.yaml
kubectl apply -f deploy/k8s/dataset-exporter/demo-silent-oriented.yaml
kubectl apply -f deploy/k8s/dataset-exporter/demo-validation-failure.yaml
kubectl wait -n fma-small-analytics --for=condition=complete job/dataset-export-demo-high-energy --timeout=300s
kubectl wait -n fma-small-analytics --for=condition=complete job/dataset-export-demo-silent-oriented --timeout=300s
kubectl wait -n fma-small-analytics --for=condition=complete job/dataset-export-demo-validation-failure --timeout=300s
```

```sh
kubectl apply -f deploy/k8s/dataset-exporter/demo-high-energy.yaml
kubectl apply -f deploy/k8s/dataset-exporter/demo-silent-oriented.yaml
kubectl apply -f deploy/k8s/dataset-exporter/demo-validation-failure.yaml
kubectl wait -n fma-small-analytics --for=condition=complete job/dataset-export-demo-high-energy --timeout=300s
kubectl wait -n fma-small-analytics --for=condition=complete job/dataset-export-demo-silent-oriented --timeout=300s
kubectl wait -n fma-small-analytics --for=condition=complete job/dataset-export-demo-validation-failure --timeout=300s
```

Bundle output lands on the shared `artifacts-pvc` under:

```text
/app/artifacts/datasets/<run_id>/
```

## Local FMA Burst and Scaling

For operator-supplied local FMA-Small data, first create a separate PVC:

```powershell
kubectl apply -f deploy/k8s/ingestion/fma-input-pvc.yaml
```

```sh
kubectl apply -f deploy/k8s/ingestion/fma-input-pvc.yaml
```

Populate it with:

```text
/app/data/local/fma_metadata/tracks.csv
/app/data/local/fma_small/<prefix>/<track_id>.mp3
```

Run the bounded burst Jobs:

```powershell
kubectl apply -f deploy/k8s/ingestion/fma-burst-5.yaml
kubectl wait -n fma-small-analytics --for=condition=complete job/ingestion-fma-burst-5 --timeout=600s
kubectl apply -f deploy/k8s/ingestion/fma-burst-100.yaml
kubectl wait -n fma-small-analytics --for=condition=complete job/ingestion-fma-burst-100 --timeout=1800s
```

```sh
kubectl apply -f deploy/k8s/ingestion/fma-burst-5.yaml
kubectl wait -n fma-small-analytics --for=condition=complete job/ingestion-fma-burst-5 --timeout=600s
kubectl apply -f deploy/k8s/ingestion/fma-burst-100.yaml
kubectl wait -n fma-small-analytics --for=condition=complete job/ingestion-fma-burst-100 --timeout=1800s
```

Manual bounded scaling path:

- Scale `processing` to `1`, `2`, and `3` replicas with `kubectl scale deployment/processing --replicas=<n>`.
- Use distinct run IDs for repeated 5-track runs:
  - `k3s-scale-r1`
  - `k3s-scale-r2`
  - `k3s-scale-r3`
- Inspect:
  - `kubectl logs`
  - `kubectl top pods`
  - review console output
  - Grafana dashboards
  - dataset-exporter output bundles

Phase 7.1 documents the K3s evaluation path, but does not port the Compose
evaluation scripts into Kubernetes automation.

## Operational Notes

- The manifests assume a default writable K3s storage class such as the common
  local-path provisioner.
- Kafka remains single-broker and single-partition by design in this bounded
  variant.
- MinIO-backed claim-check URIs remain under:

```text
s3://fma-small-artifacts/runs/<run_id>/segments/<track_id>/<segment_idx>.wav
s3://fma-small-artifacts/runs/<run_id>/manifests/segments.parquet
```

- `artifacts-pvc` remains necessary even when `STORAGE_BACKEND=minio` because
  it stores review demo inputs, processing state snapshots, and dataset export
  bundles.
- Jobs are intentionally outside the root Kustomize apply set. Re-run them by
  deleting the finished Job and applying the YAML again.

## Non-Production Limits

- Single broker Kafka KRaft only
- Single replica TimescaleDB only
- Single replica MinIO only
- Single replica Grafana only
- Manual scaling only
- No Ingress/TLS, no service mesh, no GitOps, no Terraform, no autoscaling,
  and no HA/DR claims
