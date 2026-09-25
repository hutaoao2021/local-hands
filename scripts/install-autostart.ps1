$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Vbs = (Resolve-Path (Join-Path $Root 'scripts\start-bridge-hidden.vbs')).Path
$Startup = [Environment]::GetFolderPath('Startup')
if (-not $Startup) { throw 'Could not resolve the current user Startup folder.' }

$ShortcutPath = Join-Path $Startup 'Local Hands Bridge.lnk'
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = Join-Path $env:SystemRoot 'System32\wscript.exe'
$Shortcut.Arguments = '"' + $Vbs + '"'
$Shortcut.WorkingDirectory = $Root
$Shortcut.Description = 'Start Local Hands Browser Bridge after Windows sign-in'
$Shortcut.Save()

Write-Host "Installed Local Hands autostart for the current Windows user."
Write-Host "Shortcut: $ShortcutPath"
Write-Host "No administrator permission was required."
Write-Host ""
Write-Host "Important: pair the browser extension once using a visible start-bridge.ps1 session before relying on hidden autostart."
Write-Host "The current bridge process is not restarted by this installer."
