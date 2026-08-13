$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$DeploymentRoot = $PSScriptRoot
$ComposeFile = Join-Path $DeploymentRoot "compose.production.yml"
$EnvFile = Join-Path $DeploymentRoot ".env.production"
$InitialEnvFile = Join-Path $DeploymentRoot ".env.production.initial"
$RuntimeRoot = Join-Path $DeploymentRoot "runtime"

function Initialize-Environment {
  if (Test-Path -LiteralPath $EnvFile) {
    return
  }
  if (!(Test-Path -LiteralPath $InitialEnvFile)) {
    throw "Missing initial deployment configuration: $InitialEnvFile"
  }
  Copy-Item -LiteralPath $InitialEnvFile -Destination $EnvFile
  Write-Host "Initialized .env.production. Future upgrades will preserve this file."
}

function Sync-ReleaseVersion {
  $versionFile = Join-Path $DeploymentRoot "VERSION.json"
  if (!(Test-Path -LiteralPath $versionFile)) {
    throw "Release metadata is missing: $versionFile"
  }
  $metadata = Get-Content -LiteralPath $versionFile -Raw -Encoding UTF8 | ConvertFrom-Json
  $releaseVersion = [string]$metadata.release_version
  if ($releaseVersion -notmatch '^[A-Za-z0-9._-]+$') {
    throw "Invalid release version in VERSION.json"
  }

  $lines = @(Get-Content -LiteralPath $EnvFile -Encoding UTF8)
  $updated = $false
  for ($index = 0; $index -lt $lines.Count; $index += 1) {
    if ($lines[$index] -match '^RELEASE_VERSION=') {
      $lines[$index] = "RELEASE_VERSION=$releaseVersion"
      $updated = $true
    }
  }
  if (!$updated) {
    $lines += "RELEASE_VERSION=$releaseVersion"
  }
  $content = ($lines -join [Environment]::NewLine) + [Environment]::NewLine
  [IO.File]::WriteAllText($EnvFile, $content, [Text.UTF8Encoding]::new($false))
}

function Get-EnvValue([string]$Name, [string]$DefaultValue = "") {
  if (!(Test-Path -LiteralPath $EnvFile)) {
    return $DefaultValue
  }
  $line = Get-Content -LiteralPath $EnvFile |
    Where-Object { $_ -match "^$([regex]::Escape($Name))=" } |
    Select-Object -Last 1
  if ($null -eq $line) {
    return $DefaultValue
  }
  return ($line -split "=", 2)[1].Trim()
}

function Assert-DeploymentFiles {
  foreach ($path in @($ComposeFile, $EnvFile)) {
    if (!(Test-Path -LiteralPath $path)) {
      throw "Missing deployment file: $path"
    }
  }
}

function Write-Stage([string]$Message) {
  Write-Host ""
  Write-Host "==> $Message"
}

function Assert-DockerReady {
  $docker = Get-Command docker -ErrorAction SilentlyContinue
  if ($null -eq $docker) {
    throw "Docker is not installed or is not available on PATH. Install Docker Desktop or Docker Engine with Compose v2."
  }
  & docker info --format "{{.ServerVersion}}" *> $null
  if ($LASTEXITCODE -ne 0) {
    throw "Docker is installed but the engine is not running. Start Docker and run this script again."
  }
  & docker compose version *> $null
  if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose v2 is unavailable."
  }
}

function Invoke-Compose {
  param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
  & docker compose --env-file $EnvFile -f $ComposeFile @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "docker compose failed: $($Arguments -join ' ')"
  }
}

function Initialize-Runtime {
  $dataDir = Join-Path $RuntimeRoot "data"
  $storageDir = Join-Path $RuntimeRoot "storage"
  $backupsDir = Join-Path $RuntimeRoot "backups"
  foreach ($path in @($dataDir, $storageDir, $backupsDir)) {
    New-Item -ItemType Directory -Path $path -Force | Out-Null
  }

  $database = Join-Path $dataDir "data.db"
  $seedDatabase = Join-Path $DeploymentRoot "seed\data.db"
  if (!(Test-Path -LiteralPath $database)) {
    if (!(Test-Path -LiteralPath $seedDatabase)) {
      throw "Initial database seed is missing: $seedDatabase"
    }
    Copy-Item -LiteralPath $seedDatabase -Destination $database
    Write-Host "Initialized the production database from the packaged delivery snapshot."
  } else {
    Write-Host "Existing production database preserved: $database"
  }

  $storageMarker = Join-Path $storageDir ".seed-imported"
  $seedStorage = Join-Path $DeploymentRoot "seed\storage"
  if (!(Test-Path -LiteralPath $storageMarker) -and (Test-Path -LiteralPath $seedStorage)) {
    Get-ChildItem -LiteralPath $seedStorage -Force | Copy-Item -Destination $storageDir -Recurse -Force
    New-Item -ItemType File -Path $storageMarker -Force | Out-Null
    Write-Host "Initialized packaged snapshots and task templates."
  }
}

function Get-HealthUrl {
  $bindAddress = Get-EnvValue "INTRANET_BIND_ADDRESS" "0.0.0.0"
  $port = Get-EnvValue "INTRANET_PORT" "8093"
  $hostAddress = if ($bindAddress -eq "0.0.0.0") { "127.0.0.1" } else { $bindAddress }
  return "http://${hostAddress}:${port}/health"
}

function Wait-ForHealthyService([int]$TimeoutSeconds = 240) {
  $healthUrl = Get-HealthUrl
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    try {
      $response = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 8
      if ($response.data.status -eq "ok" -and $response.data.database -eq "ok") {
        return $healthUrl
      }
    } catch {
      Start-Sleep -Seconds 3
    }
  }
  throw "Timed out waiting for service health: $healthUrl"
}
