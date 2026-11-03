# Plan de desarrollo — borrador 0.1

## Entregas propuestas

| Entrega | Resultado verificable | Dependencias |
|---|---|---|
| 1. Definición | Alcance, reglas y modelo revisados con responsables | Decisiones operativas de este documento |
| 2. Base técnica | Proyecto ejecutable, PostgreSQL, acceso y permisos | Entorno y tecnología definidos |
| 3. Operación mínima | Catálogo, lotes, vencimientos, ingresos, salidas, stock y costo promedio | Unidad de medida, reglas de disponibilidad y política de costo |
| 4. Control de inventario | Conteos, revisión de diferencias, ajustes y auditoría | Responsables y flujo de aprobación |
| 5. Información de gestión | Excel, kardex, valorización y dashboard | Definición de indicadores y permisos |
| 6. Piloto | Carga inicial conciliada, capacitación y restauración probada | Validación funcional y entorno institucional |
| 7. Integraciones | Intercambio validado con sistemas existentes | Acceso autorizado y formatos disponibles |

La primera versión de la visión se completa con las entregas 2 a 5 y su validación en el piloto. Integraciones corresponden a una fase posterior. No se fijan plazos hasta conocer equipo, infraestructura y alcance operativo.

## Decisiones que afectan la implementación

1. ¿Se gestionarán solo medicamentos, o también insumos y otros productos?
2. ¿Cuántas bodegas y usuarios participarán en el piloto?
3. Confirmado el 8 de septiembre de 2026: control por lote y vencimiento para medicamentos desde la primera versión. Falta validar FEFO, bloqueo de salidas por vencimiento, umbrales de alerta y etiquetas con solo mes y año.
4. ¿Los movimientos se ingresarán manualmente, se importarán desde AVIS o se combinarán ambas vías? ¿Qué sistema será la referencia de cada dato?
5. ¿Quién autoriza los ajustes y cómo se separará esa función del registro?
6. ¿Qué moneda, impuestos, precisión y redondeo se utilizarán? ¿El promedio se calculará por bodega o para toda la institución?
7. ¿Dónde se alojará la aplicación y quién administrará usuarios y respaldos?
8. ¿Existe una nómina de productos y un inventario inicial con cantidades y costos revisados?

## Primera iteración de programación

Preparar el proyecto y configuración PostgreSQL; incorporar autenticación, roles y acceso por bodega; crear catálogo, lotes y formularios de movimientos con asignación de lotes; implementar confirmación transaccional y consulta de stock por lote y vencimiento.

La iteración debe incluir pruebas de permisos, concurrencia, prevención de duplicados, costo promedio y reversión completa ante errores. Usará datos ficticios hasta contar con una carga institucional validada.

Verificar también que salidas simultáneas no produzcan saldo negativo por lote, que la suma de lotes coincida con el total del producto y que los ingresos sin lote o vencimiento sean rechazados. Las pruebas de FEFO y de exclusión de vencidos se incorporarán al adoptar esas reglas.

## Escenario de demostración

Crear una bodega y un producto ficticio. Registrar 100 unidades a $1.000 y 50 a $1.300. Verificar 150 unidades valorizadas en $165.000. Registrar una salida de 20 y comprobar 130 unidades y $143.000. Intentar retirar 131 y comprobar rechazo sin modificar saldo. Consultar quién registró cada operación y exportar el kardex cuando esté disponible el módulo Excel.

Asignar el primer ingreso al lote DEMO-A con vencimiento 2027-06-30 y el segundo al lote DEMO-B con vencimiento 2027-12-31. Realizar la demostración con fecha operativa anterior a ambos vencimientos. La salida de 20 unidades del lote DEMO-A debe dejar 80 en DEMO-A y 50 en DEMO-B. Intentar sacar 81 de DEMO-A debe fallar aunque el producto conserve 130 unidades totales. Consultar el historial de cada lote.

## Estado de esta entrega

Se implementó la primera iteración de programación: autenticación, cinco perfiles iniciales y accesos por bodega; catálogo; lotes y vencimientos; saldos iniciales, ingresos y salidas; confirmación transaccional; stock y costo promedio. También se adelantaron kardex y auditoría básica. Las 31 pruebas automatizadas pasan sobre PostgreSQL, incluidas concurrencia y protección de historial. Las reglas adoptadas para desarrollo y sus límites están en `06_Primera_entrega_operativa.md`.

La siguiente entrega es el control de inventario físico: sesiones de conteo, captura por lote, diferencias, revisión y ajustes con autorización. Antes de habilitar ajustes hay que definir sus responsables y completar las correcciones auditadas. Después siguen Excel y dashboard, validación del piloto e integraciones. El despliegue institucional continúa pendiente.
