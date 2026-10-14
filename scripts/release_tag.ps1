<#
.SYNOPSIS
  Create an annotated SemVer git tag for stock-platform.

.DESCRIPTION
  Enforces VERSION file consistency, refuses to move existing tags,
  and maps -Kind to documentation expectations (patch=small, minor/major=big).

  The tag message is always written to a UTF-8 (no BOM) temp file OUTSIDE the
  repo and passed to `git tag -a -F`, never as a native `-m` argument. This keeps
  Chinese annotations intact: PowerShell 5.1 encodes native command-line
  arguments with the ANSI code page (GBK on this machine), which would otherwise
  mangle any non-ASCII message.

.PARAMETER Version
  SemVer without leading v, e.g. 0.0.1

.PARAMETER Kind
  patch | minor | major | rc

.PARAMETER Message
  Annotated tag message body (short). Prefer -MessageFile for Chinese.

.PARAMETER MessageFile
  Path to a UTF-8 file whose contents become the tag message body.
  Use this for Chinese annotations so no CLI encoding is involved.

.PARAMETER DryRun
  Print actions only.

.EXAMPLE
  .\scripts\release_tag.ps1 -Version 0.0.1 -Kind patch -Message "M0.1 scaffold"

.EXAMPLE
  .\scripts\release_tag.ps1 -Version 4.6.1 -Kind patch -MessageFile "$env:TEMP\tag.txt"
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)]
  [ValidatePattern('^\d+\.\d+\.\d+([.-][0-9A-Za-z.+-]+)?$')]
  [string]$Version,

  [Parameter(Mandatory = $true)]
  [ValidateSet('patch', 'minor', 'major', 'rc')]
  [string]$Kind,

  [Parameter(Mandatory = $false)]
  [string]$Message = '',

  [Parameter(Mandatory = $false)]
  [string]$MessageFile = '',

  [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot '..')
Set-Location $root

$versionFile = Join-Path $root 'VERSION'
if (-not (Test-Path $versionFile)) {
  throw "VERSION file missing at $versionFile"
}
$tag = "v$Version"
$fileVersion = (Get-Content $versionFile -Raw).Trim()
if ($fileVersion -ne $Version) {
  throw "VERSION file is '$fileVersion' but -Version is '$Version'. Update VERSION first."
}

if ([string]::IsNullOrWhiteSpace($Message) -and [string]::IsNullOrWhiteSpace($MessageFile)) {
  throw "Provide -Message (ASCII) or -MessageFile (UTF-8, for Chinese)."
}

if (-not [string]::IsNullOrWhiteSpace($MessageFile)) {
  if (-not (Test-Path $MessageFile)) {
    throw "MessageFile not found: $MessageFile"
  }
  $body = [System.IO.File]::ReadAllText($MessageFile, (New-Object System.Text.UTF8Encoding($false)))
} else {
  $body = $Message
}
$body = $body.TrimStart([char]0xFEFF).TrimEnd("`r", "`n")

$fullMessage = @"
$tag ($Kind milestone)

$body

See docs/ROADMAP.md and docs/versioning.md.
"@

Write-Host "Root:    $root"
Write-Host "Version: $Version"
Write-Host "Tag:     $tag"
Write-Host "Kind:    $Kind"

if ($DryRun) {
  $existing = git tag -l $tag
  if ($existing) {
    Write-Host "[DryRun] note: tag $tag already exists (would refuse without -DryRun)"
  }
  $status = git status --porcelain
  if ($status) {
    Write-Host "[DryRun] note: working tree not clean (would refuse without -DryRun)"
  }
  Write-Host "[DryRun] git tag -a $tag -F <utf8-tempfile>"
  Write-Host $fullMessage
  exit 0
}

$existing = git tag -l $tag
if ($existing) {
  throw "Tag $tag already exists. Refusing to move tags."
}

$status = git status --porcelain
if ($status) {
  throw "Working tree not clean. Commit or stash before tagging.`n$status"
}

$msgFile = Join-Path $env:TEMP ("sp_tagmsg_$Version.txt")
[System.IO.File]::WriteAllText($msgFile, $fullMessage, (New-Object System.Text.UTF8Encoding($false)))

git tag -a $tag -F $msgFile
Write-Host "Created annotated tag $tag (UTF-8 message via $msgFile)"
git show $tag --no-patch
Write-Host "Done. Push when ready: git push origin main --follow-tags"
