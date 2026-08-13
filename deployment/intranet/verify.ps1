. (Join-Path $PSScriptRoot "_common.ps1")

$manifest = Join-Path $DeploymentRoot "SHA256SUMS.txt"
if (!(Test-Path -LiteralPath $manifest)) {
  throw "Package manifest is missing: $manifest"
}

$checked = 0
foreach ($line in Get-Content -LiteralPath $manifest -Encoding UTF8) {
  if ([string]::IsNullOrWhiteSpace($line)) {
    continue
  }
  if ($line -notmatch '^([0-9a-fA-F]{64})  (.+)$') {
    throw "Invalid manifest entry: $line"
  }
  $expected = $matches[1].ToUpperInvariant()
  $relative = $matches[2].Replace('/', [IO.Path]::DirectorySeparatorChar)
  $path = Join-Path $DeploymentRoot $relative
  if (!(Test-Path -LiteralPath $path -PathType Leaf)) {
    throw "Package file is missing: $relative"
  }
  $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
  if ($actual -ne $expected) {
    throw "Package file checksum mismatch: $relative"
  }
  $checked += 1
}

Write-Host "Package verification succeeded: $checked files checked."
