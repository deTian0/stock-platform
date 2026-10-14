<#
.SYNOPSIS
  Run a scheduled stock-platform job and record the run in the ops ledger.

.DESCRIPTION
  Before T2 the platform had **no structured record** of "did the scheduled job
  actually run?". The 2026-10-13/14 incident proved the cost: market.db stopped
  advancing and the brief froze at 10-12, yet the only way to find out why was to
  leave the platform and dig through Windows Task Scheduler — where the 18:30
  backfill task turned out to have **never been registered at all**.

  This wrapper is the single entry point for *scheduled* runs. It resolves the
  job from a **task preset** (so the canonical arguments can never be forgotten),
  runs the target script in a **child process** (so the target's own ``exit``
  codes are captured and can never bypass this wrapper), then appends exactly one
  record to the platform-owned ledger ``data/logs/runs.jsonl`` via
  ``stock-platform-ops-ledger --record``.

  Recording is **best-effort**: any failure to log is reported but never changes
  the exit code — a bookkeeping problem must not fail the job it is observing.
  The ledger only ever writes the platform's own ``data/`` directory; it never
  touches ``market.db`` or any database (ADR 0058 / ADR 0076).

.PARAMETER Task
  Job id — also the ledger task name. Known presets:
  daily | postmarket | marketdb-backfill. Unknown ids are stored as-is, but then
  ``-Script`` must be given explicitly (the ledger must accept future jobs).

.PARAMETER Script
  Optional. Path to the .ps1 to run (absolute, or relative to the repo root).
  Defaults to the preset for ``-Task``.

.PARAMETER TargetArgs
  Optional. Arguments forwarded to the target script, space-separated
  (e.g. ``-Mode dry-run``). Defaults to the preset for ``-Task``. Kept as a plain
  string on purpose: ``powershell -File`` passes ``-Name a,b`` through as one
  token, so a string[] parameter would silently degrade to a single argument.

.PARAMETER PlannedAt
  Scheduled time, e.g. ``08:30`` or an ISO8601 timestamp. Defaults to the preset.

.PARAMETER Asof
  Trade date this run targets (YYYY-MM-DD). Recorded for reference only.

.EXAMPLE
  # Canonical 08:30 pre-market job (args come from the preset)
  .\scripts\ops\Invoke-ScheduledRun.ps1 -Task daily

.EXAMPLE
  # Canonical 18:30 backfill, dry-run reconnaissance pass
  .\scripts\ops\Invoke-ScheduledRun.ps1 -Task marketdb-backfill -TargetArgs '-Mode dry-run'

.EXAMPLE
  # Ad-hoc: any script, recorded under a custom task id
  .\scripts\ops\Invoke-ScheduledRun.ps1 -Task adhoc -Script .\scripts\ops\Invoke-MarketDbBackfill.ps1 -TargetArgs '-Mode validate'
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)]
  [string]$Task,

  [string]$Script = '',

  [string]$TargetArgs = '',

  [string]$PlannedAt = '',

  [string]$Asof = ''
)

# Canonical schedule: one place to change when a job's arguments move.
$TASK_PRESETS = @{
  'daily'             = @{ Script = 'scripts\ops\Invoke-DailyPipeline.ps1'
                           Args   = '-MarketDb -PrevSession -Digest'
                           PlannedAt = '08:30' }
  'postmarket'        = @{ Script = 'scripts\ops\Invoke-DailyPipeline.ps1'
                           Args   = '-MarketDb -PrevSession -SettleAfter -Digest'
                           PlannedAt = '15:30' }
  'marketdb-backfill' = @{ Script = 'scripts\ops\Invoke-MarketDbBackfill.ps1'
                           Args   = '-Mode apply'
                           PlannedAt = '18:30' }
}

# Keep going on stray stderr from native children: the platform CLIs print
# pandas RuntimeWarnings and the whole point is to capture the exit code, not to
# abort on noise (see docs/ops/scheduler.md).
$ErrorActionPreference = 'Continue'

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..\..')
Set-Location $repoRoot

$venvPy = Join-Path $repoRoot '.venv\Scripts\python.exe'
$python = if (Test-Path $venvPy) { $venvPy } else { 'python' }

$env:PYTHONIOENCODING = 'utf-8'

$preset = $TASK_PRESETS[$Task]
if ([string]::IsNullOrWhiteSpace($Script)) {
  if ($null -ne $preset) { $Script = [string]$preset.Script }
}
if ([string]::IsNullOrWhiteSpace($TargetArgs) -and $null -ne $preset) {
  $TargetArgs = [string]$preset.Args
}
if ([string]::IsNullOrWhiteSpace($PlannedAt) -and $null -ne $preset) {
  $PlannedAt = [string]$preset.PlannedAt
}

if ([string]::IsNullOrWhiteSpace($Script)) {
  Write-Host "SCHEDULED task=$Task has no preset and no -Script; refusing to guess."
  exit 2
}

# Resolve the target script (absolute, or relative to the repo root).
if (-not (Test-Path $Script)) {
  $candidate = Join-Path $repoRoot $Script
  if (Test-Path $candidate) { $Script = $candidate }
}

$psExe = (Get-Command powershell.exe -ErrorAction SilentlyContinue).Source
if ([string]::IsNullOrWhiteSpace($psExe)) { $psExe = 'powershell.exe' }

# Space-separated → argv tokens (empty tokens dropped).
$forward = @()
if (-not [string]::IsNullOrWhiteSpace($TargetArgs)) {
  $forward = @($TargetArgs -split '\s+' | Where-Object { $_ -ne '' })
}

$startedAt = Get-Date
$sw = [System.Diagnostics.Stopwatch]::StartNew()
$ec = 1

if (-not (Test-Path $Script)) {
  Write-Host "SCHEDULED task=$Task script NOT FOUND: $Script"
}
else {
  Write-Host "SCHEDULED task=$Task script=$Script args=[$($forward -join ' ')]"
  # Child process: the target's `exit` cannot terminate this wrapper, so we always
  # get to record a row. stderr is intentionally NOT merged (see header notes).
  & $psExe -NoProfile -ExecutionPolicy Bypass -File $Script @forward
  $ec = $LASTEXITCODE
}
$sw.Stop()

$endedAt = Get-Date
$duration = [math]::Round($sw.Elapsed.TotalSeconds, 3)

# --- ledger record (best-effort; never changes $ec) -------------------------
$recArgs = @(
  '-m', 'stock_platform_research.ops_ledger_cli',
  '--record',
  '--task', $Task,
  '--exit-code', "$ec",
  '--started-at', $startedAt.ToString('o'),
  '--ended-at', $endedAt.ToString('o'),
  '--duration-sec', "$duration"
)
if (-not [string]::IsNullOrWhiteSpace($PlannedAt)) { $recArgs += @('--planned-at', $PlannedAt) }
if (-not [string]::IsNullOrWhiteSpace($Asof)) { $recArgs += @('--asof', $Asof) }

try {
  & $python @recArgs 2>&1 | Out-Null
  Write-Host "SCHEDULED task=$Task exit=$ec duration=${duration}s ledger-recorded"
}
catch {
  Write-Host "SCHEDULED task=$Task exit=$ec duration=${duration}s ledger-record FAILED (best-effort): $_"
}

Write-Host "SCHEDULED task=$Task done exit=$ec"
exit $ec
