. (Join-Path $PSScriptRoot "_common.ps1")

Import-LegacyDeploymentState
Initialize-Environment
Sync-ReleaseVersion
Sync-DetectedOutboundProxy
Assert-DeploymentFiles
Assert-DockerReady
Write-Stage "Verifying release package integrity"
& (Join-Path $PSScriptRoot "verify.ps1")
Write-Stage "Preparing persistent runtime data"
Initialize-Runtime
Invoke-Compose -Arguments @("config", "--quiet")

try {
  $releaseVersion = Get-EnvValue "RELEASE_VERSION"
  $requiredImages = @(
    "new-drug-intelligence-api:$releaseVersion",
    "new-drug-intelligence-web:$releaseVersion"
  )
  $missingImages = @()
  foreach ($image in $requiredImages) {
    if (!(Test-DockerImageExists -Image $image)) {
      $missingImages += $image
    }
  }

  if ($missingImages.Count -gt 0) {
    $offlineImages = Join-Path $DeploymentRoot "images\production-images.tar"
    if (!(Test-Path -LiteralPath $offlineImages -PathType Leaf)) {
      throw "Packaged production images are missing: $offlineImages. Re-copy the complete release package; do not run docker compose --build on the intranet server."
    }
    Write-Stage "Loading packaged production images (first start can take several minutes)"
    & docker load --quiet --input $offlineImages
    if ($LASTEXITCODE -ne 0) {
      throw "Failed to load packaged Docker images."
    }
  } else {
    Write-Stage "Packaged production images already exist; skipping image import."
  }

  foreach ($image in $requiredImages) {
    if (!(Test-DockerImageExists -Image $image)) {
      throw "Packaged image tag is missing after import: $image"
    }
  }
  Write-Stage "Starting application containers in offline mode (no build, no pull)"
  Invoke-Compose -Arguments @("up", "-d", "--pull", "never", "--no-build", "--remove-orphans")

  Write-Stage "Waiting for the web application and database health check"
  $healthUrl = Wait-ForHealthyService -TimeoutSeconds 300
  Invoke-Compose -Arguments @("ps")
  $port = Get-EnvValue "INTRANET_PORT" "8093"
  Write-Host ""
  Write-Host "Deployment succeeded."
  Write-Host "Health: $healthUrl"
  Write-Host "Open from the intranet: http://<server-ip>:$port/"
  Write-Host "For a first deployment, read FIRST-LOGIN.txt for the initial account."
} catch {
  Write-Warning $_.Exception.Message
  try { Invoke-Compose -Arguments @("logs", "--tail", "120", "api", "web") } catch { }
  throw
}
