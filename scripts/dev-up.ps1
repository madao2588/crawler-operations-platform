param(
  [int]$BackendPort = 8000,
  [int]$FrontendPort = 8093,
  [string]$FrontendMode = 'react'
)

$ErrorActionPreference = "Stop"
$LogFileClearAttempts = 20

function Get-ListeningPids([int]$Port) {
  $matches = netstat -ano -p tcp | Select-String "LISTENING\s+\d+$" | Select-String ":$Port\s"
  $pids = @()
  foreach ($line in $matches) {
    $parts = ($line.ToString().Trim() -split "\s+")
    if ($parts.Length -gt 0) {
      $portPid = $parts[-1]
      if ($portPid -match "^\d+$" -and $portPid -ne "0") {
        $pids += [int]$portPid
      }
    }
  }
  return $pids | Select-Object -Unique
}

function Stop-PortProcesses([int]$Port) {
  $pids = Get-ListeningPids -Port $Port
  foreach ($portPid in $pids) {
    taskkill /PID $portPid /F | Out-Null
    if ($LASTEXITCODE -eq 0) {
      Write-Host "Stopped PID $portPid on port $Port"
    } else {
      Write-Warning "Failed to stop PID $portPid on port ${Port}."
    }
  }
}

function Assert-PortFree([int]$Port) {
  $pids = Get-ListeningPids -Port $Port
  if ($pids.Count -gt 0) {
    throw "Port $Port is still in use by PID(s): $($pids -join ', ')"
  }
}

function Get-LanIPv4Address {
  try {
    $configuration = Get-NetIPConfiguration -ErrorAction Stop |
      Where-Object {
        $_.NetAdapter.Status -eq "Up" -and
        $null -ne $_.IPv4DefaultGateway -and
        $null -ne $_.IPv4Address
      } |
      Select-Object -First 1

    if ($null -ne $configuration) {
      $address = $configuration.IPv4Address | Select-Object -First 1
      if ($null -ne $address -and -not [string]::IsNullOrWhiteSpace($address.IPAddress)) {
        return $address.IPAddress
      }
    }
  } catch {
    return $null
  }

  return $null
}

function Wait-ForHttpOk([string]$Url, [int]$TimeoutSeconds = 30) {
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    try {
      $response = Invoke-WebRequest -UseBasicParsing $Url -TimeoutSec 3
      if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) {
        return
      }
    } catch {
      Start-Sleep -Milliseconds 500
    }
  }

  throw "Timed out waiting for HTTP endpoint: $Url"
}

function Stop-LaunchedProcess([System.Diagnostics.Process]$Process) {
  if ($null -eq $Process) {
    return
  }

  try {
    if (!$Process.HasExited) {
      taskkill /PID $Process.Id /T /F | Out-Null
    }
  } catch {
    Write-Warning "Failed to stop launched process PID $($Process.Id): $($_.Exception.Message)"
  }
}

function Write-LogTail([string]$Label, [string]$Path, [int]$Tail = 30) {
  if (!(Test-Path -LiteralPath $Path)) {
    return
  }

  $lines = Get-Content -LiteralPath $Path -Tail $Tail -ErrorAction SilentlyContinue
  if ($lines.Count -eq 0) {
    return
  }

  Write-Host ""
  Write-Host "$Label ($Path):"
  $lines | ForEach-Object { Write-Host $_ }
}

function Prepare-LogFile([string]$Path) {
  if (!(Test-Path $Path)) {
    New-Item -ItemType File -Path $Path | Out-Null
    return $Path
  }

  for ($attempt = 1; $attempt -le $LogFileClearAttempts; $attempt++) {
    try {
      Clear-Content -Path $Path -ErrorAction Stop
      return $Path
    } catch {
      if ($attempt -lt $LogFileClearAttempts) {
        Start-Sleep -Milliseconds 150
      }
    }
  }

  $directory = Split-Path -Parent $Path
  $name = [System.IO.Path]::GetFileNameWithoutExtension($Path)
  $extension = [System.IO.Path]::GetExtension($Path)
  $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
  $fallbackPath = Join-Path $directory "$name.$timestamp$extension"
  New-Item -ItemType File -Path $fallbackPath -Force | Out-Null
  Write-Warning "Log file is busy: $Path. Using fallback log file: $fallbackPath"
  return $fallbackPath
}

$crawlerRoot = Split-Path $PSScriptRoot -Parent
$serverDir = Join-Path $crawlerRoot "server"
$frontendDir = Join-Path $crawlerRoot "frontend"
$reactFrontendDir = Join-Path $crawlerRoot "web"
$pythonWrapper = Join-Path $PSScriptRoot "pythonw.ps1"
$frontendBuildScript = Join-Path $PSScriptRoot "frontend-build.ps1"
$reactFrontendLog = Join-Path $crawlerRoot "frontend-react.log"
$reactFrontendErrLog = Join-Path $crawlerRoot "frontend-react.err.log"
$frontendBuildDir = Join-Path $frontendDir "build\web"
$backendLog = Join-Path $crawlerRoot "backend.log"
$backendErrLog = Join-Path $crawlerRoot "backend.err.log"
$frontendLog = Join-Path $crawlerRoot "frontend.log"
$frontendErrLog = Join-Path $crawlerRoot "frontend.err.log"

if (!(Test-Path $pythonWrapper)) {
  throw "Missing Python wrapper: $pythonWrapper"
}

if (!(Test-Path $frontendBuildScript)) {
  throw "Missing frontend build script: $frontendBuildScript"
}

$useFlutterFrontend = $FrontendMode.ToLowerInvariant() -eq "flutter"
$useReactFrontend = $FrontendMode.ToLowerInvariant() -eq "react"

if (-not $useFlutterFrontend -and -not $useReactFrontend) {
  throw "Invalid FrontendMode '$FrontendMode'. Supported values: flutter, react"
}

if ($useReactFrontend -and !(Test-Path $reactFrontendDir)) {
  throw "Missing React frontend directory: $reactFrontendDir"
}

$frontendApiBaseUrl = if ([string]::IsNullOrWhiteSpace($env:API_BASE_URL)) {
  "http://127.0.0.1:$BackendPort"
} else {
  $env:API_BASE_URL
}

if ([string]::IsNullOrWhiteSpace($frontendApiBaseUrl)) {
  throw "Set API_BASE_URL or ensure backend is reachable"
}

Write-Host "Cleaning existing listeners..."
Stop-PortProcesses -Port $BackendPort
Stop-PortProcesses -Port $FrontendPort
Assert-PortFree -Port $BackendPort
Assert-PortFree -Port $FrontendPort

if ($useFlutterFrontend) {
  if (!(Test-Path $frontendBuildScript)) {
    throw "Missing frontend build script: $frontendBuildScript"
  }

  Write-Host "Building stable flutter web assets..."
  & powershell -NoProfile -ExecutionPolicy Bypass -File $frontendBuildScript -ApiBaseUrl $frontendApiBaseUrl
  if ($LASTEXITCODE -ne 0) {
    throw "Frontend build failed with exit code $LASTEXITCODE."
  }
}

if ($useFlutterFrontend) {
  $frontendIndex = Join-Path $frontendBuildDir "index.html"
  if (!(Test-Path $frontendIndex)) {
    throw "Flutter build completed without creating $frontendIndex"
  }
}

$backendLog = Prepare-LogFile -Path $backendLog
$backendErrLog = Prepare-LogFile -Path $backendErrLog
$frontendLog = Prepare-LogFile -Path $frontendLog
$frontendErrLog = Prepare-LogFile -Path $frontendErrLog
$reactFrontendLog = Prepare-LogFile -Path $reactFrontendLog
$reactFrontendErrLog = Prepare-LogFile -Path $reactFrontendErrLog

$backendProc = $null
$frontendProc = $null

try {
  Write-Host "Starting backend on http://127.0.0.1:$BackendPort ..."
  $backendCommand = "Set-Location '$serverDir'; & '$pythonWrapper' -m uvicorn main:app --host 127.0.0.1 --port $BackendPort"
  $backendProc = Start-Process -FilePath "powershell" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $backendCommand) -WindowStyle Hidden -PassThru -RedirectStandardOutput $backendLog -RedirectStandardError $backendErrLog

  Wait-ForHttpOk -Url "http://127.0.0.1:$BackendPort/health"

  Write-Host "Starting frontend ($FrontendMode) on http://127.0.0.1:$FrontendPort ..."
  if ($useFlutterFrontend) {
    $frontendCommand = "Set-Location '$frontendDir'; & '$pythonWrapper' -m http.server $FrontendPort --bind 127.0.0.1 --directory '$frontendBuildDir'"
    $frontendProc = Start-Process -FilePath "powershell" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $frontendCommand) -WindowStyle Hidden -PassThru -RedirectStandardOutput $frontendLog -RedirectStandardError $frontendErrLog
  } else {
    $reactCommand = "Set-Location '$reactFrontendDir'; `$env:API_BASE_URL = '$frontendApiBaseUrl'; npm run dev -- --host 0.0.0.0 --port $FrontendPort"
    $frontendProc = Start-Process -FilePath "powershell" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $reactCommand) -WindowStyle Hidden -PassThru -RedirectStandardOutput $reactFrontendLog -RedirectStandardError $reactFrontendErrLog
  }

  Wait-ForHttpOk -Url "http://127.0.0.1:$FrontendPort/" -TimeoutSeconds 60

  Write-Host ""
  Write-Host "Backend PID:  $($backendProc.Id)"
  Write-Host "Frontend PID: $($frontendProc.Id)"
  Write-Host "Backend URL:  http://127.0.0.1:$BackendPort"
  Write-Host "Frontend URL: http://127.0.0.1:$FrontendPort"
  if ($useReactFrontend) {
    $lanAddress = Get-LanIPv4Address
    if ([string]::IsNullOrWhiteSpace($lanAddress)) {
      Write-Host "LAN URL:      unavailable (open http://<this-computer-ip>:$FrontendPort)"
    } else {
      Write-Host "LAN URL:      http://${lanAddress}:$FrontendPort"
    }
  }
  Write-Host "Frontend API: $frontendApiBaseUrl"
  Write-Host "Frontend Mode: $FrontendMode"
  Write-Host "Backend Log:  $backendLog"
  if ($useFlutterFrontend) {
    Write-Host "Frontend Log: $frontendLog"
  } else {
    Write-Host "Frontend Log: $reactFrontendLog"
  }
} catch {
  Write-Warning "Combined startup failed: $($_.Exception.Message)"
  Stop-LaunchedProcess -Process $frontendProc
  Stop-LaunchedProcess -Process $backendProc
  Stop-PortProcesses -Port $BackendPort
  Stop-PortProcesses -Port $FrontendPort
  Write-LogTail -Label "Backend error log" -Path $backendErrLog
  Write-LogTail -Label "Backend output log" -Path $backendLog
  Write-LogTail -Label "Frontend error log" -Path $(if ($useFlutterFrontend) { $frontendErrLog } else { $reactFrontendErrLog })
  Write-LogTail -Label "Frontend output log" -Path $(if ($useFlutterFrontend) { $frontendLog } else { $reactFrontendLog })
  throw
}
