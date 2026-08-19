$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$DeploymentRoot = $PSScriptRoot
$PackageRoot = if ((Split-Path $DeploymentRoot -Leaf) -eq "_system") {
  Split-Path $DeploymentRoot -Parent
} else {
  $DeploymentRoot
}
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

function Import-LegacyDeploymentState {
  if ($PackageRoot -eq $DeploymentRoot) {
    return
  }

  $legacyEnv = Join-Path $PackageRoot ".env.production"
  if (!(Test-Path -LiteralPath $EnvFile) -and (Test-Path -LiteralPath $legacyEnv -PathType Leaf)) {
    Copy-Item -LiteralPath $legacyEnv -Destination $EnvFile
    Write-Host "Preserved configuration from the previous flat package layout."
  }

  $legacyRuntime = Join-Path $PackageRoot "runtime"
  if (!(Test-Path -LiteralPath $RuntimeRoot) -and (Test-Path -LiteralPath $legacyRuntime -PathType Container)) {
    Copy-Item -LiteralPath $legacyRuntime -Destination $RuntimeRoot -Recurse
    Write-Host "Preserved runtime data from the previous flat package layout."
  }
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

function Set-EnvValue([string]$Name, [AllowEmptyString()][string]$Value) {
  $lines = if (Test-Path -LiteralPath $EnvFile) {
    @(Get-Content -LiteralPath $EnvFile -Encoding UTF8)
  } else {
    @()
  }
  $pattern = "^$([regex]::Escape($Name))="
  $updated = $false
  for ($index = 0; $index -lt $lines.Count; $index += 1) {
    if ($lines[$index] -match $pattern) {
      $lines[$index] = "$Name=$Value"
      $updated = $true
    }
  }
  if (!$updated) {
    $lines += "$Name=$Value"
  }
  $content = ($lines -join [Environment]::NewLine) + [Environment]::NewLine
  [IO.File]::WriteAllText($EnvFile, $content, [Text.UTF8Encoding]::new($false))
}

function Remove-LegacyTargetProxyBypasses {
  $legacyHosts = @(
    "service.most.gov.cn",
    "gdstc.gd.gov.cn",
    "kjj.gz.gov.cn",
    "www.hp.gov.cn",
    "www.hengqin.gov.cn",
    "kjt.hunan.gov.cn",
    "kjj.changsha.gov.cn"
  )
  $configured = Get-EnvValue "CRAWLER_OUTBOUND_NO_PROXY" "localhost,127.0.0.1,::1"
  $entries = [Collections.Generic.List[string]]::new()
  foreach ($entry in $configured.Split(",")) {
    $normalized = $entry.Trim()
    if (!$normalized -or $legacyHosts -contains $normalized.ToLowerInvariant()) {
      continue
    }
    if (!$entries.Contains($normalized)) {
      $entries.Add($normalized)
    }
  }
  foreach ($localHost in @("localhost", "127.0.0.1", "::1")) {
    if (!$entries.Contains($localHost)) {
      $entries.Add($localHost)
    }
  }
  Set-EnvValue "CRAWLER_OUTBOUND_NO_PROXY" ($entries -join ",")
}

function Convert-ToContainerProxyUrl([string]$ProxyUrl) {
  if ([string]::IsNullOrWhiteSpace($ProxyUrl)) {
    return ""
  }
  $candidate = $ProxyUrl.Trim()
  if ($candidate -notmatch '^[A-Za-z][A-Za-z0-9+.-]*://') {
    $candidate = "http://$candidate"
  }
  $uri = $null
  if (![Uri]::TryCreate($candidate, [UriKind]::Absolute, [ref]$uri)) {
    return ""
  }
  if ($uri.Scheme -notin @("http", "https")) {
    return ""
  }
  $builder = [UriBuilder]::new($uri)
  if ($builder.Host -in @("localhost", "127.0.0.1", "::1")) {
    $builder.Host = "host.docker.internal"
  }
  return $builder.Uri.AbsoluteUri.TrimEnd("/")
}

function Get-WindowsSystemProxy {
  if ($env:OS -ne "Windows_NT") {
    return ""
  }
  try {
    $target = [Uri]"https://service.most.gov.cn/"
    $proxy = [Net.WebRequest]::DefaultWebProxy.GetProxy($target)
    if ($null -eq $proxy -or $proxy.AbsoluteUri -eq $target.AbsoluteUri) {
      return ""
    }
    return $proxy.AbsoluteUri
  } catch {
    return ""
  }
}

function Sync-DetectedOutboundProxy(
  [AllowNull()][string]$DetectedProxyUrl = $null
) {
  Remove-LegacyTargetProxyBypasses

  $useSystemProxy = (Get-EnvValue "CRAWLER_USE_SYSTEM_PROXY" "true").ToLowerInvariant()
  if ($useSystemProxy -eq "false") {
    return
  }

  $autoDetectRaw = Get-EnvValue "CRAWLER_AUTO_DETECT_WINDOWS_PROXY" ""
  if ([string]::IsNullOrWhiteSpace($autoDetectRaw)) {
    $existingProxy = Get-EnvValue "CRAWLER_OUTBOUND_PROXY_URL" ""
    $autoDetectRaw = if ([string]::IsNullOrWhiteSpace($existingProxy)) { "true" } else { "false" }
    Set-EnvValue "CRAWLER_AUTO_DETECT_WINDOWS_PROXY" $autoDetectRaw
  }
  if ($autoDetectRaw.ToLowerInvariant() -ne "true") {
    return
  }

  $detected = if ($PSBoundParameters.ContainsKey("DetectedProxyUrl")) {
    $DetectedProxyUrl
  } else {
    Get-WindowsSystemProxy
  }
  $containerProxy = Convert-ToContainerProxyUrl $detected
  Set-EnvValue "CRAWLER_OUTBOUND_PROXY_URL" $containerProxy
  if ($containerProxy) {
    $proxyHost = ([Uri]$containerProxy).Authority
    Write-Host "Detected Windows outbound proxy for containers: $proxyHost"
  } else {
    Write-Host "No Windows outbound proxy detected; collectors will try direct access."
  }
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

function Test-DockerEngineReady {
  & docker info --format "{{.ServerVersion}}" *> $null
  return $LASTEXITCODE -eq 0
}

function Wait-ForDockerEngine([int]$TimeoutSeconds = 180) {
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    if (Test-DockerEngineReady) {
      return $true
    }
    Start-Sleep -Seconds 3
  }
  return $false
}

function Test-DockerImageExists([string]$Image) {
  $imageIds = @(& docker image ls --quiet $Image 2>$null)
  if ($LASTEXITCODE -ne 0) {
    return $false
  }
  return $imageIds.Count -gt 0
}

function Enable-AutomaticStartup(
  [string]$StartupDirectory = [Environment]::GetFolderPath("Startup")
) {
  if ($env:OS -ne "Windows_NT") {
    return
  }
  if ([string]::IsNullOrWhiteSpace($StartupDirectory)) {
    throw "The Windows Startup folder is unavailable for the current user."
  }

  New-Item -ItemType Directory -Path $StartupDirectory -Force | Out-Null
  $powershell = (Get-Command powershell.exe -ErrorAction Stop).Source
  $startScript = Join-Path $DeploymentRoot "start-system.ps1"
  $shortcutPath = Join-Path $StartupDirectory "New Drug Intelligence Platform.lnk"
  $shell = New-Object -ComObject WScript.Shell
  $shortcut = $shell.CreateShortcut($shortcutPath)
  $shortcut.TargetPath = $powershell
  $shortcut.Arguments = "-NoLogo -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$startScript`" -NoBrowser -AutoStart"
  $shortcut.WorkingDirectory = $PackageRoot
  $shortcut.Description = "Start New Drug Intelligence Platform automatically"
  $shortcut.Save()
  Write-Host "Automatic startup enabled for the current Windows user."
}

function Assert-DockerReady {
  $docker = Get-Command docker -ErrorAction SilentlyContinue
  if ($null -eq $docker) {
    throw "Docker is not installed or is not available on PATH. Install Docker Desktop or Docker Engine with Compose v2."
  }

  if (!(Test-DockerEngineReady)) {
    $dockerDesktop = $null
    if ($env:OS -eq "Windows_NT") {
      $candidates = @()
      if ($env:ProgramFiles) {
        $candidates += Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
      }
      if ($env:LOCALAPPDATA) {
        $candidates += Join-Path $env:LOCALAPPDATA "Docker\Docker Desktop.exe"
      }
      $dockerDesktop = $candidates |
        Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
        Select-Object -First 1
    }

    if ($dockerDesktop) {
      Write-Stage "Docker engine is not running; starting Docker Desktop"
      $dockerDesktopProcess = Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue
      if (!$dockerDesktopProcess) {
        Start-Process -FilePath $dockerDesktop -WindowStyle Hidden
      }
      if (!(Wait-ForDockerEngine -TimeoutSeconds 180)) {
        throw "Docker Desktop started but its Linux engine was not ready after 3 minutes. Open Docker Desktop and check its error message."
      }
    } else {
      throw "Docker is installed but the engine is not running. Start Docker Engine and run this launcher again."
    }
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
