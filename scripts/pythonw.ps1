param(
  [switch]$IncludeDevDependencies,
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$PythonArgs
)

$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

$crawlerRoot = Split-Path $PSScriptRoot -Parent
$workspaceRoot = Split-Path $crawlerRoot -Parent
$serverDir = Join-Path $crawlerRoot "server"
$requirements = Join-Path $serverDir "requirements.txt"
$devRequirements = Join-Path $serverDir "requirements-dev.txt"

$pythonExe = if ([string]::IsNullOrWhiteSpace($env:CRAWLER_PYTHON_EXE)) {
  Join-Path $workspaceRoot ".venv\Scripts\python.exe"
} else {
  $env:CRAWLER_PYTHON_EXE
}

$pythonWorks = $false
if (Test-Path -LiteralPath $pythonExe) {
  try {
    & $pythonExe -c "import sys; raise SystemExit(0)" *> $null
    $pythonWorks = $LASTEXITCODE -eq 0
  } catch {
    $pythonWorks = $false
  }
}

if ($pythonWorks) {
  & $pythonExe @PythonArgs
  exit $LASTEXITCODE
}

$uv = Get-Command uv -ErrorAction SilentlyContinue
if ($null -eq $uv) {
  throw "No working Python found at '$pythonExe', and uv is not available on PATH."
}

Write-Warning "Python environment is unavailable at '$pythonExe'; using an isolated uv Python 3.11 environment."
$uvArgs = @(
  "run",
  "--isolated",
  "--python",
  "3.11",
  "--with-requirements",
  $requirements
)
if ($IncludeDevDependencies) {
  $uvArgs += @("--with-requirements", $devRequirements)
}
$uvArgs += "python"
$uvArgs += $PythonArgs

& $uv.Source @uvArgs
exit $LASTEXITCODE
