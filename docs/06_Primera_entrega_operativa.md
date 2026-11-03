# Primera entrega operativa

## Qué está disponible

La aplicación permite iniciar sesión, administrar el catálogo de productos, registrar saldos iniciales, ingresos y salidas con varias líneas de lotes, confirmar movimientos y consultar existencias y kardex. La configuración de bodegas y accesos se realiza desde Administración.

Cada movimiento pasa por borrador y confirmación. Un borrador no modifica existencias; se puede cancelar. Confirmar actualiza cantidades, valores y auditoría en una única transacción. Los movimientos cerrados y sus líneas tienen protección contra modificación y eliminación en PostgreSQL, además de no tener pantallas de edición.

Hay cinco perfiles iniciales y permisos por bodega. Ningún usuario ordinario obtiene acceso a todas las bodegas por pertenecer a un grupo. El superusuario de instalación tiene acceso completo explícitamente y debe reservarse para configuración y pruebas.

## Comenzar a usar la entrega

Las migraciones y los cinco grupos ya se aplicaron al entorno local de esta entrega. En otra copia, ejecutar primero:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
```

Crear un administrador si aún no existe:

```powershell
.\.venv\Scripts\python.exe manage.py createsuperuser
```

Iniciar el servidor:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start-dev.ps1
```

1. Entrar en `http://127.0.0.1:8000/admin/` con el superusuario.
2. Crear una bodega en **Existencias → Bodegas**.
3. Crear las cuentas de los participantes y asignarles los grupos adecuados. La gestión de identidades está reservada al superusuario en esta entrega.
4. Crear un **Acceso a bodega** por usuario y bodega. El permiso depende tanto del perfil como de este acceso.
5. Registrar productos desde **Productos → Nuevo producto**, con una cuenta autorizada para catálogo.
6. Entrar como operador por `http://127.0.0.1:8000/ingresar/`.
7. Abrir **Movimientos → Registrar movimiento**, completar bodega, referencia documental y motivo, y añadir una línea por producto y lote.
8. Guardar el borrador, revisar y pulsar **Confirmar y actualizar stock**.

No se crean cuentas con contraseñas predeterminadas ni se cargan existencias de demostración en la base de trabajo.

## Perfiles iniciales

| Perfil | Capacidades iniciales |
|---|---|
| Administrador | Mantener catálogo, configurar bodegas y accesos, consultar existencias, movimientos y auditoría |
| Operador | Consultar catálogo y existencias; registrar, confirmar y cancelar borradores en sus bodegas |
| Contabilidad | Consultar catálogo, stock, movimientos, kardex, costo promedio y valorización |
| Auditor | Consulta de catálogo, stock, movimientos, costos y auditoría |
| Dirección | Consulta de existencias y valorización; el dashboard ejecutivo resumido sigue pendiente |

Para acceder a la configuración de Django, el administrador debe tener también el atributo **Es staff**. Ese atributo por sí solo no concede permisos operativos. Los costos históricos se ocultan al operador; sí puede revisar el costo que ingresó en su propio borrador. Si debe consultar costos históricos, el superusuario puede asignar explícitamente el permiso correspondiente.

`bootstrap_roles` crea los grupos faltantes y conserva los permisos de grupos que ya existan. No asigna usuarios ni reemplaza ajustes institucionales.

## Reglas utilizadas para esta iteración

Estas decisiones permiten probar el sistema y todavía requieren validación institucional:

- Registro manual; sin conexión o importación desde AVIS.
- Cantidades expresadas en unidad base, con hasta tres decimales. No hay conversión automática de cajas a unidades.
- Valores expresados en CLP, con hasta seis decimales internos y redondeo de mitad hacia arriba. El costo ingresado es el costo final suministrado por el operador; no se calculan impuestos.
- Costo promedio móvil por producto y bodega. Seleccionar un lote no cambia el método de valorización. Al agotar un producto, se retira todo el valor residual.
- Lote y fecha completa de vencimiento obligatorios para todos los productos de esta iteración. Las fechas con solo mes y año deben aclararse antes del registro.
- Un lote se considera vencido cuando su fecha es anterior al día actual en Chile. Puede utilizarse durante la fecha indicada. La regla de disponibilidad debe validarse con el responsable antes del piloto.
- Las salidas de lotes vencidos se rechazan. Las cantidades vencidas permanecen en el stock físico y valorizado hasta implementar una baja autorizada.
- Las bodegas y productos inactivos no permiten nuevos movimientos ni aportan stock disponible.
- Existencias ordenadas por vencimiento y filtro de próximos 90 días. La selección de lotes es manual; no hay asignación FEFO automática ni alertas enviadas a terceros.
- Solo se confirman borradores con fecha efectiva del día actual. Los atrasados se cancelan y registran de nuevo; no hay recalculo retroactivo de costos.
- El saldo inicial se permite únicamente antes del primer movimiento confirmado de cada producto en esa bodega. Sus diferentes lotes deben registrarse juntos.
- Un movimiento admite hasta 50 líneas. Reenviar la misma solicitud o confirmar dos veces no duplica sus efectos.

## Trazabilidad y límites

El kardex muestra fecha, bodega, producto, lote, tipo, cantidad y saldo por producto después de cada línea. Los perfiles autorizados ven además los valores aplicados y saldos valorizados. Incluye solo movimientos confirmados.

La auditoría identifica creación, actualización de catálogo, creación de borradores, confirmaciones y cancelaciones. La configuración de usuarios, bodegas y accesos conserva el historial propio de Django. La protección de historial en PostgreSQL no equivale a una garantía frente al propietario de la base, que puede modificar su esquema.

Los lotes registrados son inmutables en esta entrega. Una equivocación en su código o fecha requiere intervención de desarrollo revisada; cancelar un borrador no libera el código del lote. No se ha habilitado un procedimiento de corrección de lotes ni de movimientos confirmados. Usar datos ficticios durante estas pruebas.

Continúan pendientes: conteos físicos, revisión y aprobación de diferencias, ajustes y bajas, devoluciones, transferencias, bloqueo por cuarentena, correcciones auditadas, exportación Excel, filtros históricos por corte, dashboard ejecutivo, restauración de respaldos y conexión con AVIS.

## Validaciones

Las 31 pruebas automatizadas pasan contra PostgreSQL real en una base temporal separada. Cubren autenticación, permisos y aislamiento por bodega; formularios; costo promedio; saldos por lote; vencimientos; cancelaciones; reversión completa por errores; protección de historial; reintentos y concurrencia.

El ejemplo del plan produce 150 unidades y $165.000 después de ambos ingresos; una salida de 20 deja 130 unidades y $143.000. Dos salidas simultáneas de 7 sobre 10 unidades permiten solo una confirmación y dejan 3 unidades. Dos confirmaciones simultáneas de un ingreso actualizan stock una sola vez.

Las pruebas también verifican que un fallo al escribir auditoría revierte todos los cambios de stock. Pasaron las revisiones de dependencias, Ruff, formato, configuración Django y ausencia de cambios de modelos sin migración.

Se aplicaron las tres migraciones de inventario a `sicfe_dev` y se crearon los cinco grupos. Se comprobó además el ejemplo completo con la cuenta PostgreSQL `sicfe_app`, incluyendo escritura de auditoría; todos los registros temporales de esa comprobación se revirtieron al terminar.

Referencia técnica utilizada: [transacciones Django](https://docs.djangoproject.com/en/5.2/topics/db/transactions/) y [bloqueos select_for_update](https://docs.djangoproject.com/en/5.2/ref/models/querysets/#select-for-update). La implementación serializa operaciones dentro de cada bodega y bloquea productos en un orden consistente.
