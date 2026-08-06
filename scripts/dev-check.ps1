param()

$ErrorActionPreference = "Stop"

$crawlerRoot = Split-Path $PSScriptRoot -Parent
$serverDir = Join-Path $crawlerRoot "server"
$frontendDir = Join-Path $crawlerRoot "frontend"
$reactFrontendDir = Join-Path $crawlerRoot "web"
$pythonWrapper = Join-Path $PSScriptRoot "pythonw.ps1"
$flutterWrapper = Join-Path $PSScriptRoot "flutterw.ps1"

if (!(Test-Path $pythonWrapper)) {
  throw "Missing Python wrapper: $pythonWrapper"
}

if (!(Test-Path $flutterWrapper)) {
  throw "Missing Flutter wrapper: $flutterWrapper"
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
Push-Location $frontendDir
try {
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
  if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
  }

  Write-Host "Running Flutter frontend analyze..."
  & $flutterWrapper analyze
  if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
  }

  Write-Host "Running Flutter frontend tests..."
  & $flutterWrapper test
  exit $LASTEXITCODE
} finally {
  Pop-Location
}
