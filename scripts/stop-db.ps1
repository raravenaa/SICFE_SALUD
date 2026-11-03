$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
& .\.venv\Scripts\python.exe scripts/dev.py stop
if ($LASTEXITCODE -ne 0) { throw 'No se pudo detener PostgreSQL.' }
