$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $projectRoot '.runtime'
$postgresExe = Join-Path $runtimeRoot 'pgsql\bin\postgres.exe'
if (Test-Path -LiteralPath $postgresExe) {
    & $postgresExe --version
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL local no se puede ejecutar.' }
    return
}
New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
$archive = Join-Path $runtimeRoot 'postgresql-17.11-windows-x64.zip'
# Enlace publicado en https://www.enterprisedb.com/download-postgresql-binaries
Invoke-WebRequest -UseBasicParsing -Uri 'https://sbp.enterprisedb.com/getfile.jsp?fileid=1260491' -OutFile $archive
Expand-Archive -LiteralPath $archive -DestinationPath $runtimeRoot -Force
if (-not (Test-Path -LiteralPath $postgresExe)) { throw 'El archivo no contiene los binarios esperados.' }
& $postgresExe --version
if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL local no se puede ejecutar.' }
Get-FileHash -LiteralPath $archive -Algorithm SHA256 | Select-Object Algorithm,Hash
