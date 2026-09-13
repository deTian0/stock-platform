<#
.SYNOPSIS
  Smoke-check required docs exist and internal markdown links resolve.

.DESCRIPTION
  Used locally and in CI (via pwsh). Fails on missing relative targets.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot '..')
Set-Location $root

$required = @(
  'VERSION',
  'README.md',
  'CHANGELOG.md',
  'CONTRIBUTING.md',
  'AGENTS.md',
  'docs/ROADMAP.md',
  'docs/versioning.md',
  'docs/architecture/0001-target-architecture.md',
  'docs/architecture/0002-m0-2-contracts.md',
  'docs/architecture/0003-providers-normalize-symbol.md',
  'docs/architecture/0004-replay-daily-realtime.md',
  'docs/contracts/datasets.md',
  'docs/contracts/capability-matrix.md',
  'docs/contracts/market-strategy.md',
  'scripts/release_tag.ps1',
  'scripts/check_docs.ps1',
  'packages/providers/README.md',
  'packages/providers/pyproject.toml',
  'packages/providers/src/stock_platform_providers/__init__.py',
  'apps/workbench/README.md'
)

$failed = $false
foreach ($rel in $required) {
  $path = Join-Path $root $rel
  if (-not (Test-Path $path)) {
    Write-Error "Missing required file: $rel"
    $failed = $true
  }
}

$ver = (Get-Content (Join-Path $root 'VERSION') -Raw).Trim()
if ($ver -notmatch '^\d+\.\d+\.\d+') {
  Write-Error "VERSION not semver-ish: $ver"
  $failed = $true
}
$changelog = Get-Content (Join-Path $root 'CHANGELOG.md') -Raw
if ($changelog -notmatch [regex]::Escape("[$ver]")) {
  Write-Error "CHANGELOG.md missing section [$ver]"
  $failed = $true
}

# Relative markdown links: ](path) or ](path#anchor) — skip http(s), mailto, anchors-only
$mdFiles = Get-ChildItem -Path $root -Recurse -Filter *.md |
  Where-Object { $_.FullName -notmatch '\\\.git\\' }

$linkPattern = '\[([^\]]+)\]\(([^)]+)\)'
foreach ($file in $mdFiles) {
  $text = Get-Content $file.FullName -Raw
  foreach ($m in [regex]::Matches($text, $linkPattern)) {
    $target = $m.Groups[2].Value.Trim()
    if ($target -match '^(https?://|mailto:|#)') { continue }
    $pathPart = ($target -split '#', 2)[0]
    if ([string]::IsNullOrWhiteSpace($pathPart)) { continue }
    $resolved = [System.IO.Path]::GetFullPath((Join-Path $file.DirectoryName $pathPart))
    if (-not (Test-Path -LiteralPath $resolved)) {
      $relFile = $file.FullName.Substring($root.Path.Length).TrimStart('\', '/')
      Write-Error "Broken link in ${relFile}: ($target)"
      $failed = $true
    }
  }
}

if ($failed) {
  throw 'docs check failed'
}

Write-Host "docs check OK (VERSION=$ver, files=$($required.Count), md=$($mdFiles.Count))"
