# Sube al servidor lo que no esta en git: modelos, base de datos y .env.
# Se ejecuta en tu PC (PowerShell), desde la carpeta del proyecto:
#   powershell -ExecutionPolicy Bypass -File deploy\subir_al_servidor.ps1 -Servidor 1.2.3.4
#
# Antes: deten el bot en tu PC (Ctrl+C) para que la base de datos no cambie
# mientras se copia y para no tener dos bots respondiendo a la vez.
param(
  [Parameter(Mandatory = $true)][string]$Servidor,
  [string]$Usuario = 'cyberbot',
  [string]$Carpeta = 'MPB',
  [switch]$SinBaseDeDatos
)
$ErrorActionPreference = 'Stop'
$destino = "$Usuario@$Servidor"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

foreach ($f in @('models\classic_model.joblib', 'models\roberta_finetuned\config.json', '.env')) {
  if (-not (Test-Path $f)) { throw "Falta $f en tu PC." }
}

Write-Host '==> Creando carpetas en el servidor'
ssh $destino "mkdir -p $Carpeta/models $Carpeta/data $Carpeta/backups"
if ($LASTEXITCODE -ne 0) { throw 'No se pudo conectar por SSH.' }

Write-Host '==> Modelo clasico'
scp models\classic_model.joblib models\classic_metrics.json "${destino}:$Carpeta/models/"
if ($LASTEXITCODE -ne 0) { throw 'Fallo la copia del modelo clasico.' }

Write-Host '==> RoBERTa ajustado (~420 MB, puede tardar)'
scp -r models\roberta_finetuned "${destino}:$Carpeta/models/"
if ($LASTEXITCODE -ne 0) { throw 'Fallo la copia de RoBERTa.' }

if (-not $SinBaseDeDatos -and (Test-Path 'data\bot_database.db')) {
  Write-Host '==> Base de datos (copia consistente)'
  $tmp = Join-Path $env:TEMP 'bot_database_subida.db'
  if (Test-Path $tmp) { Remove-Item $tmp -Force }
  & env\Scripts\python.exe -c "import sqlite3,sys; s=sqlite3.connect('data/bot_database.db'); d=sqlite3.connect(sys.argv[1]); s.backup(d); d.close(); s.close()" $tmp
  if ($LASTEXITCODE -ne 0) { throw 'No se pudo copiar la base de datos.' }
  scp $tmp "${destino}:$Carpeta/data/bot_database.db"
  if ($LASTEXITCODE -ne 0) { throw 'Fallo la subida de la base de datos.' }
  Remove-Item $tmp -Force
}

Write-Host '==> .env (credenciales)'
scp .env "${destino}:$Carpeta/.env"
if ($LASTEXITCODE -ne 0) { throw 'Fallo la subida del .env.' }
ssh $destino "chmod 600 $Carpeta/.env"

Write-Host ''
Write-Host 'Archivos subidos. Siguiente paso, en el servidor:'
Write-Host "    cd $Carpeta && bash deploy/install_services.sh bot"
