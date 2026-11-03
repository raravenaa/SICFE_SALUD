# Alcance y requisitos — borrador 0.1

## 1. Requisitos expresados en la visión

SICFE será una plataforma independiente de control, trazabilidad, valorización y fiscalización. No reemplazará inicialmente AVIS. CAS-CHILE queda fuera del alcance inicial. La base de datos será PostgreSQL y las reglas de negocio estarán centralizadas.

La primera versión comprende autenticación, productos, movimientos, stock, valorización por costo promedio, reportes Excel, auditoría básica y dashboard ejecutivo. Debe permitir una futura expansión a otras bodegas.

## 2. Propuesta de funcionamiento

El usuario confirmó el 8 de septiembre de 2026 que la primera versión debe controlar medicamentos por lote y fecha de vencimiento. Las demás reglas propuestas a continuación requieren validación operativa.

### Lotes y vencimientos

Cada ingreso y saldo inicial de medicamentos deberá identificar producto, lote, vencimiento y cantidad. Las salidas y ajustes conservarán la referencia al lote afectado. El inventario físico y las consultas de stock se desglosarán por producto, bodega y lote.

Propuestas para la implementación: sugerir primero los lotes que vencen antes (FEFO), excluir lotes vencidos o bloqueados de las salidas de uso y mostrar alertas configurables de próximos vencimientos. Estas reglas adicionales no se consideran aprobadas por la confirmación del control por lote.

El stock físico incluirá las unidades vencidas o bloqueadas mientras permanezcan en bodega; el stock disponible las excluirá. El vencimiento no eliminará existencias ni generará una baja automática. Su retiro requerirá un movimiento autorizado y trazable.

La fecha de vencimiento se registrará como fecha, sin hora. Falta acordar cómo interpretar etiquetas que solo indiquen mes y año y cuándo deja de estar disponible el lote. No se inventarán fechas para completar datos faltantes: los registros incompletos quedarán pendientes de revisión.

### Catálogo de productos

Cada producto tendrá código interno único, nombre, unidad base de medida, categoría y estado activo/inactivo. El código AVIS será una referencia opcional; no supone una integración disponible.

Los productos con movimientos no se eliminarán. Se desactivarán para conservar su historia. Las cantidades se registrarán en una unidad base; las conversiones de cajas a unidades requieren una equivalencia explícita y validada.

### Bodegas y ubicaciones

La primera implementación podrá operar con una bodega, pero el modelo admitirá varias. Un usuario deberá tener autorización sobre la bodega en la que registra operaciones.

### Movimientos

Tipos propuestos: saldo inicial, ingreso, salida, ajuste positivo y ajuste negativo. Transferencias, devoluciones e importación AVIS se especificarán antes de habilitarlas.

Cada movimiento incluirá bodega, fecha efectiva, fecha de registro, usuario, motivo, referencia documental y líneas de productos. Los ingresos incluirán costo unitario. El sistema calculará el costo de las salidas.

Flujo propuesto: borrador → confirmado. Confirmar actualizará stock, valorización y auditoría en una sola transacción. Un movimiento confirmado no se editará ni eliminará: su corrección necesitará un movimiento compensatorio con referencia al original y validación de su efecto en costos.

Se propone impedir stock negativo, cantidades no positivas, confirmaciones duplicadas y operaciones sobre productos inactivos. En la primera entrega no se permitirá insertar movimientos retroactivos que alteren una secuencia ya valorizada.

### Stock e inventario físico

El stock se consultará por producto, bodega y lote, mostrando vencimiento, cantidad física y cantidad disponible. Se conservará el historial que explica cada saldo. Los conteos y diferencias identificarán cada lote.

Una sesión de inventario contendrá saldo del sistema al corte, cantidad contada, diferencia, responsable y observaciones. Las diferencias se revisarán antes de generar ajustes. Se propone detener movimientos de la bodega durante el conteo para evitar comparar saldos de momentos distintos; si esto no es viable, habrá que diseñar conciliación al corte.

### Valorización

Propuesta pendiente de aprobación: costo promedio móvil por producto y bodega.

En un ingreso, siendo Q la cantidad previa, V el valor previo, q la cantidad recibida y c su costo unitario:

`Cantidad nueva = Q + q`

`Valor nuevo = V + (q × c)`

`Costo promedio nuevo = Valor nuevo / Cantidad nueva`

En una salida, se descontará su cantidad al costo promedio anterior. Si se agota completamente el stock, se descontará todo el valor residual para dejar cantidad y valor en cero. No se utilizarán números de punto flotante para importes.

Ejemplo: 100 unidades a $1.000 suman $100.000. Un ingreso de 50 unidades a $1.300 agrega $65.000. El saldo será de 150 unidades, con valor de $165.000 y promedio de $1.100. Una salida de 20 unidades deja 130 unidades y $143.000.

Falta definir moneda, inclusión de impuestos, precisión, redondeo, costos de ajustes positivos y tratamiento de devoluciones. Los ajustes negativos se proponen al promedio vigente. El saldo inicial necesita cantidad y valor validados institucionalmente.

### Reportes y dashboard

Exportación Excel: existencias, kardex por producto, valorización y diferencias de inventario. Filtros por bodega, producto y período, cuando correspondan. Cada reporte indicará fecha de generación y alcance de los filtros.

Dashboard propuesto: valor total de existencias, productos sin stock, ingresos y salidas del período, diferencias pendientes de revisión y lotes próximos a vencer o vencidos con existencias. Los umbrales de alertas serán configurables y requieren definición. Los reportes de existencias y kardex incluirán lote y vencimiento y permitirán filtrar por lote.

## 3. Permisos propuestos

| Operación | Administrador | Operador | Contabilidad | Auditor | Dirección |
|---|---|---|---|---|---|
| Usuarios, perfiles y configuración | Sí | No | No | Consulta de auditoría | No |
| Mantener productos | Sí | Por validar | No | No | No |
| Registrar ingresos y salidas | No por defecto | Sí | No | No | No |
| Consultar stock | Sí | Sí | Sí | Sí | Resumen |
| Consultar costos y valorización | Por validar | Por validar | Sí | Sí | Resumen |
| Aprobar ajustes | Por definir | No por defecto | Por definir | No | No |
| Consultar auditoría | Sí | No | No | Sí | No |
| Exportar reportes | Según permisos | Según permisos | Sí | Sí | Resumen |

Administración técnica no implica permiso automático para operar existencias. La aprobación de ajustes requiere un responsable designado y, como propuesta, una persona distinta de quien los registra.

## 4. Criterios de aceptación

1. Una persona sin autenticación no puede consultar ni modificar información.
2. Un usuario con perfil de consulta no puede crear movimientos ni mediante la interfaz ni mediante solicitudes directas al servidor.
3. Confirmar un ingreso incrementa cantidad y valor y deja identificado a su autor.
4. Una salida superior al saldo se rechaza sin cambios parciales.
5. Dos salidas simultáneas no pueden consumir las mismas existencias.
6. Repetir la solicitud de confirmación no duplica el movimiento.
7. El ejemplo de costo promedio de este documento produce exactamente los saldos indicados.
8. Un movimiento confirmado conserva sus datos originales después de una corrección.
9. Un ajuste de inventario requiere motivo y la autorización que se acuerde.
10. Stock, kardex y valorización coinciden para el mismo corte.
11. Los reportes respetan los permisos de quien los solicita.
12. Una restauración de respaldo se verifica antes del uso institucional.
13. Un ingreso de medicamentos sin lote o vencimiento no se puede confirmar.
14. Cada salida identifica los lotes y cantidades utilizados; no puede consumir más que el saldo de cada lote aunque el producto tenga saldo suficiente en otros lotes.
15. La suma de cantidades por lote coincide con el saldo del producto en cada bodega.
16. Un conteo permite registrar diferencias independientes para dos lotes del mismo producto.
17. El kardex permite reconstruir los ingresos, salidas y ajustes de un lote.

## 5. Límites y decisiones pendientes

No se presupone acceso a API, archivos o base de datos de AVIS. Debe acordarse qué información ingresará a SICFE y quién conciliará ambos sistemas, para evitar duplicar registros sin control.

No se propone almacenar pacientes ni recetas en esta etapa. Si se requiere información clínica, cambiarán el alcance y los controles necesarios.

El control por lote y vencimiento está confirmado para medicamentos. Queda por definir si también será obligatorio para insumos y otros productos, y validar las reglas propuestas de disponibilidad, FEFO y alertas.
