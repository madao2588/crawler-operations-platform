. (Join-Path $PSScriptRoot "_common.ps1")

Assert-DeploymentFiles
Assert-DockerReady
Invoke-Compose -Arguments @("down")
Write-Host "Services stopped. Runtime data and backups were preserved."
