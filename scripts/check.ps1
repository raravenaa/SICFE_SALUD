$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
& .\.venv\Scripts\python.exe -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Dependencias incompatibles.' }
& .\.venv\Scripts\python.exe -m ruff check .
if ($LASTEXITCODE -ne 0) { throw 'Fallo la revision de codigo.' }
& .\.venv\Scripts\python.exe -m ruff format --check .
if ($LASTEXITCODE -ne 0) { throw 'Fallo la revision de formato.' }
& .\.venv\Scripts\python.exe scripts/dev.py start
if ($LASTEXITCODE -ne 0) { throw 'No se pudo iniciar PostgreSQL.' }
& .\.venv\Scripts\python.exe manage.py check
if ($LASTEXITCODE -ne 0) { throw 'Fallo la comprobacion Django.' }
& .\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
if ($LASTEXITCODE -ne 0) { throw 'Hay modelos sin migracion.' }
& .\.venv\Scripts\python.exe manage.py test --settings=config.test_settings --noinput
if ($LASTEXITCODE -ne 0) { throw 'Fallaron las pruebas.' }
