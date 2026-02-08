$ErrorActionPreference = "Stop"

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

$port = 5173
Write-Host "Serving frontend at http://localhost:$port"
python -m http.server $port

