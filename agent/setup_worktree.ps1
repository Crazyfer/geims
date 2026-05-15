<#
.SYNOPSIS
    One-time setup of the git worktree the Discord agent operates inside.
    Creates a sibling directory <project>-agent on branch agent/work.
#>
[CmdletBinding()]
param(
    [string]$Branch = 'agent/work'
)

$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$parent = Split-Path -Parent $projectRoot
$name   = Split-Path -Leaf  $projectRoot
$worktree = Join-Path $parent ($name + '-agent')

Write-Output "project : $projectRoot"
Write-Output "worktree: $worktree"
Write-Output "branch  : $Branch"

if (Test-Path $worktree) {
    Write-Output "Worktree path already exists. Listing git worktrees:"
    Set-Location $projectRoot
    git worktree list
    exit 0
}

Set-Location $projectRoot

$exists = git branch --list $Branch
if ($exists) {
    git worktree add $worktree $Branch
} else {
    git worktree add $worktree -b $Branch
}

Write-Output ""
Write-Output "Worktree ready. Set AGENT_WORKTREE in agent/.env:"
Write-Output "  AGENT_WORKTREE=$worktree"
