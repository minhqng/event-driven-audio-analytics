param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$TopicName,
    [Parameter(Position = 1)]
    [int]$MaxMessages = 5
)

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

$bootstrapServer = if ($env:KAFKA_BOOTSTRAP_SERVERS) {
    $env:KAFKA_BOOTSTRAP_SERVERS
} else {
    "kafka:29092"
}

docker compose exec -T kafka /opt/bitnami/kafka/bin/kafka-console-consumer.sh `
    --bootstrap-server $bootstrapServer `
    --topic $TopicName `
    --from-beginning `
    --max-messages $MaxMessages `
    --timeout-ms 10000 `
    --property print.key=true `
    --property key.separator='|'
Assert-LastExitCode "Observing topic $TopicName"
