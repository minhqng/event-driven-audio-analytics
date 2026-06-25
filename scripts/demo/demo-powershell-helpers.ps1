Set-StrictMode -Version Latest

function Test-DemoTcpPortAvailable {
    param(
        [int]$Port
    )

    if ($null -ne (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue)) {
        $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($null -ne $listener) {
            return $false
        }
    }

    $listener = $null
    try {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Any, $Port)
        $listener.Start()
        return $true
    } catch {
        return $false
    } finally {
        if ($null -ne $listener) {
            $listener.Stop()
        }
    }
}

function Get-DemoComposePublishedPort {
    param(
        [string]$Service,
        [int]$ContainerPort
    )

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $containerId = docker compose ps -q $Service 2>$null | Select-Object -First 1
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    if ([string]::IsNullOrWhiteSpace($containerId)) {
        return $null
    }

    $portKey = "$ContainerPort/tcp"
    $portsJson = docker inspect $containerId --format "{{json .NetworkSettings.Ports}}" 2>$null
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($portsJson)) {
        return $null
    }

    $ports = $portsJson | ConvertFrom-Json
    $portProperty = $ports.PSObject.Properties[$portKey]
    if ($null -eq $portProperty) {
        return $null
    }

    $binding = @($portProperty.Value) | Select-Object -First 1
    if ($null -ne $binding -and -not [string]::IsNullOrWhiteSpace($binding.HostPort)) {
        return [int]$binding.HostPort
    }

    return $null
}

function Set-DemoHostPort {
    param(
        [string]$EnvName,
        [int]$DefaultPort,
        [string]$Service,
        [int]$ContainerPort,
        [int[]]$FallbackPorts
    )

    if (Test-Path "env:$EnvName") {
        return
    }

    $publishedPort = Get-DemoComposePublishedPort -Service $Service -ContainerPort $ContainerPort
    if ($null -ne $publishedPort) {
        Set-Item -Path "env:$EnvName" -Value ([string]$publishedPort)
        return
    }

    if (Test-DemoTcpPortAvailable -Port $DefaultPort) {
        Set-Item -Path "env:$EnvName" -Value ([string]$DefaultPort)
        return
    }

    foreach ($candidatePort in $FallbackPorts) {
        if (Test-DemoTcpPortAvailable -Port $candidatePort) {
            Write-Host "Port $DefaultPort is busy; using $EnvName=$candidatePort for this demo run."
            Set-Item -Path "env:$EnvName" -Value ([string]$candidatePort)
            return
        }
    }

    throw "No available host port found for $EnvName. Tried $DefaultPort and $($FallbackPorts -join ', ')."
}

function Initialize-DemoHostPorts {
    Set-DemoHostPort `
        -EnvName "REVIEW_PORT" `
        -DefaultPort 8080 `
        -Service "review" `
        -ContainerPort 8080 `
        -FallbackPorts (18080..18089)
    Set-DemoHostPort `
        -EnvName "GRAFANA_PORT" `
        -DefaultPort 3000 `
        -Service "grafana" `
        -ContainerPort 3000 `
        -FallbackPorts (13000..13009)
    Set-DemoHostPort `
        -EnvName "TIMESCALEDB_PORT" `
        -DefaultPort 5432 `
        -Service "timescaledb" `
        -ContainerPort 5432 `
        -FallbackPorts (15432..15441)
    Set-DemoHostPort `
        -EnvName "KAFKA_BROKER_PORT" `
        -DefaultPort 9092 `
        -Service "kafka" `
        -ContainerPort 9092 `
        -FallbackPorts (19092..19101)
}
