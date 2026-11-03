param([string]$PythonPath)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    if (-not $PythonPath) {
        $candidate = Join-Path $env:LOCALAPPDATA 'Python\pythoncore-3.14-64\python.exe'
        if (Test-Path $candidate) { $PythonPath = $candidate }
        else { throw 'Indica Python 3.14 con -PythonPath C:\ruta\python.exe' }
    }
    & $PythonPath -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el entorno virtual.' }
}
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'No se pudieron instalar las dependencias.' }
if (-not (Test-Path '.runtime\pgsql\bin\pg_ctl.exe')) {
    & "$PSScriptRoot\install-postgres.ps1"
}
& .\.venv\Scripts\python.exe scripts/dev.py setup
if ($LASTEXITCODE -ne 0) { throw 'No se pudo preparar PostgreSQL.' }
& .\.venv\Scripts\python.exe manage.py migrate --noinput
if ($LASTEXITCODE -ne 0) { throw 'Fallaron las migraciones.' }
& .\.venv\Scripts\python.exe manage.py bootstrap_roles
if ($LASTEXITCODE -ne 0) { throw 'No se pudieron crear los perfiles.' }
& .\.venv\Scripts\python.exe manage.py check
if ($LASTEXITCODE -ne 0) { throw 'Fallo la comprobacion Django.' }
Write-Host 'Entorno listo. Inicia con: powershell -ExecutionPolicy Bypass -File scripts/start-dev.ps1'
