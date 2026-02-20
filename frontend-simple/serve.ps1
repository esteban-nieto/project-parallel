$ErrorActionPreference = "Stop"

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

$port = 5174
Write-Host "Serving frontend-simple at http://localhost:$port"
python -m http.server $port
