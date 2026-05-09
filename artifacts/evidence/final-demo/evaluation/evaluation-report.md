# FMA-Small Bounded Evaluation Report

Generated at: `2026-05-09T10:00:24.850030Z`

## Summary

This report is bounded local FMA-Small evidence for the PoC. It is not benchmark-scale performance evidence and does not claim production-ready throughput.

## Scenario Matrix

| scenario | run_id | status | requested_tracks | accepted_tracks | segments | storage_backend | processing_replicas |
| --- | --- | --- | --- | --- | --- | --- | --- |
| deterministic-review-demo | eval-deterministic-review-demo | passed | 2 | 1 | 3 | local | 1 |
| fma-small-burst-5 | eval-fma-5 | passed | 5 | 5 | 96 | local | 1 |
| fma-small-burst-100 | eval-fma-100 | passed | 100 | 100 | 1933 | local | 1 |
| fma-small-scaling-r1 | eval-scale-r1 | passed | 5 | 5 | 96 | local | 1 |
| fma-small-scaling-r2 | eval-scale-r2 | passed | 5 | 5 | 96 | local | 2 |
| fma-small-scaling-r3 | eval-scale-r3 | passed | 5 | 5 | 96 | local | 3 |
| fma-small-full-local-experiment | eval-fma-full-local | skipped | n/a | 0 | 0 | local | 1 |

## Latency

| scenario | wall_clock_ms | db_span_ms | artifact_write_mean_ms | artifact_read_p95_ms | processing_p50_ms | processing_p95_ms | writer_p95_ms |
| --- | --- | --- | --- | --- | --- | --- | --- |
| deterministic-review-demo | 9815.418 | 2858.931 | 881.498 | 42.269 | 65.478 | 66.507 | 30.939 |
| fma-small-burst-100 | 320213.681 | 273206.506 | 237881.214 | 34.693 | 44.838 | 89.957 | 8.599 |
| fma-small-burst-5 | 36382.111 | 14110.854 | 12119.048 | 42.809 | 49.523 | 92.367 | 6.142 |
| fma-small-full-local-experiment | 0.000 | n/a | n/a | n/a | n/a | n/a | n/a |
| fma-small-scaling-r1 | 36896.803 | 14509.500 | 12542.061 | 31.312 | 51.669 | 97.549 | 7.070 |
| fma-small-scaling-r2 | 39621.155 | 14739.794 | 12171.594 | 37.251 | 50.060 | 116.474 | 6.649 |
| fma-small-scaling-r3 | 37521.533 | 14755.789 | 11860.500 | 47.465 | 45.853 | 151.244 | 7.299 |

## Throughput

| scenario | tracks_per_minute | segments_per_minute | writer_records_per_minute |
| --- | --- | --- | --- |
| deterministic-review-demo | 12.226 | 18.338 | 91.692 |
| fma-small-burst-5 | 8.246 | 158.320 | 489.801 |
| fma-small-burst-100 | 18.737 | 362.196 | 1106.074 |
| fma-small-scaling-r1 | 8.131 | 156.111 | 482.969 |
| fma-small-scaling-r2 | 7.572 | 145.377 | 449.760 |
| fma-small-scaling-r3 | 7.995 | 153.512 | 474.927 |
| fma-small-full-local-experiment | 0.000 | 0.000 | 0.000 |

## Resource Usage

| scenario | container | cpu_mean_pct | cpu_max_pct | memory_max_mb |
| --- | --- | --- | --- | --- |
| deterministic-review-demo | cinema_app | 240.395 | 480.620 | 171.400 |
| deterministic-review-demo | ingestion | 146.020 | 146.020 | 42.520 |
| deterministic-review-demo | kafka | 60.680 | 90.100 | 405.700 |
| deterministic-review-demo | processing | 11.760 | 23.440 | 160.500 |
| deterministic-review-demo | timescaledb | 7.330 | 14.620 | 41.830 |
| deterministic-review-demo | writer | 1.970 | 3.590 | 26.850 |
| fma-small-burst-100 | cinema_app | 236.771 | 480.800 | 196.200 |
| fma-small-burst-100 | event-driven-audio-analytics-pytest-run-edd3c3daa477 | 95.477 | 173.190 | 224.600 |
| fma-small-burst-100 | ingestion | 58.507 | 236.970 | 785.000 |
| fma-small-burst-100 | kafka | 63.931 | 232.290 | 633.200 |
| fma-small-burst-100 | processing | 114.103 | 378.750 | 324.000 |
| fma-small-burst-100 | timescaledb | 27.357 | 82.770 | 47.060 |
| fma-small-burst-100 | writer | 18.769 | 107.750 | 48.910 |
| fma-small-burst-5 | cinema_app | 168.073 | 385.250 | 188.100 |
| fma-small-burst-5 | event-driven-audio-analytics-pytest-run-c635ade7d53a | 54.150 | 54.150 | 194.700 |
| fma-small-burst-5 | ingestion | 97.132 | 201.720 | 589.000 |
| fma-small-burst-5 | kafka | 65.069 | 180.050 | 433.700 |
| fma-small-burst-5 | processing | 65.051 | 153.120 | 294.000 |
| fma-small-burst-5 | timescaledb | 6.923 | 18.990 | 42.620 |
| fma-small-burst-5 | writer | 17.117 | 83.000 | 44.450 |
| fma-small-full-local-experiment | n/a | n/a | n/a | n/a |
| fma-small-scaling-r1 | cinema_app | 242.034 | 398.070 | 163.800 |
| fma-small-scaling-r1 | event-driven-audio-analytics-pytest-run-da03b7da28d5 | 85.570 | 85.570 | 159.700 |
| fma-small-scaling-r1 | ingestion | 75.930 | 183.910 | 288.200 |
| fma-small-scaling-r1 | kafka | 70.241 | 199.330 | 451.700 |
| fma-small-scaling-r1 | processing | 81.216 | 153.880 | 309.500 |
| fma-small-scaling-r1 | timescaledb | 6.524 | 19.900 | 42.600 |
| fma-small-scaling-r1 | writer | 17.916 | 92.520 | 26.930 |
| fma-small-scaling-r2 | cinema_app | 244.367 | 483.000 | 176.600 |
| fma-small-scaling-r2 | event-driven-audio-analytics-pytest-run-573a5fd99408 | 68.670 | 89.660 | 234.000 |
| fma-small-scaling-r2 | ingestion | 67.078 | 149.860 | 383.800 |
| fma-small-scaling-r2 | kafka | 51.353 | 233.060 | 450.200 |
| fma-small-scaling-r2 | processing | 42.929 | 181.060 | 262.900 |
| fma-small-scaling-r2 | timescaledb | 4.039 | 15.570 | 42.190 |
| fma-small-scaling-r2 | writer | 5.614 | 20.090 | 27.150 |
| fma-small-scaling-r3 | cinema_app | 216.050 | 396.180 | 186.100 |
| fma-small-scaling-r3 | event-driven-audio-analytics-pytest-run-6502018db38f | 88.095 | 111.040 | 372.400 |
| fma-small-scaling-r3 | ingestion | 74.318 | 160.990 | 384.000 |
| fma-small-scaling-r3 | kafka | 87.075 | 244.120 | 482.800 |
| fma-small-scaling-r3 | processing | 42.977 | 175.010 | 309.700 |
| fma-small-scaling-r3 | timescaledb | 5.889 | 27.020 | 42.460 |
| fma-small-scaling-r3 | writer | 6.633 | 22.030 | 27.160 |

## Scaling Evidence

audio.segment.ready is currently created with 1 partition; processing replica scaling is partition-bound.

| scenario | processing_replicas | segments_per_minute | processing_ms_p95 | processing_cpu_mean_pct |
| --- | --- | --- | --- | --- |
| fma-small-scaling-r1 | 1 | 156.111 | 97.549 | 81.216 |
| fma-small-scaling-r2 | 2 | 145.377 | 116.474 | 42.929 |
| fma-small-scaling-r3 | 3 | 153.512 | 151.244 | 42.977 |

Verdict: `bounded_partition_limited_evidence`

## Restart/Replay Evidence

- Summary: `/app/artifacts/evidence/final-demo/restart-replay/restart-replay-summary.json`
- Baseline: `/app/artifacts/evidence/final-demo/restart-replay/restart-replay-baseline.json`
- Run ID: `replay-smoke`
- Metadata rows: 2
- Feature rows: 3
- Processing metric rows: 6
- Writer write metric rows: 30

## Limitations

- Measurements are bounded local PoC evidence only.
- End-to-end latency uses script wall-clock timing and DB activity span.
- Per-segment ingestion-created timestamps are not persisted through the full pipeline.
- CPU and memory are Docker container samples, not kernel-level profiling.
- Scaling is limited by the current single-partition Kafka topic setup.
- Full FMA-Small runs are optional local experiments only.
- No model training, model serving, Flink, Spark, or additional datasets are included.
