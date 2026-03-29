Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

docker compose config | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "docker compose config failed with exit code $LASTEXITCODE."
}

Write-Host "Compose config rendered successfully."
