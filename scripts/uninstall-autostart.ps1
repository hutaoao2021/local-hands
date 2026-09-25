$ErrorActionPreference = 'Stop'
$Startup = [Environment]::GetFolderPath('Startup')
$ShortcutPath = Join-Path $Startup 'Local Hands Bridge.lnk'
if (Test-Path $ShortcutPath) {
    Remove-Item -LiteralPath $ShortcutPath -Force
    Write-Host "Removed Local Hands Windows autostart: $ShortcutPath"
} else {
    Write-Host "Local Hands Windows autostart was not installed."
}
Write-Host "Any bridge process already running is left untouched."
