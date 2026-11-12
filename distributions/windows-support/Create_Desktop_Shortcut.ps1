$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$IconDir = Join-Path $Root "packages\pps-resources\assets\app"
$Desktop = [Environment]::GetFolderPath("Desktop")

$Shell = New-Object -ComObject WScript.Shell

function New-ToolkitShortcut {
  param(
    [string]$Name,
    [string]$Target,
    [string]$Description,
    [string]$IconName
  )
  $ShortcutPath = Join-Path $Desktop $Name
  $Shortcut = $Shell.CreateShortcut($ShortcutPath)
  $Shortcut.TargetPath = $Target
  $Shortcut.WorkingDirectory = $Root
  $Shortcut.WindowStyle = 1
  $Shortcut.Description = $Description
  $IconPath = Join-Path $IconDir $IconName
  if (Test-Path -LiteralPath $IconPath) {
    $Shortcut.IconLocation = "$IconPath,0"
  }
  $Shortcut.Save()
  Write-Host "Created shortcut: $ShortcutPath"
}

New-ToolkitShortcut `
  -Name "Peripersonal Space Toolkit.lnk" `
  -IconName "pps_toolkit_icon.ico" `
  -Target (Join-Path $Root "apps\designer\launchers\Launch_HTML_Dashboard.bat") `
  -Description "Launch the Peripersonal Space Toolkit local dashboard"

New-ToolkitShortcut `
  -Name "PPS Experiment Runner.lnk" `
  -IconName "pps_runner_icon.ico" `
  -Target (Join-Path $Root "apps\runner\launchers\Launch_Experiment_Runner.bat") `
  -Description "Launch native PPS Focus Mode for a prepared dashboard setup"
