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
  'docs/architecture/0005-em-get-capability-matrix.md',
  'docs/architecture/0006-workbench-shell.md',
  'docs/architecture/0007-fail-closed-alignment.md',
  'docs/architecture/0008-research-lvrev-pit.md',
  'docs/architecture/0009-agent-plugins.md',
  'docs/architecture/0010-market-strategy-global.md',
  'docs/architecture/0011-paper-execution-safety.md',
  'docs/architecture/0012-v1-product-boundary.md',
  'docs/architecture/0013-astock-http-live.md',
  'docs/architecture/0014-global-http-live.md',
  'docs/architecture/0015-cn-trading-calendar.md',
  'docs/architecture/0016-workbench-minimal-ui.md',
  'docs/architecture/0017-light-debate.md',
  'docs/architecture/0018-us-hk-trading-calendar.md',
  'docs/architecture/0019-multi-market-paper-timing.md',
  'docs/architecture/0020-cn-fund-flow.md',
  'docs/architecture/0021-cn-lhb.md',
  'docs/architecture/0022-cn-unlock.md',
  'docs/architecture/0023-cn-minute.md',
  'docs/architecture/0024-cn-depth5.md',
  'docs/architecture/0025-cn-financial.md',
  'docs/architecture/0026-cn-adj-factor.md',
  'docs/architecture/0027-cn-full-minute.md',
  'docs/architecture/0028-cn-apply-adjust.md',
  'docs/architecture/0029-cn-universe-cross-section.md',
  'docs/architecture/0030-cn-daily-refresh.md',
  'docs/architecture/0031-live-presets-em-circuit.md',
  'docs/architecture/0032-ops-health.md',
  'docs/architecture/0033-recommend-performance.md',
  'docs/architecture/0034-optional-llm-debate.md',
  'docs/architecture/0035-strategy-config-compare.md',
  'docs/architecture/0036-broker-port.md',
  'docs/architecture/0037-ths-sim-broker.md',
  'docs/architecture/0038-ths-sim-gates.md',
  'docs/architecture/0039-phase-d-e2e.md',
  'docs/architecture/0040-daily-universe-readable-reasons.md',
  'docs/architecture/0041-daily-pipeline.md',
  'docs/architecture/0042-sector-fund-flow-news.md',
  'docs/architecture/0043-portfolio-paper-performance.md',
  'docs/architecture/0044-calendar-2028-scheduler.md',
  'docs/ops/refresh-and-fixtures.md',
  'docs/ops/daily-universe.md',
  'docs/ops/daily-pipeline.md',
  'docs/ops/scheduler.md',
  'docs/ops/calendar-maintenance.md',
  'docs/upstream-archive.md',
  'docs/release-checklist.md',
  'docs/contracts/datasets.md',
  'docs/contracts/capability-matrix.md',
  'docs/contracts/market-strategy.md',
  'docs/contracts/eastmoney-http.md',
  'scripts/release_tag.ps1',
  'scripts/check_docs.ps1',
  'scripts/check_versions.ps1',
  'packages/providers/README.md',
  'packages/providers/pyproject.toml',
  'packages/providers/src/stock_platform_providers/__init__.py',
  'apps/workbench/README.md',
  'apps/workbench/pyproject.toml',
  'apps/workbench/src/stock_platform_workbench/__init__.py',
  'packages/research/README.md',
  'packages/research/pyproject.toml',
  'packages/research/src/stock_platform_research/__init__.py',
  'packages/agents/README.md',
  'packages/agents/pyproject.toml',
  'packages/agents/src/stock_platform_agents/__init__.py',
  'packages/execution/README.md',
  'packages/execution/pyproject.toml',
  'packages/execution/src/stock_platform_execution/__init__.py'
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
