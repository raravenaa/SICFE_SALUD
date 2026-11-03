# Entorno de desarrollo local

## Componentes

Windows de 64 bits y Python 3.14. El proyecto utiliza Django 5.2 LTS, PostgreSQL 17.11, Psycopg 3, python-dotenv y Ruff. Las versiones exactas de Python instalables se gestionan por separado; las dependencias de aplicación están fijadas en `requirements.txt`. `requirements.in` expresa los rangos para futuras actualizaciones deliberadas.

Se utiliza el Python ya instalado en el equipo para crear `.venv`. PostgreSQL se extrae dentro del proyecto, sin registrar un servicio de Windows ni modificar el PATH global. Los scripts actuales están preparados para Windows.

Fuentes consultadas para preparar el entorno: [compatibilidad de Django 5.2](https://docs.djangoproject.com/en/5.2/releases/5.2/), [distribución PostgreSQL para Windows](https://www.postgresql.org/download/windows/) y [binarios de EDB](https://www.enterprisedb.com/download-postgresql-binaries).

## Estructura

| Ruta | Función |
|---|---|
| `.venv/` | Intérprete y dependencias aisladas |
| `.runtime/pgsql/` | Binarios locales de PostgreSQL |
| `.local/pgdata/` | Archivos persistentes de la base de desarrollo |
| `.local/postgres.log` | Registro de PostgreSQL |
| `.env` | Configuración y secretos locales generados aleatoriamente |
| `.env.example` | Plantilla sin secretos |
| `config/` | Configuración Django, rutas, WSGI y ASGI |
| `apps/core/` | Página inicial, comprobación de conexión y pruebas |
| `apps/inventory/` | Catálogo, movimientos, saldos, permisos, auditoría y pruebas |
| `templates/` | Plantillas de interfaz |
| `scripts/` | Preparación, arranque, parada y verificaciones |

`.gitignore` excluye secretos, entorno virtual, binarios y datos locales. No borrar `.local/pgdata` para solucionar errores: contiene la base de datos. Detener el entorno conserva sus datos. No hay inicio automático al reiniciar Windows.

## Preparar una nueva copia

Ejecutar desde la raíz del proyecto:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
```

Si Python está en otra ubicación:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1 -PythonPath 'C:\ruta\python.exe'
```

El script crea el entorno virtual cuando falta, instala las versiones fijadas, descarga los binarios de PostgreSQL desde EDB cuando faltan, genera `.env` sin sobrescribirlo, inicializa la base local y aplica migraciones. Necesita conexión a Internet para las descargas iniciales. `ExecutionPolicy Bypass` solo se aplica al proceso iniciado; no cambia la política global de PowerShell.

PostgreSQL escucha en `127.0.0.1:5433`, la base se llama `sicfe_dev` y la cuenta de aplicación es `sicfe_app`. Se exige contraseña con SCRAM. La cuenta de aplicación no es superusuario ni puede crear roles o bases. `sicfe_admin` se usa exclusivamente para preparar la instancia y ejecutar las pruebas locales.

## Iniciar y detener

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start-dev.ps1
```

- Página inicial: http://127.0.0.1:8000/
- Administración: http://127.0.0.1:8000/admin/
- Comprobación de base de datos: http://127.0.0.1:8000/health/

La comprobación devuelve `{"status":"ok"}` con HTTP 200 cuando puede consultar PostgreSQL y HTTP 503 cuando la conexión falla. No expone credenciales ni detalles internos del error.

Para terminar el servidor web, presionar `Ctrl+C` en su terminal. Para detener la base de datos:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/stop-db.ps1
```

## Crear el primer administrador

Con PostgreSQL en marcha:

```powershell
.\.venv\Scripts\python.exe manage.py createsuperuser
```

El comando pide nombre de usuario y contraseña de forma interactiva. No se incluye una contraseña de administrador predeterminada. El superusuario configura usuarios y asigna los perfiles iniciales del SICFE; las bodegas y accesos están disponibles en Administración. Consulta `06_Primera_entrega_operativa.md` para el flujo completo.

## Verificar

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check.ps1
```

Comprueba dependencias, análisis de código, formato, configuración Django, migraciones pendientes y pruebas. Las pruebas crean y eliminan únicamente la base `test_sicfe_dev`, separada de `sicfe_dev`, usando `config.test_settings`. Esta configuración es exclusivamente local.

Para trabajar con Django no es necesario activar el entorno virtual; se puede usar directamente `.\.venv\Scripts\python.exe manage.py ...`.

### Verificación inicial — 8 de septiembre de 2026

Entorno instalado con Python 3.14.6, Django 5.2.17 y PostgreSQL 17.11. Se aplicaron las 18 migraciones iniciales de Django. Pasaron la revisión de dependencias, Ruff, formato, comprobaciones Django y las cuatro pruebas automatizadas contra una base PostgreSQL temporal.

También se inició Django temporalmente en `127.0.0.1:8000`: la página inicial y el formulario de administración respondieron HTTP 200, y `/health/` confirmó conexión a PostgreSQL. El servidor web de verificación se detuvo al terminar; PostgreSQL quedó iniciado. Para abrir la aplicación, ejecutar `scripts/start-dev.ps1`.

## Alcance de esta base

La base técnica se amplió con autenticación de usuarios, perfiles, permisos por bodega y los primeros módulos de existencias. La entrega operativa y sus 31 pruebas se documentan en `06_Primera_entrega_operativa.md`. La integración con AVIS continúa pendiente.

El servidor `runserver` y `DEBUG=True` corresponden al desarrollo. El despliegue institucional necesitará configuración propia y los controles definidos en la arquitectura.

## Problemas frecuentes

- **`py` dice que no hay Python:** el lanzador antiguo puede no reconocer la instalación disponible. `setup.ps1` busca el Python 3.14 instalado por el administrador de Python; también permite indicar `-PythonPath`.
- **Puerto 5433 ocupado:** detener este PostgreSQL si está activo, elegir un puerto local libre en `.env` y volver a iniciar. No detener procesos ajenos al proyecto.
- **Puerto 8000 ocupado:** ejecutar manualmente `manage.py runserver 127.0.0.1:8001` y usar esa dirección.
- **Fallo de contraseña:** revisar `.env`. Cambiar ese archivo no cambia las contraseñas de una base ya inicializada; no regenerarlo como reparación automática.
- **PostgreSQL no inicia:** consultar `.local/postgres.log` y ejecutar `.runtime\pgsql\bin\postgres.exe --version` para comprobar los binarios.
