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
  Path to the archived a-stock-engine clone. Required unless STOCK_PLATFORM_ENGINE_REPO is set.
  No hardcoded sibling default — fail-closed when unset.

.PARAMETER SkipPlatformPost
  ADR 0097: after a successful ``apply`` the wrapper also runs the platform
  post-close steps that need today's bar — ``stock-platform-loop-health``
  (local/health/) and ``stock-platform-shadow-board --settle-daily``
  (local/shadow/). Both are best-effort and never change the exit code. Pass this
  switch to run the engine backfill alone (debugging only).

.EXAMPLE
  .\scripts\ops\Invoke-MarketDbBackfill.ps1 -Mode dry-run -EngineRoot <engine-root>
  .\scripts\ops\Invoke-MarketDbBackfill.ps1 -Mode apply
#>
[CmdletBinding()]
param(
  [ValidateSet('apply', 'dry-run', 'validate')]
  [string]$Mode = 'apply',
  [string]$EngineRoot = '',
  # ADR 0097: skip the platform post-close steps (loop health + shadow settle).
  # Only useful for debugging the engine backfill itself.
  [switch]$SkipPlatformPost
)

$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($EngineRoot)) {
  $EngineRoot = [string]$env:STOCK_PLATFORM_ENGINE_REPO
}
if ([string]::IsNullOrWhiteSpace($EngineRoot)) {
  Write-Error "EngineRoot is required (pass -EngineRoot or set STOCK_PLATFORM_ENGINE_REPO). No default sibling path."
  exit 1
}

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

# --- platform post-close steps (ADR 0097) ------------------------------------
# The engine backfill is the thing that pushes **today's** bar into market.db, so
# the platform-side work that depends on that bar belongs here rather than in the
# 15:30 pipeline (which still sees T-1):
#   1. loop_health  -> recompute coverage / brief / hits / performance / dataQuality
#      against the just-updated warehouse (writes local/health/).
#   2. shadow --settle-daily -> settle pending shadow ledger rows with closes that
#      only exist now (local/shadow/, ADR 0093 forward samples). Without this the
#      forward ledger stays pending forever and Y2 never gets evidence.
# Both are best-effort: a failure is reported but never turns a successful backfill
# into a failed task, and never changes $ec.
if ($ec -eq 0 -and $Mode -eq 'apply' -and -not $SkipPlatformPost) {
  $repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
  $platformPy = Join-Path $repoRoot '.venv\Scripts\python.exe'
  if (-not (Test-Path $platformPy)) { $platformPy = 'python' }

  Push-Location $repoRoot
  try {
    Write-Host 'POST loop-health'
    & $platformPy -m stock_platform_research.loop_health_cli --on-ok summary
    Write-Host "POST loop-health exit=$LASTEXITCODE"

    Write-Host 'POST shadow-settle'
    & $platformPy -m stock_platform_research.shadow_board.cli --settle-daily
    Write-Host "POST shadow-settle exit=$LASTEXITCODE"
  }
  catch {
    Write-Warning "platform post-close step failed: $($_.Exception.Message)"
  }
  finally {
    Pop-Location
  }
}
elseif (-not $SkipPlatformPost) {
  Write-Host "POST skipped (mode=$Mode exit=$ec; platform steps only run after a successful apply)"
}

exit $ec
