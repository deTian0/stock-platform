<#
.SYNOPSIS
  Register / inspect / remove the two stock-platform scheduled tasks
  (pre-market 08:30 + post-market 15:30).

.DESCRIPTION
  Wraps Register-ScheduledTask from the versioned XML files in scripts/ops:
    stock-platform-daily.xml      -> task "stock-platform-daily"      (08:30, -MarketDb -PrevSession -Digest)
    stock-platform-postmarket.xml -> task "stock-platform-postmarket" (15:30, -MarketDb -PrevSession -SettleAfter -Digest)

  Tasks run as the current user (InteractiveToken, LeastPrivilege) — no admin
  needed. Non-trading days are skipped by the wrapper (exit 0 via calendar).

.PARAMETER All
  Register both tasks (default action when no other action switch is given).

.PARAMETER PreMarket
  Register only the pre-market task.

.PARAMETER PostMarket
  Register only the post-market task.

.PARAMETER Status
  Show registration state + last/next run info; change nothing.

.PARAMETER Unregister
  Remove both tasks (or only those selected by -PreMarket / -PostMarket).

.PARAMETER RunNow
  After registration, start the selected tasks immediately (verification).

.EXAMPLE
  .\scripts\ops\Register-ScheduledTasks.ps1                 # register both
  .\scripts\ops\Register-ScheduledTasks.ps1 -Status
  .\scripts\ops\Register-ScheduledTasks.ps1 -Unregister
#>
[CmdletBinding()]
param(
  [switch]$PreMarket,
  [switch]$PostMarket,
  [switch]$All,
  [switch]$Status,
  [switch]$Unregister,
  [switch]$RunNow
)

$ErrorActionPreference = 'Stop'
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..\..')
Set-Location $repoRoot

$tasks = @(
  @{
    Name = 'stock-platform-daily'
    Xml  = 'scripts\ops\stock-platform-daily.xml'
    Slot = 'PreMarket'
  },
  @{
    Name = 'stock-platform-postmarket'
    Xml  = 'scripts\ops\stock-platform-postmarket.xml'
    Slot = 'PostMarket'
  }
)

$selected = $tasks | Where-Object {
  if ($PreMarket -and $_.Slot -eq 'PreMarket') { return $true }
  if ($PostMarket -and $_.Slot -eq 'PostMarket') { return $true }
  return ($All -or (-not $PreMarket -and -not $PostMarket))
}

function Show-Status {
  foreach ($t in $tasks) {
    $existing = Get-ScheduledTask -TaskName $t.Name -ErrorAction SilentlyContinue
    if ($null -eq $existing) {
      Write-Host ("{0,-28} NOT REGISTERED" -f $t.Name)
      continue
    }
    $info = $existing | Get-ScheduledTaskInfo
    Write-Host ("{0,-28} state={1,-9} lastRun={2} lastResult=0x{3:X} nextRun={4}" -f `
      $t.Name, $existing.State, $info.LastRunTime, $info.LastTaskResult, $info.NextRunTime)
  }
}

if ($Status) {
  Show-Status
  exit 0
}

if ($Unregister) {
  foreach ($t in $selected) {
    $existing = Get-ScheduledTask -TaskName $t.Name -ErrorAction SilentlyContinue
    if ($null -ne $existing) {
      Unregister-ScheduledTask -TaskName $t.Name -Confirm:$false
      Write-Host "UNREGISTERED $($t.Name)"
    }
    else {
      Write-Host "SKIP $($t.Name) (not registered)"
    }
  }
  exit 0
}

foreach ($t in $selected) {
  $xmlPath = Join-Path $repoRoot $t.Xml
  if (-not (Test-Path $xmlPath)) {
    Write-Error "Missing task XML: $xmlPath"
    exit 1
  }
  # PS 5.1 Get-Content would decode UTF-8 (no BOM) XML with the ANSI codepage
  # and corrupt the Chinese description ("任务 XML 格式错误"). ReadAllText is UTF-8.
  $xml = [System.IO.File]::ReadAllText($xmlPath)
  # Task Scheduler's -Xml string parameter rejects the encoding declaration
  # ("(1,40)::错误: 无法切换编码"); the file keeps it for GUI import.
  $xml = $xml -replace '^\s*<\?xml[^>]*\?>\s*', ''
  # Idempotent: re-register overwrites an existing definition.
  Register-ScheduledTask -TaskName $t.Name -Xml $xml -Force -ErrorAction Stop | Out-Null
  Write-Host "REGISTERED $($t.Name) (from $($t.Xml))"
}

if ($RunNow) {
  foreach ($t in $selected) {
    Write-Host "START $($t.Name) (on demand)"
    Start-ScheduledTask -TaskName $t.Name
  }
}

Show-Status
