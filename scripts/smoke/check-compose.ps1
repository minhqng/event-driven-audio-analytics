Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

docker compose config | Out-Null
Write-Host "Compose config rendered successfully."
