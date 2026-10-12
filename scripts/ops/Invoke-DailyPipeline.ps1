<#
.SYNOPSIS
  Run stock-platform-daily on CN trading days; skip closed days with exit 0.

.DESCRIPTION
  Resolves --asof (today local, or -Asof), checks TradingCalendar for CN,
  then invokes stock-platform-daily. Default provider is replay (no liveTrading).
  No secrets. PowerShell 5.1+ compatible (no && chaining).

  Uses the repo .venv interpreter when present (falls back to PATH `python`),
  and the CLI itself now auto-loads repo-root `.env` (P0-2) — so a scheduled
  task no longer needs the .env injected by a wrapper .bat.

.PARAMETER Asof
  Trade date YYYY-MM-DD. Default: local calendar today.

.PARAMETER Market
  Calendar market id (default CN).

.PARAMETER Provider
  stock-platform-daily --provider. Default: env STOCK_PLATFORM_DAILY_PROVIDER
  or 'replay' (CI / offline). Live day-use: tushare / cn_tushare_http
  (requires STOCK_PLATFORM_TUSHARE_TOKEN; no silent fixture fallback).
  Offline whole-market: market_db (single SQL pass over the engine warehouse).

.PARAMETER LiveDay
  One-shot day-use: Provider=tushare (unless already set), SkipRefresh, SettleAfter.
  Does not change the script default for CI (still replay without this switch).

.PARAMETER MarketDb
  P0-1 fast path: Provider=market_db, whole-market universe, and refresh JSON
  persistence off. The pre-market job finishes in seconds instead of hours.

.PARAMETER PrevSession
  Resolve -Asof as the **previous CN trading day** before local today.
  Scheduled runs should use this: market.db is backfilled by the production
  side in the evening, so a morning run for *today* would hit an empty panel
  (today's bars do not exist yet). T-1 close is the correct PIT cross-section.

.PARAMETER Digest
  After a successful pipeline run, render the human-readable markdown digest
  (stock-platform-digest) for the same asof into data/digests/.

.PARAMETER SettleAfter
  After successful brief: log picks into performance JSONL and settle pending
  (engine market.db preferred). Maps to stock-platform-daily --settle-after.

.EXAMPLE
  .\scripts\ops\Invoke-DailyPipeline.ps1 -MarketDb
  # 盘前推荐：全市场 + 本地 market.db 批量取数（默认快路径）

.EXAMPLE
  .\scripts\ops\Invoke-DailyPipeline.ps1 -Asof 2026-09-02 -Provider tushare -SkipRefresh
  # live daily via Tushare (token from .env / env); skip refresh persist
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
  [switch]$MarketDb,
  [switch]$PrevSession,
  [switch]$Digest,
  [switch]$Force
)

$ErrorActionPreference = 'Stop'

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..\..')
Set-Location $repoRoot

# Prefer the repo venv interpreter: a scheduled task has no activated shell and
# may have no `python` on PATH at all (the old script assumed otherwise).
$venvPy = Join-Path $repoRoot '.venv\Scripts\python.exe'
$python = if (Test-Path $venvPy) { $venvPy } else { 'python' }

if ($MarketDb) {
  $Provider = 'market_db'
  if ([string]::IsNullOrWhiteSpace($Universe)) {
    # Whole-market universe straight from the warehouse.
    $Universe = ''
  }
}

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

# -PrevSession: scheduled runs must review T-1, not today (see .PARAMETER notes).
if ($PrevSession) {
  $pyPrev = @"
from datetime import date, timedelta
from stock_platform_providers import get_trading_calendar
today = date.fromisoformat('$Asof')
cal = get_trading_calendar('$Market')
day = today - timedelta(days=1)
for _ in range(30):
    if cal.is_trading_day(day):
        print(day.isoformat()); break
    day -= timedelta(days=1)
else:
    raise SystemExit('no trading day found within 30 days before ' + today.isoformat())
"@
  $prev = & $python -c $pyPrev
  if ($LASTEXITCODE -ne 0) {
    Write-Error "PrevSession resolution failed (TradingCalendar import or data issue)."
    exit 1
  }
  $prev = ($prev | Select-Object -Last 1).ToString().Trim()
  if (-not $prev) {
    Write-Error "PrevSession resolution returned an empty date."
    exit 1
  }
  Write-Host "PREVSESSION asof=$Asof -> $prev"
  $Asof = $prev
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

$tradingFlag = & $python -c $pyCheck
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

# P0-1: the offline bulk source serves the whole market in one SQL pass; skip the
# per-symbol JSON dump (measured ~110s for 5.2k files with no consumer in the brief).
if ($Provider -eq 'market_db') {
  $cliArgs += @('--universe-source', 'market_db', '--no-refresh-persist')
}

if ($SkipRefresh) {
  $cliArgs += '--skip-refresh'
}

if ($SettleAfter) {
  $cliArgs += '--settle-after'
}

Write-Host "RUN stock-platform-daily asof=$Asof provider=$Provider out=$Out settleAfter=$SettleAfter liveDay=$LiveDay marketDb=$MarketDb prevSession=$PrevSession digest=$Digest"
$cmd = Get-Command stock-platform-daily -ErrorAction SilentlyContinue
if ($null -ne $cmd) {
  & stock-platform-daily @cliArgs
  $cliEc = $LASTEXITCODE
}
else {
  # Fallback when console script is not on PATH (editable install / venv).
  & $python -m stock_platform_research.daily_cli @cliArgs
  $cliEc = $LASTEXITCODE
}

if ($cliEc -ne 0) {
  exit $cliEc
}

if ($Digest) {
  Write-Host "DIGEST rendering markdown digest for asof=$Asof"
  $digestArgs = @('-m', 'stock_platform_research.daily_digest_cli', '--asof', $Asof)
  & $python @digestArgs
  if ($LASTEXITCODE -ne 0) {
    # Digest is best-effort: a rendering failure must not flip the pipeline result.
    Write-Host "WARN digest rendering failed (pipeline result unchanged)"
  }
}
exit $cliEc
