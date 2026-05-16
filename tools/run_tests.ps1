<#
.SYNOPSIS
    Runs Godot test scenarios and reports pass/fail.
    Windowed by default; use -Headless for CI.

.PARAMETER Scenario
    Run only this scenario (without the .json extension).

.PARAMETER ShowFull
    Stream full Godot stdout for each scenario.

.PARAMETER Headless
    Run without a window (CI mode). Disables window focusing.

.PARAMETER Linger
    Seconds to keep the window open after the scenario ends (default 3.0 in windowed mode).

.EXAMPLE
    .\tools\run_tests.ps1
    .\tools\run_tests.ps1 -Scenario double_jump
    .\tools\run_tests.ps1 -Headless

.NOTES
    Set $env:GODOT_BIN to the absolute path of the Godot executable, or place
    godot.exe on PATH.
#>
[CmdletBinding()]
param(
    [string]$Scenario,
    [switch]$ShowFull,
    [switch]$Headless,
    [double]$Linger = 0.0
)

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32Window {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern bool AllowSetForegroundWindow(int dwProcessId);
}
"@

function Set-WindowForeground([System.Diagnostics.Process]$proc) {
    $deadline = (Get-Date).AddSeconds(5)
    while ($proc.MainWindowHandle -eq [IntPtr]::Zero -and (Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 150
        $proc.Refresh()
    }
    if ($proc.MainWindowHandle -ne [IntPtr]::Zero) {
        [Win32Window]::AllowSetForegroundWindow($proc.Id) | Out-Null
        [Win32Window]::ShowWindow($proc.MainWindowHandle, 9) | Out-Null  # SW_RESTORE
        [Win32Window]::SetForegroundWindow($proc.MainWindowHandle) | Out-Null
    }
}

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

if (-not (Test-Path (Join-Path $projectRoot '.godot'))) {
    Write-Output "importing assets (first run)..."
    $importProc = Start-Process -FilePath $godot `
        -ArgumentList @('--headless', '--import', '--path', $projectRoot) `
        -NoNewWindow -Wait -PassThru `
        -RedirectStandardOutput (New-TemporaryFile).FullName `
        -RedirectStandardError  (New-TemporaryFile).FullName
    Write-Output "import done (exit $($importProc.ExitCode))`n"
}

$scenarios = Get-ChildItem -Path $scenariosDir -Filter '*.json' | Sort-Object Name
if ($Scenario) {
    $scenarios = $scenarios | Where-Object { $_.BaseName -eq $Scenario }
    if (-not $scenarios) { throw "No scenario matched: $Scenario" }
}

$passed = 0
$failed = @()

$effectiveLinger = $Linger
if (-not $Headless -and $effectiveLinger -le 0.0) { $effectiveLinger = 3.0 }

foreach ($s in $scenarios) {
    Write-Output "=== $($s.BaseName) ==="
    $stdoutTmp = New-TemporaryFile
    $stderrTmp = New-TemporaryFile
    $rel = "res://tests/scenarios/$($s.Name)"

    $godotArgs = @()
    if ($Headless) { $godotArgs += '--headless' }
    $godotArgs += @('--path', $projectRoot, 'res://tests/test_runner.tscn', '--', '--scenario', $rel)
    if ($effectiveLinger -gt 0.0) { $godotArgs += @('--linger', ('{0:N2}' -f $effectiveLinger)) }

    $proc = Start-Process -FilePath $godot `
        -ArgumentList $godotArgs `
        -NoNewWindow -PassThru `
        -RedirectStandardOutput $stdoutTmp.FullName `
        -RedirectStandardError  $stderrTmp.FullName

    if (-not $Headless) { Set-WindowForeground $proc }

    $proc.WaitForExit()

    $stdout = Get-Content $stdoutTmp.FullName
    if ($ShowFull) {
        $stdout | ForEach-Object { Write-Output $_ }
    } else {
        $stdout | Where-Object { $_ -match 'summary|fail_detail' } | ForEach-Object { Write-Output "  $_" }
    }
    Remove-Item $stdoutTmp.FullName, $stderrTmp.FullName -Force

    # Use stdout summary as authoritative signal; Godot may exit non-zero on
    # Windows headless due to Vulkan/display init errors unrelated to test outcome.
    $summaryLine = $stdout | Where-Object { $_ -match '\[TEST\].*\bsummary\b' } | Select-Object -Last 1
    $scenePassed = $summaryLine -match 'summary PASS'
    if ($scenePassed) { $passed++ } else { $failed += $s.BaseName }
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
