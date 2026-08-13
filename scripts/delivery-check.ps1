param(
  [switch]$SkipHttp
)

$ErrorActionPreference = "Stop"
$scriptArgs = @((Join-Path $PSScriptRoot "delivery_check.py"))
if ($SkipHttp) {
  $scriptArgs += "--skip-http"
}

& (Join-Path $PSScriptRoot "pythonw.ps1") @scriptArgs
exit $LASTEXITCODE
