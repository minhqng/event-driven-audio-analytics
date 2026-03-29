# Lightweight Validation

Use lightweight checks that match the maturity of this scaffold:

## Tree And Script Presence

```sh
bash ./scripts/smoke/check-tree.sh
```

## Compose Config Sanity

```sh
bash ./scripts/smoke/check-compose.sh
```

## Import And Syntax Sanity

```sh
bash ./scripts/smoke/check-imports.sh
```

## Minimal Test Hooks

```sh
python -m unittest discover -s tests -p "test_*.py"
```

## Legacy PowerShell Wrappers

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-tree.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-compose.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-imports.ps1
```

Do not claim full correctness from these checks alone.
