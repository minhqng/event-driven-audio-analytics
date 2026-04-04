Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath (Resolve-Path (Join-Path $PSScriptRoot "../.."))

function Assert-LastExitCode {
    param(
        [string]$Context
    )

    if ($LASTEXITCODE -ne 0) {
        throw "$Context failed with exit code $LASTEXITCODE."
    }
}

Write-Host "Building pytest image..."
docker compose build pytest
Assert-LastExitCode "docker compose build pytest"

if ($args.Count -gt 0) {
    Write-Host "Running pytest with explicit arguments..."
    docker compose run --rm pytest @args
    Assert-LastExitCode "docker compose run pytest"
}
else {
    Write-Host "Running full pytest suite..."
    docker compose run --rm pytest
    Assert-LastExitCode "docker compose run pytest"
}
