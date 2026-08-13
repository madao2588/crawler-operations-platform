. (Join-Path $PSScriptRoot "_common.ps1")

Assert-DeploymentFiles
Assert-DockerReady
Invoke-Compose -Arguments @("ps")

$healthUrl = Get-HealthUrl
try {
  $response = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 10
  $response | ConvertTo-Json -Depth 5
  if ($response.data.status -ne "ok") {
    exit 1
  }
} catch {
  Write-Error "Service health check failed at ${healthUrl}: $($_.Exception.Message)"
  exit 1
}
