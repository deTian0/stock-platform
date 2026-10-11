<#
.SYNOPSIS
  "WorkBuddy mode": refresh the westock JSON cache, then run the daily pipeline.

.DESCRIPTION
  One command that wires the two halves of the WorkBuddy data path together:

    1. bridge  — `stock-platform-workbuddy-bridge` calls the WorkBuddy `westock`
                 CLI and lands `daily_{code}.json` / `realtime_{code}.json` in
                 STOCK_PLATFORM_WORKBUDDY_CACHE_DIR.
    2. daily   — `stock-platform-daily` runs with
                 STOCK_PLATFORM_PROVIDER_PRESET=workbuddy, whose read-only
                 `workbuddy` provider consumes exactly that cache.

  Neither half is live-trading: the provider is offline-deterministic and the
  bridge only reads public market data. No secrets, no `liveTradingEnabled`.

  Default symbol set = the CLI's own universe config; pass -Symbols /
  -SymbolsFile to override. Auto-derives a watchlist from the engine market.db
  with -FromMarketDb (top-N by recent amount).

.PARAMETER Symbols
  Comma-separated codes, e.g. "sh600519,sz000001,sh510300".

.PARAMETER SymbolsFile
  File with one code per line (# comments allowed).

.PARAMETER FromMarketDb
  Derive the symbol list from the engine market.db instead of the universe
  config. Combine with -Top to bound it.

.PARAMETER Top
  When -FromMarketDb is set, keep this many most-active codes (default 50).

.PARAMETER Datasets
  daily,realtime (default daily). Use both for a full snapshot.

.PARAMETER Limit
  Bars per symbol for the daily dataset (default 120).

.PARAMETER Asof
  Trade date / quote date YYYY-MM-DD. Default: local today for the pipeline;
  the bridge omits --date (latest available) unless -AsofQuote is given.

.PARAMETER AsofQuote
  Pass --asof to the bridge's quote call (historical snapshot, not live).

.PARAMETER SkipBridge
  Do not refresh the cache (use whatever is already on disk).

.PARAMETER SkipDaily
  Only refresh the cache.

.PARAMETER DryRun
  Bridge parses + reports but writes nothing; the daily run is skipped.

.PARAMETER Force
  Run the daily pipeline even on a non-trading day.

.EXAMPLE
  .\scripts\ops\Invoke-WorkbuddyBridge.ps1 -Symbols sh600519,sz000001 -Datasets daily,realtime
  # Refresh the cache for two codes, then run the daily pipeline in workbuddy mode.

.EXAMPLE
  .\scripts\ops\Invoke-WorkbuddyBridge.ps1 -FromMarketDb -Top 200 -Limit 60
  # Bridge the 200 most-active codes with 60 bars, then run the pipeline.
#>
[CmdletBinding()]
param(
  [string]$Symbols = '',
  [string]$SymbolsFile = '',
  [switch]$FromMarketDb,
  [int]$Top = 50,
  [string]$Datasets = 'daily',
  [int]$Limit = 120,
  [string]$Period = 'day',
  [string]$Adjust = 'qfq',
  [string]$Asof = '',
  [string]$AsofQuote = '',
  [string]$CacheDir = '',
  [string]$Out = '',
  [string]$Provider = '',
  [switch]$SkipBridge,
  [switch]$SkipDaily,
  [switch]$DryRun,
  [switch]$Force
)

$ErrorActionPreference = 'Stop'

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..\..')
Set-Location $repoRoot

# Prefer the repo venv interpreter: a scheduled task has no activated shell.
$venvPy = Join-Path $repoRoot '.venv\Scripts\python.exe'
$python = if (Test-Path $venvPy) { $venvPy } else { 'python' }

# ---- Load repo-root .env so manual runs match scheduled runs ----------------
$dotenv = Join-Path $repoRoot '.env'
if (Test-Path $dotenv) {
  Get-Content $dotenv | ForEach-Object {
    $line = $_.Trim()
    if ($line -eq '' -or $line.StartsWith('#')) { return }
    if ($line -like 'export *') { $line = $line.Substring(7).Trim() }
    $idx = $line.IndexOf('=')
    if ($idx -lt 1) { return }
    $key = $line.Substring(0, $idx).Trim()
    $val = $line.Substring($idx + 1).Trim()
    if ($val.Length -ge 2 -and $val[0] -eq $val[-1] -and ($val[0] -eq '"' -or $val[0] -eq "'")) {
      $val = $val.Substring(1, $val.Length - 2)
    }
    # setdefault semantics: an explicitly exported value always wins
    if ([string]::IsNullOrEmpty([Environment]::GetEnvironmentVariable($key, 'Process'))) {
      [Environment]::SetEnvironmentVariable($key, $val, 'Process')
    }
  }
}

# ---- Resolve cache dir (default under data/ so it survives reboots) ---------
if ([string]::IsNullOrWhiteSpace($CacheDir)) {
  if (-not [string]::IsNullOrWhiteSpace($env:STOCK_PLATFORM_WORKBUDDY_CACHE_DIR)) {
    $CacheDir = $env:STOCK_PLATFORM_WORKBUDDY_CACHE_DIR
  }
  else {
    $CacheDir = Join-Path $repoRoot 'data\workbuddy_cache'
  }
}
$env:STOCK_PLATFORM_WORKBUDDY_CACHE_DIR = $CacheDir

# ---- WorkBuddy mode: route daily/realtime through the cache ----------------
$env:STOCK_PLATFORM_PROVIDER_PRESET = 'workbuddy'

Write-Host "WORKBUDDY MODE cache=$CacheDir preset=$($env:STOCK_PLATFORM_PROVIDER_PRESET)"
New-Item -ItemType Directory -Force -Path $CacheDir | Out-Null

# ---- Derive symbols from market.db when asked ------------------------------
if ($FromMarketDb -and [string]::IsNullOrWhiteSpace($Symbols) -and [string]::IsNullOrWhiteSpace($SymbolsFile)) {
  $db = $env:STOCK_PLATFORM_ENGINE_MARKET_DB
  if ([string]::IsNullOrWhiteSpace($db)) {
    Write-Error "STOCK_PLATFORM_ENGINE_MARKET_DB is not set; cannot use -FromMarketDb."
    exit 1
  }
  Write-Host "DERIVE symbols from market.db (top $Top by recent amount)"
  $pyDerive = @"
import sqlite3
db = sqlite3.connect(r'''$db''')
try:
    asof = db.execute('select max(date) from daily_price').fetchone()[0]
    if not asof:
        raise SystemExit('daily_price is empty')
    rows = db.execute(
        '''select code
             from daily_price
            where date = ?
            order by amount desc
            limit ?''',
        (asof, $Top),
    ).fetchall()
finally:
    db.close()
print(','.join(r[0] for r in rows))
"@
  $Symbols = (& $python -c $pyDerive | Select-Object -Last 1).ToString().Trim()
  if ([string]::IsNullOrWhiteSpace($Symbols)) {
    Write-Error "market.db returned no symbols for -FromMarketDb."
    exit 1
  }
}

# ---- Step 1: bridge --------------------------------------------------------
if (-not $SkipBridge) {
  $bridgeArgs = @(
    '--cache-dir', $CacheDir,
    '--datasets', $Datasets,
    '--period', $Period,
    '--adjust', $Adjust,
    '--limit', $Limit
  )
  if (-not [string]::IsNullOrWhiteSpace($Symbols)) { $bridgeArgs += @('--symbols', $Symbols) }
  if (-not [string]::IsNullOrWhiteSpace($SymbolsFile)) { $bridgeArgs += @('--symbols-file', $SymbolsFile) }
  if (-not [string]::IsNullOrWhiteSpace($AsofQuote)) { $bridgeArgs += @('--asof', $AsofQuote) }
  if ($DryRun) { $bridgeArgs += '--dry-run' }

  Write-Host "BRIDGE stock-platform-workbuddy-bridge $($bridgeArgs -join ' ')"
  $cmd = Get-Command stock-platform-workbuddy-bridge -ErrorAction SilentlyContinue
  if ($null -ne $cmd) {
    & stock-platform-workbuddy-bridge @bridgeArgs
  }
  else {
    & $python -m stock_platform_research.workbuddy_bridge_cli @bridgeArgs
  }
  $bridgeEc = $LASTEXITCODE
  if ($bridgeEc -ne 0) {
    Write-Host "WARN bridge exited $bridgeEc (continuing to the daily run unless -SkipDaily)"
  }
}

if ($DryRun) {
  Write-Host "DRY-RUN: cache not written; skipping the daily run."
  exit 0
}

if ($SkipDaily) {
  Write-Host "SKIP daily run (-SkipDaily)."
  exit 0
}

# ---- Step 2: daily pipeline in workbuddy mode ------------------------------
$dailyScript = Join-Path $PSScriptRoot 'Invoke-DailyPipeline.ps1'
$dailyParams = @{}
if (-not [string]::IsNullOrWhiteSpace($Asof)) { $dailyParams['Asof'] = $Asof }
if (-not [string]::IsNullOrWhiteSpace($Out)) { $dailyParams['Out'] = $Out }
if ($Force) { $dailyParams['Force'] = $true }
# Invoke-DailyPipeline defaults --provider to replay and passes it explicitly,
# which would override the preset. Pin it to `workbuddy` unless the caller
# asked for something else.
if ([string]::IsNullOrWhiteSpace($Provider)) {
  $Provider = 'workbuddy'
  $env:STOCK_PLATFORM_DAILY_PROVIDER = 'workbuddy'
}
$dailyParams['Provider'] = $Provider
# The workbuddy provider serves a bounded cache; per-symbol JSON refresh is
# meaningless (the bridge already produced it), so skip the refresh pass.
$dailyParams['SkipRefresh'] = $true

Write-Host "DAILY workbuddy mode (provider=$Provider preset=$($env:STOCK_PLATFORM_PROVIDER_PRESET))"
& $dailyScript @dailyParams
exit $LASTEXITCODE
