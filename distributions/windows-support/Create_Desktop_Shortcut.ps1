$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$IconPath = Join-Path $Root "packages\pps-resources\assets\app\pps_toolkit_icon.ico"
$Desktop = [Environment]::GetFolderPath("Desktop")

$Shell = New-Object -ComObject WScript.Shell

function New-ToolkitShortcut {
  param(
    [string]$Name,
    [string]$Target,
    [string]$Description
  )
  $ShortcutPath = Join-Path $Desktop $Name
  $Shortcut = $Shell.CreateShortcut($ShortcutPath)
  $Shortcut.TargetPath = $Target
  $Shortcut.WorkingDirectory = $Root
  $Shortcut.WindowStyle = 1
  $Shortcut.Description = $Description
  if (Test-Path $IconPath) {
    $Shortcut.IconLocation = "$IconPath,0"
  }
  $Shortcut.Save()
  Write-Host "Created shortcut: $ShortcutPath"
}

New-ToolkitShortcut `
  -Name "Peripersonal Space Toolkit.lnk" `
  -Target (Join-Path $Root "apps\designer\launchers\Launch_HTML_Dashboard.bat") `
  -Description "Launch the Peripersonal Space Toolkit local dashboard"

New-ToolkitShortcut `
  -Name "PPS Experiment Runner.lnk" `
  -Target (Join-Path $Root "apps\runner\launchers\Launch_Experiment_Runner.bat") `
  -Description "Launch native PPS Focus Mode for a prepared dashboard setup"
