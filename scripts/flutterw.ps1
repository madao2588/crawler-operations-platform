$ErrorActionPreference = "Stop"

$crawlerRoot = Split-Path $PSScriptRoot -Parent
$workspaceRoot = Split-Path $crawlerRoot -Parent
$defaultLocalFlutterRoot = Join-Path $workspaceRoot ".local-tools\flutter-sdk"

function Get-FlutterRootFromCommand {
  $command = Get-Command flutter -ErrorAction SilentlyContinue
  if ($null -eq $command) {
    return $null
  }

  $binDir = Split-Path $command.Source -Parent
  return Split-Path $binDir -Parent
}

function Test-FlutterCacheWritable([string]$flutterRoot) {
  $cacheDir = Join-Path $flutterRoot "bin\cache"
  if (!(Test-Path $cacheDir)) {
    return $false
  }

  $probe = Join-Path $cacheDir "codex-write-test.tmp"
  try {
    Set-Content -LiteralPath $probe -Value "ok" -NoNewline -ErrorAction Stop
    Remove-Item -LiteralPath $probe -Force -ErrorAction Stop
    return $true
  } catch {
    return $false
  }
}

function Assert-PathWithinWorkspace([string]$targetPath) {
  $workspacePath = [System.IO.Path]::GetFullPath($workspaceRoot)
  $resolvedTargetPath = [System.IO.Path]::GetFullPath($targetPath)
  if (!$resolvedTargetPath.StartsWith($workspacePath, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to manage Flutter SDK outside workspace root: $resolvedTargetPath"
  }
}

function Ensure-LocalFlutterSdk([string]$sourceFlutterRoot, [string]$targetFlutterRoot) {
  Assert-PathWithinWorkspace $targetFlutterRoot

  $sourceFlutterBat = Join-Path $sourceFlutterRoot "bin\flutter.bat"
  if (!(Test-Path $sourceFlutterBat)) {
    throw "Missing source Flutter SDK: $sourceFlutterBat"
  }

  $targetFlutterBat = Join-Path $targetFlutterRoot "bin\flutter.bat"
  if (Test-Path $targetFlutterBat) {
    return $targetFlutterRoot
  }

  New-Item -ItemType Directory -Force -Path (Split-Path $targetFlutterRoot -Parent) | Out-Null

  Write-Host "Copying Flutter SDK to writable workspace path:"
  Write-Host "  Source: $sourceFlutterRoot"
  Write-Host "  Target: $targetFlutterRoot"

  $robocopyArgs = @(
    $sourceFlutterRoot,
    $targetFlutterRoot,
    "/E",
    "/R:2",
    "/W:2",
    "/NFL",
    "/NDL",
    "/NJH",
    "/NJS",
    "/NP"
  )

  & robocopy @robocopyArgs | Out-Host
  $robocopyExitCode = $LASTEXITCODE
  if ($robocopyExitCode -ge 8) {
    throw "robocopy failed with exit code $robocopyExitCode while copying Flutter SDK."
  }

  if (!(Test-Path $targetFlutterBat)) {
    throw "Flutter SDK copy completed without creating $targetFlutterBat"
  }

  return $targetFlutterRoot
}

function Resolve-FlutterRoot {
  if (![string]::IsNullOrWhiteSpace($env:CRAWLER_FLUTTER_ROOT)) {
    $overrideRoot = $env:CRAWLER_FLUTTER_ROOT.Trim()
    $overrideFlutterBat = Join-Path $overrideRoot "bin\flutter.bat"
    if (!(Test-Path $overrideFlutterBat)) {
      throw "CRAWLER_FLUTTER_ROOT does not contain bin\flutter.bat: $overrideFlutterBat"
    }
    return $overrideRoot
  }

  $commandFlutterRoot = Get-FlutterRootFromCommand
  if ($null -eq $commandFlutterRoot) {
    $localFlutterBat = Join-Path $defaultLocalFlutterRoot "bin\flutter.bat"
    if (Test-Path $localFlutterBat) {
      return $defaultLocalFlutterRoot
    }
    throw "Flutter is not available on PATH and no local SDK was found at $defaultLocalFlutterRoot"
  }

  if (Test-FlutterCacheWritable $commandFlutterRoot) {
    return $commandFlutterRoot
  }

  return Ensure-LocalFlutterSdk $commandFlutterRoot $defaultLocalFlutterRoot
}

$flutterRoot = Resolve-FlutterRoot
$flutterBat = Join-Path $flutterRoot "bin\flutter.bat"
$env:PATH = "$(Join-Path $flutterRoot 'bin');$env:PATH"

Write-Host "Using Flutter SDK: $flutterRoot"
& $flutterBat @args
exit $LASTEXITCODE
