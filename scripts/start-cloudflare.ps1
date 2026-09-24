$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
python (Join-Path $Root 'server\cloudflare_companion.py') @args
