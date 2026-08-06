param(
  [string]$ApiBaseUrl = $env:API_BASE_URL
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ApiBaseUrl)) {
  throw "Set API_BASE_URL or pass -ApiBaseUrl before building the frontend."
}

$crawlerRoot = Split-Path $PSScriptRoot -Parent
$frontendDir = Join-Path $crawlerRoot "frontend"
$flutterWrapper = Join-Path $PSScriptRoot "flutterw.ps1"

if (!(Test-Path $flutterWrapper)) {
  throw "Missing Flutter wrapper: $flutterWrapper"
}

Push-Location $frontendDir
try {
  & $flutterWrapper pub get
  if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
  }

  & $flutterWrapper build web --release --dart-define=API_BASE_URL=$ApiBaseUrl
  exit $LASTEXITCODE
} finally {
  Pop-Location
}
