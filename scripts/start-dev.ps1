$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
& .\.venv\Scripts\python.exe scripts/dev.py start
if ($LASTEXITCODE -ne 0) { throw 'No se pudo iniciar PostgreSQL.' }
& .\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
if ($LASTEXITCODE -ne 0) { throw 'El servidor Django termino con un error.' }
