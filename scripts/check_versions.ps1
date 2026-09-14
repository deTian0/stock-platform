<#
.SYNOPSIS
  Verify root VERSION matches all package pyproject / __version__ fields.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot '..')
Set-Location $root

$ver = (Get-Content (Join-Path $root 'VERSION') -Raw).Trim()
if ($ver -notmatch '^\d+\.\d+\.\d+') {
  throw "VERSION not semver-ish: $ver"
}

$failed = $false
$pyprojects = @(
  'packages/providers/pyproject.toml',
  'packages/research/pyproject.toml',
  'packages/agents/pyproject.toml',
  'packages/execution/pyproject.toml',
  'apps/workbench/pyproject.toml'
)
$inits = @(
  'packages/providers/src/stock_platform_providers/__init__.py',
  'packages/research/src/stock_platform_research/__init__.py',
  'packages/agents/src/stock_platform_agents/__init__.py',
  'packages/execution/src/stock_platform_execution/__init__.py',
  'apps/workbench/src/stock_platform_workbench/__init__.py'
)

foreach ($rel in $pyprojects) {
  $text = Get-Content (Join-Path $root $rel) -Raw
  if ($text -notmatch '(?m)^version\s*=\s*"([^"]+)"') {
    Write-Error "No version= in $rel"
    $failed = $true
    continue
  }
  $pkg = $Matches[1]
  if ($pkg -ne $ver) {
    Write-Error "Version mismatch $rel : $pkg != VERSION $ver"
    $failed = $true
  }
}

foreach ($rel in $inits) {
  $text = Get-Content (Join-Path $root $rel) -Raw
  if ($text -notmatch '__version__\s*=\s*"([^"]+)"') {
    Write-Error "No __version__ in $rel"
    $failed = $true
    continue
  }
  $pkg = $Matches[1]
  if ($pkg -ne $ver) {
    Write-Error "__version__ mismatch $rel : $pkg != VERSION $ver"
    $failed = $true
  }
}

if ($failed) {
  throw 'version check failed'
}

Write-Host "version check OK (VERSION=$ver, packages=$($pyprojects.Count))"
