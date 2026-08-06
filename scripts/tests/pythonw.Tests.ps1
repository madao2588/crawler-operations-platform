$repoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$pythonWrapper = Join-Path $repoRoot "scripts\pythonw.ps1"

Describe "pythonw.ps1" {
  It "falls back to uv when the configured virtualenv Python is broken" {
    $previousPython = $env:CRAWLER_PYTHON_EXE
    try {
      $env:CRAWLER_PYTHON_EXE = Join-Path $TestDrive "missing-python.exe"
      $output = & powershell -NoProfile -ExecutionPolicy Bypass -File $pythonWrapper --version 2>&1
      $exitCode = $LASTEXITCODE
    } finally {
      $env:CRAWLER_PYTHON_EXE = $previousPython
    }

    $exitCode | Should Be 0
    ($output -join "`n") | Should Match "Python 3\.11"
  }
}
