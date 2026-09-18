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
  stock-platform-daily --provider. Default: env STOCK_PLATFORM_DAILY_PROVIDER
  or 'replay' (CI / offline). Live day-use: tushare / cn_tushare_http
  (requires STOCK_PLATFORM_TUSHARE_TOKEN; no silent fixture fallback).

.PARAMETER LiveDay
  One-shot day-use: Provider=tushare (unless already set), SkipRefresh, SettleAfter.
  Does not change the script default for CI (still replay without this switch).

.PARAMETER SettleAfter
  After successful brief: log picks into performance JSONL and settle pending
  (engine market.db preferred). Maps to stock-platform-daily --settle-after.

.EXAMPLE
  .\scripts\ops\Invoke-DailyPipeline.ps1 -Asof 2026-09-02
  # replay demo against repo fixtures (default universe + fixtures path)

.EXAMPLE
  .\scripts\ops\Invoke-DailyPipeline.ps1 -Asof 2026-09-02 -Provider tushare -SkipRefresh
  # live daily via Tushare (token from env); skip refresh persist

.EXAMPLE
  .\scripts\ops\Invoke-DailyPipeline.ps1 -LiveDay -Asof 2026-09-12
  # 一键日用：tushare + 跳过 refresh + 落库 + 记入/结算绩效

.EXAMPLE
  .\scripts\ops\Invoke-DailyPipeline.ps1 -Asof 2028-01-05 -SkipRefresh
#>
[CmdletBinding()]
param(
  [string]$Asof = '',
  [ValidateSet('CN', 'US', 'HK')]
  [string]$Market = 'CN',
  [string]$Provider = '',
  [string]$Fixtures = '',
  [string]$Out = '',
  [string]$Universe = '',
  [switch]$SkipRefresh,
  [switch]$SettleAfter,
  [switch]$LiveDay,
  [switch]$Force
)

$ErrorActionPreference = 'Stop'

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..\..')
Set-Location $repoRoot

if ($LiveDay) {
  if ([string]::IsNullOrWhiteSpace($Provider)) {
    $Provider = 'tushare'
  }
  $SkipRefresh = $true
  $SettleAfter = $true
}

if ([string]::IsNullOrWhiteSpace($Asof)) {
  $Asof = (Get-Date).ToString('yyyy-MM-dd')
}

if ([string]::IsNullOrWhiteSpace($Provider)) {
  if (-not [string]::IsNullOrWhiteSpace($env:STOCK_PLATFORM_DAILY_PROVIDER)) {
    $Provider = $env:STOCK_PLATFORM_DAILY_PROVIDER
  }
  else {
    $Provider = 'replay'
  }
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

if ($SettleAfter) {
  $cliArgs += '--settle-after'
}

Write-Host "RUN stock-platform-daily asof=$Asof provider=$Provider out=$Out settleAfter=$SettleAfter liveDay=$LiveDay"
$cmd = Get-Command stock-platform-daily -ErrorAction SilentlyContinue
if ($null -ne $cmd) {
  & stock-platform-daily @cliArgs
  exit $LASTEXITCODE
}

# Fallback when console script is not on PATH (editable install / venv).
& python -m stock_platform_research.daily_cli @cliArgs
exit $LASTEXITCODE
