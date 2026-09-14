<#
.SYNOPSIS
  Run stock-platform-daily on CN trading days; skip closed days with exit 0.

.DESCRIPTION
  Resolves --asof (today local, or -Asof), checks TradingCalendar for CN,
  then invokes stock-platform-daily. Default provider is replay (no liveTrading).
  No secrets. PowerShell 5.1+ compatible (no && chaining).

.PARAMETER Asof
  Trade date YYYY-MM-DD. Default: local calendar today.

.PARAMETER Market
  Calendar market id (default CN).

.PARAMETER Provider
  stock-platform-daily --provider (default replay).

.PARAMETER Fixtures
  Replay fixtures directory. Default: packages/providers/tests/fixtures
  relative to repo root, or env STOCK_PLATFORM_FIXTURES.

.PARAMETER Out
  Persist root for refresh/briefs. Default: env STOCK_PLATFORM_REFRESH_DIR
  or %TEMP%\stock-platform-daily.

.PARAMETER Universe
  Optional universe JSON path.

.PARAMETER SkipRefresh
  Pass --skip-refresh to the CLI.

.PARAMETER Force
  Run even on non-trading days (still uses TradingCalendar only for logging).

.EXAMPLE
  .\scripts\ops\Invoke-DailyPipeline.ps1 -Asof 2028-01-03
  # skips (CN New Year observed) with exit 0

.EXAMPLE
  .\scripts\ops\Invoke-DailyPipeline.ps1 -Asof 2026-09-02
  # replay demo against repo fixtures (default universe + fixtures path)

.EXAMPLE
  .\scripts\ops\Invoke-DailyPipeline.ps1 -Asof 2028-01-05 -SkipRefresh
#>
[CmdletBinding()]
param(
  [string]$Asof = '',
  [ValidateSet('CN', 'US', 'HK')]
  [string]$Market = 'CN',
  [string]$Provider = 'replay',
  [string]$Fixtures = '',
  [string]$Out = '',
  [string]$Universe = '',
  [switch]$SkipRefresh,
  [switch]$Force
)

$ErrorActionPreference = 'Stop'

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..\..')
Set-Location $repoRoot

if ([string]::IsNullOrWhiteSpace($Asof)) {
  $Asof = (Get-Date).ToString('yyyy-MM-dd')
}

if ([string]::IsNullOrWhiteSpace($Fixtures)) {
  if (-not [string]::IsNullOrWhiteSpace($env:STOCK_PLATFORM_FIXTURES)) {
    $Fixtures = $env:STOCK_PLATFORM_FIXTURES
  }
  else {
    $Fixtures = Join-Path $repoRoot 'packages\providers\tests\fixtures'
  }
}

if ([string]::IsNullOrWhiteSpace($Out)) {
  if (-not [string]::IsNullOrWhiteSpace($env:STOCK_PLATFORM_REFRESH_DIR)) {
    $Out = $env:STOCK_PLATFORM_REFRESH_DIR
  }
  else {
    $Out = Join-Path $env:TEMP 'stock-platform-daily'
  }
}

$pyCheck = @"
from datetime import date
from stock_platform_providers import get_trading_calendar
asof = date.fromisoformat('$Asof')
cal = get_trading_calendar('$Market')
print('1' if cal.is_trading_day(asof) else '0')
"@

$tradingFlag = & python -c $pyCheck
if ($LASTEXITCODE -ne 0) {
  Write-Error "TradingCalendar check failed (is stock-platform-providers installed?)"
  exit 1
}
$tradingFlag = ($tradingFlag | Select-Object -Last 1).ToString().Trim()

if ($tradingFlag -ne '1') {
  if (-not $Force) {
    Write-Host "SKIP non-trading day market=$Market asof=$Asof (exit 0)"
    exit 0
  }
  Write-Host "WARN non-trading day market=$Market asof=$Asof but -Force set; continuing"
}

$cliArgs = @(
  '--asof', $Asof,
  '--provider', $Provider,
  '--out', $Out
)

if ($Provider -eq 'replay') {
  $cliArgs += @('--fixtures', $Fixtures)
}

if (-not [string]::IsNullOrWhiteSpace($Universe)) {
  $cliArgs += @('--universe', $Universe)
}

if ($SkipRefresh) {
  $cliArgs += '--skip-refresh'
}

Write-Host "RUN stock-platform-daily asof=$Asof provider=$Provider out=$Out"
$cmd = Get-Command stock-platform-daily -ErrorAction SilentlyContinue
if ($null -ne $cmd) {
  & stock-platform-daily @cliArgs
  exit $LASTEXITCODE
}

# Fallback when console script is not on PATH (editable install / venv).
& python -m stock_platform_research.daily_cli @cliArgs
exit $LASTEXITCODE
