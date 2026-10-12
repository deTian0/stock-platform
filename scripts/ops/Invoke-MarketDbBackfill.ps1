<#
.SYNOPSIS
  Backfill the a-stock-engine market.db daily_price gaps (production-side feed).

.DESCRIPTION
  The pre-market job resolves T-1 from the calendar and builds a PIT cross-section
  from market.db. Nothing on this box fed that warehouse, so a morning run could
  resolve an asof the DB did not cover yet -> empty panel -> an EMPTY brief that
  shadows the newest real one in the digest. This wrapper closes that gap by
  running the **engine's own** backfill script (the platform itself never writes
  market.db — ADR 0058, C2: the platform is read-only over the warehouse).

  The engine script is idempotent: it lists CN trading days whose row count is
  below the full-market threshold and re-fetches only those (INSERT OR REPLACE),
  strictly sequentially with an inter-call sleep (CPU-safe).

.PARAMETER Mode
  apply   (default) fetch + write the missing days
  dry-run only list what would be backfilled; nothing is written
  validate calibrate the unit conversion against an existing full-coverage day

.PARAMETER EngineRoot
  Path to the archived a-stock-engine clone. Defaults to the sibling checkout.

.EXAMPLE
  .\scripts\ops\Invoke-MarketDbBackfill.ps1 -Mode dry-run
  .\scripts\ops\Invoke-MarketDbBackfill.ps1 -Mode apply
#>
[CmdletBinding()]
param(
  [ValidateSet('apply', 'dry-run', 'validate')]
  [string]$Mode = 'apply',
  [string]$EngineRoot = 'D:\workspace\stock_trading\a-stock-engine'
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path $EngineRoot)) {
  Write-Error "Engine root not found: $EngineRoot (pass -EngineRoot <path>)"
  exit 1
}

$py = Join-Path $EngineRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) {
  # Fall back to PATH python; the engine script itself explains a missing dep.
  $py = 'python'
}

$engineScript = Join-Path $EngineRoot 'empirical\backfill_market_daily.py'
if (-not (Test-Path $engineScript)) {
  Write-Error "Engine backfill script not found: $engineScript"
  exit 1
}

# The engine script resolves market.db from its own file location, so cwd is
# irrelevant; still, run from the engine root so its `src` import path works.
Push-Location $EngineRoot
try {
  Write-Host "RUN engine backfill mode=$Mode engine=$EngineRoot py=$py"
  & $py $engineScript "--$Mode"
  $ec = $LASTEXITCODE
}
finally {
  Pop-Location
}

Write-Host "BACKFILL mode=$Mode exit=$ec"
exit $ec
