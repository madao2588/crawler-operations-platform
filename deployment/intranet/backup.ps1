. (Join-Path $PSScriptRoot "_common.ps1")

Assert-DeploymentFiles
Assert-DockerReady

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$fileName = "manual.$timestamp.db"
$containerPath = "/app/server/backups/$fileName"
$pythonCode = "import sqlite3,sys; source=sqlite3.connect('file:/app/server/runtime-data/data.db?mode=ro', uri=True); target=sqlite3.connect(sys.argv[1]); source.backup(target); result=target.execute('PRAGMA integrity_check').fetchone()[0]; target.close(); source.close(); raise SystemExit(0 if result == 'ok' else 2)"

Invoke-Compose -Arguments @("exec", "-T", "api", "python", "-c", $pythonCode, $containerPath)
$hostPath = Join-Path $RuntimeRoot "backups\$fileName"
if (!(Test-Path -LiteralPath $hostPath)) {
  throw "Backup command completed without creating $hostPath"
}
Write-Host "Consistent SQLite backup created: $hostPath"
