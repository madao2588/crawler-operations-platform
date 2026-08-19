param(
  [int]$BackendPort = 8000,
  [int]$FrontendPort = 8093
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
$reactFrontendDir = Join-Path $crawlerRoot "web"
$pythonWrapper = Join-Path $PSScriptRoot "pythonw.ps1"
$reactFrontendLog = Join-Path $crawlerRoot "frontend-react.log"
$reactFrontendErrLog = Join-Path $crawlerRoot "frontend-react.err.log"
$backendLog = Join-Path $crawlerRoot "backend.log"
$backendErrLog = Join-Path $crawlerRoot "backend.err.log"

if (!(Test-Path $pythonWrapper)) {
  throw "Missing Python wrapper: $pythonWrapper"
}

if (!(Test-Path $reactFrontendDir)) {
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

Write-Host "Restarting backend while keeping the current frontend available..."
Stop-PortProcesses -Port $BackendPort
Assert-PortFree -Port $BackendPort

$backendLog = Prepare-LogFile -Path $backendLog
$backendErrLog = Prepare-LogFile -Path $backendErrLog

$backendProc = $null
$frontendProc = $null

try {
  Write-Host "Starting backend on http://127.0.0.1:$BackendPort ..."
  $backendCommand = "Set-Location '$serverDir'; & '$pythonWrapper' -m uvicorn main:app --host 127.0.0.1 --port $BackendPort"
  $backendProc = Start-Process -FilePath "powershell" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $backendCommand) -WindowStyle Hidden -PassThru -RedirectStandardOutput $backendLog -RedirectStandardError $backendErrLog

  Wait-ForHttpOk -Url "http://127.0.0.1:$BackendPort/health"

  Write-Host "Backend is healthy. Switching frontend..."
  Stop-PortProcesses -Port $FrontendPort
  Assert-PortFree -Port $FrontendPort
  $reactFrontendLog = Prepare-LogFile -Path $reactFrontendLog
  $reactFrontendErrLog = Prepare-LogFile -Path $reactFrontendErrLog

  Write-Host "Starting React frontend on http://127.0.0.1:$FrontendPort ..."
  $reactCommand = "Set-Location '$reactFrontendDir'; `$env:API_BASE_URL = '$frontendApiBaseUrl'; npm run dev -- --host 0.0.0.0 --port $FrontendPort"
  $frontendProc = Start-Process -FilePath "powershell" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $reactCommand) -WindowStyle Hidden -PassThru -RedirectStandardOutput $reactFrontendLog -RedirectStandardError $reactFrontendErrLog

  Wait-ForHttpOk -Url "http://127.0.0.1:$FrontendPort/" -TimeoutSeconds 60

  Write-Host ""
  Write-Host "Backend PID:  $($backendProc.Id)"
  Write-Host "Frontend PID: $($frontendProc.Id)"
  Write-Host "Backend URL:  http://127.0.0.1:$BackendPort"
  Write-Host "Frontend URL: http://127.0.0.1:$FrontendPort"
  $lanAddress = Get-LanIPv4Address
  if ([string]::IsNullOrWhiteSpace($lanAddress)) {
    Write-Host "LAN URL:      unavailable (open http://<this-computer-ip>:$FrontendPort)"
  } else {
    Write-Host "LAN URL:      http://${lanAddress}:$FrontendPort"
  }
  Write-Host "Frontend API: $frontendApiBaseUrl"
  Write-Host "Backend Log:  $backendLog"
  Write-Host "Frontend Log: $reactFrontendLog"
} catch {
  Write-Warning "Combined startup failed: $($_.Exception.Message)"
  Stop-LaunchedProcess -Process $frontendProc
  Stop-LaunchedProcess -Process $backendProc
  Stop-PortProcesses -Port $BackendPort
  if ($null -ne $frontendProc) {
    Stop-PortProcesses -Port $FrontendPort
  }
  Write-LogTail -Label "Backend error log" -Path $backendErrLog
  Write-LogTail -Label "Backend output log" -Path $backendLog
  Write-LogTail -Label "Frontend error log" -Path $reactFrontendErrLog
  Write-LogTail -Label "Frontend output log" -Path $reactFrontendLog
  throw
}
