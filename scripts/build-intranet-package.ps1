$ErrorActionPreference = "Stop"

$pythonLauncher = Join-Path $PSScriptRoot "pythonw.ps1"
$builder = Join-Path $PSScriptRoot "build_intranet_package.py"

if (!(Test-Path -LiteralPath $pythonLauncher)) {
  throw "Python launcher is missing: $pythonLauncher"
}

& $pythonLauncher $builder @args
if ($LASTEXITCODE -ne 0) {
  throw "Intranet package build failed with exit code $LASTEXITCODE"
}
