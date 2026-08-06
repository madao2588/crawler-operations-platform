param(
  [int]$BackendPort = 8000,
  [int]$FrontendPort = 8093
)

$ErrorActionPreference = "Stop"

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
  if ($pids.Count -eq 0) {
    Write-Host "No LISTENING process found on port $Port"
    return
  }
  foreach ($portPid in $pids) {
    taskkill /PID $portPid /F | Out-Null
    if ($LASTEXITCODE -eq 0) {
      Write-Host "Stopped PID $portPid on port $Port"
    } else {
      Write-Warning "Failed to stop PID $portPid on port ${Port}."
    }
  }
}

Write-Host "Stopping backend/frontend listeners..."
Stop-PortProcesses -Port $BackendPort
Stop-PortProcesses -Port $FrontendPort
Write-Host "Done."
