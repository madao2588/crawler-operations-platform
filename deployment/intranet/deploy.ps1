param(
  [switch]$ForceBuild
)

. (Join-Path $PSScriptRoot "_common.ps1")

Initialize-Environment
Sync-ReleaseVersion
Assert-DeploymentFiles
Assert-DockerReady
Write-Stage "Preparing persistent runtime data"
Initialize-Runtime
Invoke-Compose -Arguments @("config", "--quiet")

$offlineImages = Join-Path $DeploymentRoot "images\production-images.tar"
try {
  if ((Test-Path -LiteralPath $offlineImages) -and !$ForceBuild) {
    Write-Stage "Loading packaged production images (this can take several minutes)"
    & docker load --quiet --input $offlineImages
    if ($LASTEXITCODE -ne 0) {
      throw "Failed to load packaged Docker images."
    }
    Write-Stage "Starting application containers"
    Invoke-Compose -Arguments @("up", "-d", "--no-build", "--remove-orphans")
  } else {
    Write-Stage "Building production images from source (internet access may be required)"
    Invoke-Compose -Arguments @("build", "--pull")
    Write-Stage "Starting application containers"
    Invoke-Compose -Arguments @("up", "-d", "--remove-orphans")
  }

  Write-Stage "Waiting for the web application and database health check"
  $healthUrl = Wait-ForHealthyService -TimeoutSeconds 300
  Invoke-Compose -Arguments @("ps")
  $port = Get-EnvValue "INTRANET_PORT" "8093"
  Write-Host ""
  Write-Host "Deployment succeeded."
  Write-Host "Health: $healthUrl"
  Write-Host "Open from the intranet: http://<server-ip>:$port/"
  Write-Host "For a first deployment, read FIRST-LOGIN.txt and change the password after login."
} catch {
  Write-Warning $_.Exception.Message
  try { Invoke-Compose -Arguments @("logs", "--tail", "120", "api", "web") } catch { }
  throw
}
