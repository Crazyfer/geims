<#
.SYNOPSIS
    Runs Godot test scenarios in headless mode and reports pass/fail.
    PowerShell counterpart of tools/run_tests.py for systems without Python.

.PARAMETER Scenario
    Run only this scenario (without the .json extension).

.PARAMETER Verbose
    Stream full Godot stdout for each scenario.

.EXAMPLE
    .\tools\run_tests.ps1
    .\tools\run_tests.ps1 -Scenario double_jump
    .\tools\run_tests.ps1 -Verbose

.NOTES
    Set $env:GODOT_BIN to the absolute path of the Godot executable, or place
    godot.exe on PATH.
#>
[CmdletBinding()]
param(
    [string]$Scenario,
    [switch]$ShowFull,
    [switch]$Windowed,
    [double]$Linger = 0.0
)

$ErrorActionPreference = 'Stop'

function Resolve-GodotBin {
    if ($env:GODOT_BIN -and (Test-Path $env:GODOT_BIN)) { return $env:GODOT_BIN }
    foreach ($name in 'godot.exe','Godot.exe','godot') {
        $c = Get-Command $name -ErrorAction SilentlyContinue
        if ($c) { return $c.Source }
    }
    throw "Could not locate Godot. Set `$env:GODOT_BIN to the full path of the Godot executable."
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$scenariosDir = Join-Path $projectRoot 'tests\scenarios'
if (-not (Test-Path $scenariosDir)) { throw "No scenarios directory: $scenariosDir" }

$godot = Resolve-GodotBin
Write-Output "godot: $godot"
Write-Output "project: $projectRoot`n"

$scenarios = Get-ChildItem -Path $scenariosDir -Filter '*.json' | Sort-Object Name
if ($Scenario) {
    $scenarios = $scenarios | Where-Object { $_.BaseName -eq $Scenario }
    if (-not $scenarios) { throw "No scenario matched: $Scenario" }
}

$passed = 0
$failed = @()

$effectiveLinger = $Linger
if ($Windowed -and $effectiveLinger -le 0.0) { $effectiveLinger = 3.0 }

foreach ($s in $scenarios) {
    Write-Output "=== $($s.BaseName) ==="
    $stdoutTmp = New-TemporaryFile
    $stderrTmp = New-TemporaryFile
    $rel = "res://tests/scenarios/$($s.Name)"

    $godotArgs = @()
    if (-not $Windowed) { $godotArgs += '--headless' }
    $godotArgs += @('--path', $projectRoot, 'res://tests/test_runner.tscn', '--', '--scenario', $rel)
    if ($effectiveLinger -gt 0.0) { $godotArgs += @('--linger', ('{0:N2}' -f $effectiveLinger)) }

    $proc = Start-Process -FilePath $godot `
        -ArgumentList $godotArgs `
        -NoNewWindow -Wait -PassThru `
        -RedirectStandardOutput $stdoutTmp.FullName `
        -RedirectStandardError  $stderrTmp.FullName

    $stdout = Get-Content $stdoutTmp.FullName
    if ($ShowFull) {
        $stdout | ForEach-Object { Write-Output $_ }
    } else {
        $stdout | Where-Object { $_ -match 'summary|fail_detail' } | ForEach-Object { Write-Output "  $_" }
    }
    Remove-Item $stdoutTmp.FullName, $stderrTmp.FullName -Force

    if ($proc.ExitCode -eq 0) { $passed++ } else { $failed += $s.BaseName }
    Write-Output ""
}

$total = @($scenarios).Count
Write-Output "=== results ==="
Write-Output "passed $passed/$total"
if ($failed.Count -gt 0) {
    Write-Output ("failed: " + ($failed -join ', '))
    exit 1
}
exit 0
