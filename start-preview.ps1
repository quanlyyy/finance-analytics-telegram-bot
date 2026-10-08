$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:DEV_AUTH = 'true'
Write-Host 'Preview: http://127.0.0.1:8000/?demo=1'
& '.\.venv\Scripts\python.exe' -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
