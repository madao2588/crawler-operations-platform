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
    taskkill /PID $portPid /T /F | Out-Null
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

function Wait-ForHttpOk([string]$Url, [int]$TimeoutSeconds = 45) {
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

function Prepare-LogFile([string]$Path) {
  if (!(Test-Path -LiteralPath $Path)) {
    New-Item -ItemType File -Path $Path | Out-Null
    return $Path
  }
  for ($attempt = 1; $attempt -le $LogFileClearAttempts; $attempt++) {
    try {
      Clear-Content -LiteralPath $Path -ErrorAction Stop
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

function Write-LogTail([string]$Label, [string]$Path, [int]$Tail = 30) {
  if (!(Test-Path -LiteralPath $Path)) {
    return
  }
  $lines = Get-Content -LiteralPath $Path -Tail $Tail -ErrorAction SilentlyContinue
  if ($lines.Count -gt 0) {
    Write-Host ""
    Write-Host "$Label ($Path):"
    $lines | ForEach-Object { Write-Host $_ }
  }
}

$crawlerRoot = Split-Path $PSScriptRoot -Parent
$serverDir = Join-Path $crawlerRoot "server"
$webDir = Join-Path $crawlerRoot "web"
$pythonWrapper = Join-Path $PSScriptRoot "pythonw.ps1"
$webIndex = Join-Path $webDir "dist\index.html"
$backendLog = Join-Path $crawlerRoot "react-backend.log"
$backendErrLog = Join-Path $crawlerRoot "react-backend.err.log"
$frontendLog = Join-Path $crawlerRoot "react-frontend.log"
$frontendErrLog = Join-Path $crawlerRoot "react-frontend.err.log"

if (!(Test-Path -LiteralPath $pythonWrapper)) {
  throw "Missing Python wrapper: $pythonWrapper"
}
if (!(Test-Path -LiteralPath (Join-Path $webDir "package.json"))) {
  throw "Missing React frontend package: $webDir"
}
if ($null -eq (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
  throw "npm.cmd was not found on PATH."
}

Write-Host "Building React frontend..."
& npm.cmd --prefix $webDir run build
if ($LASTEXITCODE -ne 0) {
  throw "React frontend build failed with exit code $LASTEXITCODE."
}
if (!(Test-Path -LiteralPath $webIndex)) {
  throw "React build completed without creating $webIndex"
}

Write-Host "Cleaning existing listeners..."
Stop-PortProcesses -Port $BackendPort
Stop-PortProcesses -Port $FrontendPort
Assert-PortFree -Port $BackendPort
Assert-PortFree -Port $FrontendPort

$backendLog = Prepare-LogFile -Path $backendLog
$backendErrLog = Prepare-LogFile -Path $backendErrLog
$frontendLog = Prepare-LogFile -Path $frontendLog
$frontendErrLog = Prepare-LogFile -Path $frontendErrLog
$backendProc = $null
$frontendProc = $null

try {
  Write-Host "Starting backend on http://127.0.0.1:$BackendPort ..."
  $backendCommand = "Set-Location '$serverDir'; & '$pythonWrapper' -m uvicorn main:app --host 127.0.0.1 --port $BackendPort"
  $backendProc = Start-Process -FilePath "powershell" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $backendCommand) -WindowStyle Hidden -PassThru -RedirectStandardOutput $backendLog -RedirectStandardError $backendErrLog

  Write-Host "Starting React frontend on http://127.0.0.1:$FrontendPort ..."
  $frontendCommand = "& npm.cmd --prefix '$webDir' run preview -- --host 127.0.0.1 --port $FrontendPort"
  $frontendProc = Start-Process -FilePath "powershell" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $frontendCommand) -WindowStyle Hidden -PassThru -RedirectStandardOutput $frontendLog -RedirectStandardError $frontendErrLog

  Wait-ForHttpOk -Url "http://127.0.0.1:$BackendPort/health"
  Wait-ForHttpOk -Url "http://127.0.0.1:$FrontendPort/" -TimeoutSeconds 60

  Write-Host ""
  Write-Host "React migration mode is running. Flutter files are preserved."
  Write-Host "Backend PID:  $($backendProc.Id)"
  Write-Host "Frontend PID: $($frontendProc.Id)"
  Write-Host "Backend URL:  http://127.0.0.1:$BackendPort"
  Write-Host "Frontend URL: http://127.0.0.1:$FrontendPort"
  Write-Host "Backend Log:  $backendLog"
  Write-Host "Frontend Log: $frontendLog"
} catch {
  Write-Warning "React combined startup failed: $($_.Exception.Message)"
  Stop-LaunchedProcess -Process $frontendProc
  Stop-LaunchedProcess -Process $backendProc
  Stop-PortProcesses -Port $BackendPort
  Stop-PortProcesses -Port $FrontendPort
  Write-LogTail -Label "Backend error log" -Path $backendErrLog
  Write-LogTail -Label "Backend output log" -Path $backendLog
  Write-LogTail -Label "Frontend error log" -Path $frontendErrLog
  Write-LogTail -Label "Frontend output log" -Path $frontendLog
  throw
}
