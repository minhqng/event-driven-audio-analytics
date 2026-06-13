# FMA-Small Bounded Evaluation Report

Generated at: `2026-06-13T03:59:10.656023Z`

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
| deterministic-review-demo | 5879.950 | 1652.819 | 279.524 | 13.601 | 23.988 | 26.861 | 11.260 |
| fma-small-burst-100 | 126934.592 | 110060.470 | 97291.060 | 15.341 | 17.908 | 29.554 | 3.581 |
| fma-small-burst-5 | 15886.562 | 6099.108 | 4494.238 | 13.203 | 18.773 | 27.690 | 2.671 |
| fma-small-full-local-experiment | 0.000 | n/a | n/a | n/a | n/a | n/a | n/a |
| fma-small-scaling-r1 | 14600.693 | 6010.150 | 4568.835 | 13.841 | 17.913 | 26.524 | 2.527 |
| fma-small-scaling-r2 | 14990.952 | 6430.837 | 4886.273 | 15.012 | 19.147 | 35.874 | 2.843 |
| fma-small-scaling-r3 | 15272.382 | 6790.265 | 5202.530 | 14.492 | 20.707 | 35.595 | 2.734 |

## Throughput

| scenario | tracks_per_minute | segments_per_minute | writer_records_per_minute |
| --- | --- | --- | --- |
| deterministic-review-demo | 20.408 | 30.613 | 153.063 |
| fma-small-burst-5 | 18.884 | 362.571 | 1121.703 |
| fma-small-burst-100 | 47.268 | 913.699 | 2790.256 |
| fma-small-scaling-r1 | 20.547 | 394.502 | 1220.490 |
| fma-small-scaling-r2 | 20.012 | 384.232 | 1188.717 |
| fma-small-scaling-r3 | 19.643 | 377.151 | 1166.812 |
| fma-small-full-local-experiment | 0.000 | 0.000 | 0.000 |

## Resource Usage

| scenario | container | cpu_mean_pct | cpu_max_pct | memory_max_mb |
| --- | --- | --- | --- | --- |
| deterministic-review-demo | kafka | 5.300 | 5.300 | 397.400 |
| deterministic-review-demo | processing | 0.050 | 0.050 | 157.800 |
| deterministic-review-demo | timescaledb | 0.020 | 0.020 | 38.470 |
| deterministic-review-demo | writer | 0.180 | 0.180 | 27.100 |
| fma-small-burst-100 | kafka | 30.425 | 148.530 | 589.300 |
| fma-small-burst-100 | processing | 207.368 | 473.290 | 288.400 |
| fma-small-burst-100 | timescaledb | 25.219 | 51.550 | 48.030 |
| fma-small-burst-100 | writer | 16.704 | 63.410 | 44.520 |
| fma-small-burst-5 | kafka | 58.443 | 223.770 | 479.000 |
| fma-small-burst-5 | processing | 114.120 | 456.330 | 258.700 |
| fma-small-burst-5 | timescaledb | 4.862 | 19.390 | 41.640 |
| fma-small-burst-5 | writer | 2.210 | 8.750 | 26.950 |
| fma-small-full-local-experiment | n/a | n/a | n/a | n/a |
| fma-small-scaling-r1 | kafka | 67.507 | 187.930 | 496.900 |
| fma-small-scaling-r1 | processing | 117.913 | 342.360 | 260.100 |
| fma-small-scaling-r1 | timescaledb | 5.887 | 16.410 | 42.240 |
| fma-small-scaling-r1 | writer | 21.320 | 63.390 | 26.940 |
| fma-small-scaling-r2 | kafka | 44.053 | 118.350 | 430.200 |
| fma-small-scaling-r2 | processing | 110.743 | 487.380 | 265.400 |
| fma-small-scaling-r2 | timescaledb | 6.147 | 18.380 | 41.930 |
| fma-small-scaling-r2 | writer | 8.437 | 25.140 | 32.220 |
| fma-small-scaling-r3 | kafka | 17.622 | 35.680 | 405.200 |
| fma-small-scaling-r3 | processing | 67.588 | 364.170 | 286.400 |
| fma-small-scaling-r3 | timescaledb | 4.570 | 13.080 | 42.120 |
| fma-small-scaling-r3 | writer | 15.360 | 61.220 | 48.600 |

## Scaling Evidence

audio.segment.ready is currently created with 1 partition; processing replica scaling is partition-bound.

| scenario | processing_replicas | segments_per_minute | processing_ms_p95 | processing_cpu_mean_pct |
| --- | --- | --- | --- | --- |
| fma-small-scaling-r1 | 1 | 394.502 | 26.524 | 117.913 |
| fma-small-scaling-r2 | 2 | 384.232 | 35.874 | 110.743 |
| fma-small-scaling-r3 | 3 | 377.151 | 35.595 | 67.588 |

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
