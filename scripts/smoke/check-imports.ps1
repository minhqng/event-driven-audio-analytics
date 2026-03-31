Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath (Resolve-Path (Join-Path $PSScriptRoot "../.."))

python -m compileall src tests | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "python -m compileall failed with exit code $LASTEXITCODE."
}

Write-Host "Import and syntax compilation checks passed."
