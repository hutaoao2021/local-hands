$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Bridge = (Resolve-Path (Join-Path $Root 'server\browser_bridge.py')).Path

# Avoid duplicate bridge processes when Windows autostart is installed and the
# user also launches start-bridge.ps1 manually.
try {
    $escaped = [regex]::Escape($Bridge)
    $existing = Get-CimInstance Win32_Process -ErrorAction Stop |
        Where-Object { $_.CommandLine -and $_.CommandLine -match $escaped } |
        Select-Object -First 1
    if ($existing) {
        Write-Host "Local Hands Browser Bridge is already running (PID $($existing.ProcessId))."
        exit 0
    }
} catch {
    # Process discovery is best-effort; if CIM is unavailable, launch normally.
}

python $Bridge @args
