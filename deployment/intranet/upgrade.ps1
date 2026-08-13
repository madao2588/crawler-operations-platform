. (Join-Path $PSScriptRoot "_common.ps1")

Assert-DeploymentFiles
Assert-DockerReady

$database = Join-Path $RuntimeRoot "data\data.db"
if (Test-Path -LiteralPath $database) {
  Write-Host "Creating a pre-upgrade backup."
  & (Join-Path $PSScriptRoot "backup.ps1")
  if ($LASTEXITCODE -ne 0) {
    throw "Pre-upgrade backup failed. Upgrade was not started."
  }
}

& (Join-Path $PSScriptRoot "deploy.ps1")
if ($LASTEXITCODE -ne 0) {
  throw "Upgrade deployment failed. Existing runtime data was preserved."
}
