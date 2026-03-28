Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$bootstrapServer = if ($env:KAFKA_BOOTSTRAP_SERVERS) {
    $env:KAFKA_BOOTSTRAP_SERVERS
} else {
    "localhost:29092"
}

$kafkaTopics = "/opt/bitnami/kafka/bin/kafka-topics.sh"
$topics = @(
    "audio.metadata",
    "audio.segment.ready",
    "audio.features",
    "system.metrics"
)

foreach ($topic in $topics) {
    docker compose exec -T kafka $kafkaTopics `
        --bootstrap-server $bootstrapServer `
        --create `
        --if-not-exists `
        --topic $topic `
        --partitions 1 `
        --replication-factor 1 | Out-Null
}

Write-Host "Kafka topics ensured."
