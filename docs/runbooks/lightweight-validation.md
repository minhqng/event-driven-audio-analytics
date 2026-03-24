# Lightweight Validation

Use lightweight checks that match the maturity of this scaffold:

## Tree And Script Presence

```sh
./scripts/smoke/check-tree.sh
```

## Compose Config Sanity

```sh
./scripts/smoke/check-compose.sh
```

## Import And Syntax Sanity

```sh
./scripts/smoke/check-imports.sh
```

## Minimal Test Hooks

```sh
python -m unittest discover -s tests -p "test_*.py"
```

Do not claim full correctness from these checks alone.
