Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

python -m compileall src tests | Out-Null
Write-Host "Import and syntax compilation checks passed."
