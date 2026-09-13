<#
.SYNOPSIS
  Create an annotated SemVer git tag for stock-platform.

.DESCRIPTION
  Enforces VERSION file consistency, refuses to move existing tags,
  and maps -Kind to documentation expectations (patch=small, minor/major=big).

.PARAMETER Version
  SemVer without leading v, e.g. 0.0.1

.PARAMETER Kind
  patch | minor | major | rc

.PARAMETER Message
  Annotated tag message body (short).

.PARAMETER DryRun
  Print actions only.

.EXAMPLE
  .\scripts\release_tag.ps1 -Version 0.0.1 -Kind patch -Message "M0.1 scaffold"
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)]
  [ValidatePattern('^\d+\.\d+\.\d+([.-][0-9A-Za-z.+-]+)?$')]
  [string]$Version,

  [Parameter(Mandatory = $true)]
  [ValidateSet('patch', 'minor', 'major', 'rc')]
  [string]$Kind,

  [Parameter(Mandatory = $true)]
  [string]$Message,

  [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot '..')
Set-Location $root

$versionFile = Join-Path $root 'VERSION'
if (-not (Test-Path $versionFile)) {
  throw "VERSION file missing at $versionFile"
}
$fileVersion = (Get-Content $versionFile -Raw).Trim()
if ($fileVersion -ne $Version) {
  throw "VERSION file is '$fileVersion' but -Version is '$Version'. Update VERSION first."
}

$tag = "v$Version"
$existing = git tag -l $tag
if ($existing) {
  throw "Tag $tag already exists. Refusing to move tags."
}

$status = git status --porcelain
if ($status) {
  throw "Working tree not clean. Commit or stash before tagging.`n$status"
}

$fullMessage = @"
$tag ($Kind milestone)

$Message

See docs/ROADMAP.md and docs/versioning.md.
"@

Write-Host "Root:    $root"
Write-Host "Version: $Version"
Write-Host "Tag:     $tag"
Write-Host "Kind:    $Kind"

if ($DryRun) {
  Write-Host "[DryRun] git tag -a $tag -m <message>"
  Write-Host $fullMessage
  exit 0
}

git tag -a $tag -m $fullMessage
Write-Host "Created annotated tag $tag"
git show $tag --no-patch
Write-Host "Done. Push when ready: git push origin main --follow-tags"
