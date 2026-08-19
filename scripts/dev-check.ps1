param()

$ErrorActionPreference = "Stop"

$crawlerRoot = Split-Path $PSScriptRoot -Parent
$serverDir = Join-Path $crawlerRoot "server"
$reactFrontendDir = Join-Path $crawlerRoot "web"
$pythonWrapper = Join-Path $PSScriptRoot "pythonw.ps1"

if (!(Test-Path $pythonWrapper)) {
  throw "Missing Python wrapper: $pythonWrapper"
}

if (!(Test-Path (Join-Path $reactFrontendDir "package.json"))) {
  throw "Missing React frontend package: $reactFrontendDir"
}

if ($null -eq (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
  throw "npm.cmd was not found on PATH."
}

Write-Host "Running backend tests..."
Push-Location $serverDir
$previousPythonPath = $env:PYTHONPATH
try {
  $env:PYTHONPATH = "$crawlerRoot;$serverDir"
  if (![string]::IsNullOrWhiteSpace($previousPythonPath)) {
    $env:PYTHONPATH += ";$previousPythonPath"
  }
  & $pythonWrapper -IncludeDevDependencies -m pytest -q tests
  if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
  }
} finally {
  $env:PYTHONPATH = $previousPythonPath
  Pop-Location
}

Write-Host "Running frontend checks..."
Write-Host "Running React frontend typecheck..."
& npm.cmd --prefix $reactFrontendDir run typecheck
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}

Write-Host "Running React frontend tests..."
& npm.cmd --prefix $reactFrontendDir test
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}

Write-Host "Running React frontend build..."
& npm.cmd --prefix $reactFrontendDir run build
exit $LASTEXITCODE
