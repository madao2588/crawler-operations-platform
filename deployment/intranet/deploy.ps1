. (Join-Path $PSScriptRoot "_common.ps1")

Initialize-Environment
Sync-ReleaseVersion
Assert-DeploymentFiles
Assert-DockerReady
Write-Stage "Verifying release package integrity"
& (Join-Path $PSScriptRoot "verify.ps1")
if ($LASTEXITCODE -ne 0) {
  throw "Package verification failed. Re-copy the complete release package before deploying."
}
Write-Stage "Preparing persistent runtime data"
Initialize-Runtime
Invoke-Compose -Arguments @("config", "--quiet")

$offlineImages = Join-Path $DeploymentRoot "images\production-images.tar"
try {
  if (!(Test-Path -LiteralPath $offlineImages -PathType Leaf)) {
    throw "Packaged production images are missing: $offlineImages. Re-copy the complete release package; do not run docker compose --build on the intranet server."
  }
  Write-Stage "Loading packaged production images (this can take several minutes)"
  & docker load --quiet --input $offlineImages
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to load packaged Docker images."
  }
  $releaseVersion = Get-EnvValue "RELEASE_VERSION"
  foreach ($image in @(
    "new-drug-intelligence-api:$releaseVersion",
    "new-drug-intelligence-web:$releaseVersion"
  )) {
    & docker image inspect $image *> $null
    if ($LASTEXITCODE -ne 0) {
      throw "Packaged image tag is missing after import: $image"
    }
  }
  Write-Stage "Starting application containers without rebuilding"
  Invoke-Compose -Arguments @("up", "-d", "--no-build", "--remove-orphans")

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
