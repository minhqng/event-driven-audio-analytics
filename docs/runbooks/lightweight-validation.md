# Lightweight Validation

Use lightweight checks that match the maturity of this scaffold:

## Tree And Script Presence

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-tree.ps1
```

## Compose Config Sanity

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-compose.ps1
```

## Import And Syntax Sanity

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-imports.ps1
```

## Minimal Test Hooks

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

## POSIX Alternatives

```sh
bash ./scripts/smoke/check-tree.sh
bash ./scripts/smoke/check-compose.sh
bash ./scripts/smoke/check-imports.sh
```

Do not claim full correctness from these checks alone.
