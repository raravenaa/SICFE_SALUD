# SICFE Salud

Sistema Integrado de Control y Fiscalización de Existencias.

## Estado

Primera entrega operativa disponible: autenticación, perfiles y accesos por bodega, productos, lotes, saldos iniciales, ingresos, salidas, stock, costo promedio, kardex, auditoría básica y conciliación de conteos desde Excel. Probada con PostgreSQL local. Sesiones de conteo, ajustes aprobados, exportación de reportes, dashboard e integración con AVIS continúan pendientes.

## Ejecutar en Windows

Desde esta carpeta, en PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start-dev.ps1
```

Abrir http://127.0.0.1:8000/. Detener Django con `Ctrl+C` y PostgreSQL con:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/stop-db.ps1
```

Para preparar una nueva copia del proyecto, ejecutar primero `scripts/setup.ps1`. Consulta la [guía del entorno de desarrollo](docs/05_Entorno_de_desarrollo.md) para configuración, pruebas y creación de un administrador.

Base de trabajo: `01_Visión_del_Proyecto_SICFE_v1.0.docx`, facilitado por el usuario. El documento expresa la visión; las propuestas de esta carpeta deben validarse antes de tratarse como requisitos definitivos.

## Documentación

- [Alcance y requisitos](docs/02_Alcance_y_requisitos.md)
- [Arquitectura y modelo de datos](docs/03_Arquitectura_y_datos.md)
- [Plan de desarrollo y validaciones](docs/04_Plan_de_desarrollo.md)
- [Entorno de desarrollo](docs/05_Entorno_de_desarrollo.md)
- [Primera entrega operativa: uso, permisos y límites](docs/06_Primera_entrega_operativa.md)

## Objetivo de la primera entrega funcional

Un usuario autorizado ya puede registrar productos, ingresar existencias, registrar salidas y consultar stock y valorización, con trazabilidad de cada operación. Se implementó el control por lote y fecha de vencimiento solicitado. El módulo Conciliar conteo compara un archivo `.xlsx` por bodega, producto y lote, incluyendo los lotes con stock omitidos; la carga no guarda el archivo ni modifica existencias. Las siguientes entregas incorporarán sesiones de conteo, revisión y ajustes, exportación de reportes y dashboard.

La entrega utiliza reglas iniciales documentadas para probar el flujo. Antes del piloto deben validarse la política de costos, permisos, vencimientos y conciliación con la operación institucional.
