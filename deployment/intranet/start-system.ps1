param(
  [switch]$NoBrowser,
  [switch]$AutoStart
)

. (Join-Path $PSScriptRoot "_common.ps1")

$transcriptStarted = $false
$exitCode = 0
Import-LegacyDeploymentState
if ($AutoStart) {
  try {
    New-Item -ItemType Directory -Path $RuntimeRoot -Force | Out-Null
    Start-Transcript -Path (Join-Path $RuntimeRoot "launcher-autostart.log") -Append | Out-Null
    $transcriptStarted = $true
  } catch {
    Write-Warning "Automatic-start log could not be opened: $($_.Exception.Message)"
  }
}

try {
  Write-Stage "Starting New Drug Intelligence Platform"
  Assert-DockerReady
  & (Join-Path $PSScriptRoot "deploy.ps1")

  $port = Get-EnvValue "INTRANET_PORT" "8093"
  $applicationUrl = "http://127.0.0.1:$port/"
  Write-Host ""
  Write-Host "Application is ready: $applicationUrl"
  if (!$AutoStart -and $env:CRAWLER_SKIP_AUTOSTART_REGISTRATION -ne "true") {
    try {
      Enable-AutomaticStartup
    } catch {
      Write-Warning "Automatic startup could not be enabled: $($_.Exception.Message)"
    }
  }
  if (!$NoBrowser) {
    try {
      Start-Process $applicationUrl
    } catch {
      Write-Warning "The application started successfully, but the browser could not be opened automatically. Open $applicationUrl manually."
    }
  }
} catch {
  Write-Host ""
  Write-Error "Startup failed: $($_.Exception.Message)"
  $exitCode = 1
} finally {
  if ($transcriptStarted) {
    Stop-Transcript | Out-Null
  }
}

exit $exitCode
