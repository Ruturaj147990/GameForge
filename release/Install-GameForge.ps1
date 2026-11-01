# Install-GameForge.ps1 — Creates Start Menu and Desktop shortcuts for GameForge IDE (User Scope, No Admin Required)
$ErrorActionPreference = "Stop"

$InstallDir = $PSScriptRoot
$LauncherBat = Join-Path $InstallDir "GameForge.bat"
$IconPath = Join-Path $InstallDir "gameforge.ico"

if (-not (Test-Path $LauncherBat)) {
    Write-Error "Launcher not found at: $LauncherBat"
}

$WshShell = New-Object -ComObject WScript.Shell

# 1. Desktop Shortcut
$DesktopPath = [Environment]::GetFolderPath("Desktop")
$DesktopShortcutPath = Join-Path $DesktopPath "GameForge.lnk"
$Shortcut = $WshShell.CreateShortcut($DesktopShortcutPath)
$Shortcut.TargetPath = $LauncherBat
$Shortcut.WorkingDirectory = $InstallDir
$Shortcut.Description = "GameForge IDE — Turn natural-language game ideas into playable UE 5.7 games"
if (Test-Path $IconPath) {
    $Shortcut.IconLocation = "$IconPath,0"
}
$Shortcut.Save()
Write-Host "Created Desktop Shortcut: $DesktopShortcutPath"

# 2. Start Menu Shortcut
$StartMenuPath = [Environment]::GetFolderPath("Programs")
$GameForgeMenuDir = Join-Path $StartMenuPath "GameForge"
if (-not (Test-Path $GameForgeMenuDir)) {
    New-Item -ItemType Directory -Path $GameForgeMenuDir -Force | Out-Null
}
$MenuShortcutPath = Join-Path $GameForgeMenuDir "GameForge.lnk"
$MenuShortcut = $WshShell.CreateShortcut($MenuShortcutPath)
$MenuShortcut.TargetPath = $LauncherBat
$MenuShortcut.WorkingDirectory = $InstallDir
$MenuShortcut.Description = "GameForge IDE — Natural language game creation platform"
if (Test-Path $IconPath) {
    $MenuShortcut.IconLocation = "$IconPath,0"
}
$MenuShortcut.Save()
Write-Host "Created Start Menu Shortcut: $MenuShortcutPath"

Write-Host "GameForge 1.0 installation completed successfully!"
