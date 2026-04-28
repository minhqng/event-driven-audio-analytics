# Local Data

This directory is for local runtime inputs that should not be committed.

## FMA-small Layout

Place the full local FMA-small pack here when you want to run a bounded real-data burst:

```text
data/local/
|-- fma_metadata/
|   `-- tracks.csv
`-- fma_small/
    `-- <prefix>/<track_id>.mp3
```

`data/local/` is ignored by git and excluded from Docker build context. The Compose stack mounts it read-only into containers at `/app/data/local`.

## Default Demo

The final deterministic demo does not require this directory. It uses committed synthetic smoke fixtures and generated demo inputs under `artifacts/demo-inputs/`.
