param(
    [ValidateSet("Emulator", "Left", "Primary", "Right")]
    [string]$Monitor = "Left",
    [int]$RunnerWidth = 820,
    [int]$Gap = 8,
    [string]$RunnerTitlePattern = "PPS Experiment Runner",
    [string]$EmulatorTitlePattern = "Android Emulator"
)

$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Windows.Forms

if (-not ("PPSWindowPlacement.Native" -as [type])) {
    Add-Type @"
using System;
using System.Runtime.InteropServices;
namespace PPSWindowPlacement {
    public static class Native {
        [DllImport("user32.dll")]
        public static extern bool MoveWindow(IntPtr hWnd, int X, int Y, int nWidth, int nHeight, bool bRepaint);
    }
}
"@
}

$screens = [System.Windows.Forms.Screen]::AllScreens
if (-not $screens -or $screens.Count -eq 0) {
    throw "No Windows screens were reported."
}

$emulatorProcess = Get-Process -ErrorAction SilentlyContinue |
    Where-Object { $_.MainWindowHandle -ne 0 -and $_.MainWindowTitle -like "*$EmulatorTitlePattern*" } |
    Sort-Object ProcessName, Id |
    Select-Object -First 1

switch ($Monitor) {
    "Emulator" {
        if ($null -eq $emulatorProcess) {
            throw "Could not find an Android emulator window. Start the emulator or pass -Monitor Primary, Left, or Right explicitly."
        }
        $screen = [System.Windows.Forms.Screen]::FromHandle($emulatorProcess.MainWindowHandle)
    }
    "Primary" {
        $screen = $screens | Where-Object { $_.Primary } | Select-Object -First 1
    }
    "Right" {
        $screen = $screens | Sort-Object { $_.WorkingArea.X } -Descending | Select-Object -First 1
    }
    default {
        $screen = $screens | Sort-Object { $_.WorkingArea.X } | Select-Object -First 1
    }
}

if ($null -eq $screen) {
    throw "Could not resolve monitor '$Monitor'."
}

$area = $screen.WorkingArea
$usableWidth = [Math]::Max(640, [int]$area.Width)
$runnerWidth = [Math]::Max(560, [Math]::Min([int]$RunnerWidth, [int]($usableWidth * 0.48)))
$emulatorWidth = [Math]::Max(640, $usableWidth - $runnerWidth - [Math]::Max(0, $Gap))
if (($runnerWidth + $Gap + $emulatorWidth) -gt $usableWidth) {
    $runnerWidth = [Math]::Max(520, $usableWidth - $Gap - $emulatorWidth)
}

$runnerRect = [pscustomobject]@{
    X      = [int]$area.X
    Y      = [int]$area.Y
    Width  = [int]$runnerWidth
    Height = [int]$area.Height
}
$emulatorRect = [pscustomobject]@{
    X      = [int]($area.X + $runnerWidth + $Gap)
    Y      = [int]$area.Y
    Width  = [int]($area.Width - $runnerWidth - $Gap)
    Height = [int]$area.Height
}

function Move-MatchingWindow {
    param(
        [string]$Role,
        [string]$TitlePattern,
        [pscustomobject]$Rect
    )
    $process = Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $_.MainWindowHandle -ne 0 -and $_.MainWindowTitle -like "*$TitlePattern*" } |
        Sort-Object ProcessName, Id |
        Select-Object -First 1
    if ($null -eq $process) {
        return [pscustomobject]@{
            role   = $Role
            moved  = $false
            reason = "window_not_found"
            title  = ""
            pid    = $null
        }
    }
    [PPSWindowPlacement.Native]::MoveWindow(
        $process.MainWindowHandle,
        [int]$Rect.X,
        [int]$Rect.Y,
        [int]$Rect.Width,
        [int]$Rect.Height,
        $true
    ) | Out-Null
    return [pscustomobject]@{
        role   = $Role
        moved  = $true
        reason = ""
        title  = $process.MainWindowTitle
        pid    = $process.Id
        x      = [int]$Rect.X
        y      = [int]$Rect.Y
        width  = [int]$Rect.Width
        height = [int]$Rect.Height
    }
}

$results = @(
    (Move-MatchingWindow -Role "runner" -TitlePattern $RunnerTitlePattern -Rect $runnerRect),
    (Move-MatchingWindow -Role "android_emulator" -TitlePattern $EmulatorTitlePattern -Rect $emulatorRect)
)

[pscustomobject]@{
    monitor      = $Monitor
    device_name  = $screen.DeviceName
    primary      = [bool]$screen.Primary
    working_area = [pscustomobject]@{
        x      = [int]$area.X
        y      = [int]$area.Y
        width  = [int]$area.Width
        height = [int]$area.Height
    }
    runner_rect  = $runnerRect
    emulator_rect = $emulatorRect
    windows      = $results
} | ConvertTo-Json -Depth 5
