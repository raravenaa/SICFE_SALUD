# Arquitectura y datos — propuesta 0.1

## 1. Arquitectura propuesta

Aplicación web modular con servidor único y PostgreSQL. Esta organización mantiene juntas las transacciones de stock, valorización y auditoría, y permite separar módulos sin introducir servicios distribuidos desde el inicio.

Tecnología adoptada para el entorno de desarrollo: Django 5.2 LTS para lógica de negocio, autenticación y acceso a datos; páginas renderizadas en el servidor para la interfaz inicial; PostgreSQL 17.11 para persistencia y Python 3.14. Las dependencias exactas están fijadas en `requirements.txt`. El despliegue institucional continúa pendiente de definición.

Módulos: identidad y permisos, catálogo, bodegas, movimientos, inventarios físicos, valorización, reportes y auditoría.

La interfaz enviará solicitudes al servicio de aplicación. Ese servicio validará permisos y reglas y realizará las operaciones en PostgreSQL. Ocultar un botón nunca será el único control de autorización.

## 2. Modelo lógico inicial

| Entidad | Información principal | Control relevante |
|---|---|---|
| Usuario / perfil | Identidad, estado, roles | Contraseñas gestionadas por el framework |
| Acceso a bodega | Usuario, bodega, alcance | Validación en cada operación |
| Producto | Código, nombre, unidad, categoría, estado | Código único; desactivación sin borrar historia |
| Bodega | Código, nombre, estado | Código único |
| Lote | Producto, código de lote, vencimiento | Identidad interna; detección de datos contradictorios |
| Saldo de lote | Lote, bodega, cantidad, bloqueo y motivo | Una fila por lote y bodega; cantidad no negativa |
| Movimiento | Tipo, bodega, estado, fechas, autor, referencia, motivo | Confirmación única; autor obligatorio |
| Detalle de movimiento | Producto, cantidad, costo aplicado, valor aplicado | Cantidad positiva; costo decimal |
| Asignación de lote | Detalle, lote, cantidad | Mismo producto que el detalle; suma igual a cantidad del detalle |
| Saldo | Producto, bodega, cantidad, valor | Una fila por producto y bodega; bloqueo transaccional |
| Sesión de inventario | Bodega, corte, estado, responsables | Un corte explícito |
| Conteo | Sesión, producto, lote, saldo al corte, cantidad física | Diferencia calculada por lote; ajuste vinculado |
| Evento de auditoría | Actor, instante, acción, entidad, cambios, identificador de solicitud | Sin edición desde la aplicación |

El control por lote y vencimiento fue confirmado por el usuario el 8 de septiembre de 2026 y forma parte del modelo inicial. Se separará el stock físico por lote del costo promedio propuesto por producto y bodega. Seleccionar un lote no cambiará la fórmula de costo promedio.

Un mismo lote podrá tener existencias en varias bodegas. Su código no será único globalmente: distintos productos pueden compartir el texto del lote. Para un producto, una coincidencia de código con vencimientos diferentes requerirá revisión antes de crear o modificar el registro. Debe validarse si se necesita fabricante para identificar el lote sin ambigüedad.

El vencimiento de un lote con movimientos no se modificará desde el mantenimiento ordinario. Una corrección deberá preservar el valor anterior, su motivo y el responsable en auditoría. Bloquear o desbloquear existencias también tendrá permiso específico y auditoría.

## 3. Confirmación transaccional

1. Autenticar al usuario y comprobar permisos de acción y bodega.
2. Abrir transacción y bloquear el movimiento; si está confirmado, devolver el resultado ya registrado.
3. Crear de forma segura los saldos que no existan y bloquear primero los saldos por producto y después los saldos por lote, en orden consistente, para reducir bloqueos cruzados.
4. Validar todas las líneas y sus asignaciones, agrupando cantidades por producto y lote para comprobar disponibilidad total y por lote. Comprobar pertenencia del lote al producto y bodega y evaluar vencimiento y bloqueo dentro de la transacción según la política acordada.
5. Calcular los costos y valores con aritmética decimal según la política acordada.
6. Guardar detalles valorizados y asignaciones de lote, actualizar saldos agregados y por lote, confirmar movimiento y registrar auditoría.
7. Confirmar toda la transacción. Ante cualquier error, revertir todos sus cambios.

El identificador de solicitud tendrá unicidad para prevenir duplicados durante reintentos de creación. Las restricciones de base de datos respaldarán las validaciones del servicio.

## 4. Integridad y consulta histórica

Los movimientos confirmados constituyen el registro de referencia. La tabla de saldos facilita consultas y se reconciliará con el historial. Los reportes históricos se calcularán con movimientos confirmados hasta el corte solicitado, no con saldos actuales.

Guardar fecha efectiva y fecha real de registro permite identificar cuándo ocurrió una operación y cuándo fue incorporada. La primera entrega bloqueará retroactividad que exija recalcular costos. La política de períodos cerrados se debe acordar con Contabilidad.

Se almacenarán instantes con zona horaria y se presentarán en la zona institucional. Los costos y cantidades usarán tipos decimales, con precisión por definir según unidades y moneda.

## 5. Operación y seguridad

Separar desarrollo, pruebas y producción. Las credenciales se configurarán fuera del código. Producción requerirá HTTPS, control de sesiones, protección CSRF, validación de entradas y registro de fallos de acceso sin guardar contraseñas ni secretos.

La cuenta de aplicación tendrá privilegios limitados. La auditoría básica protege la trazabilidad a nivel de aplicación; no equivale a un registro inviolable frente a administradores de base de datos. Una necesidad de evidencia con protección adicional deberá especificarse.

Se definirán frecuencia y retención de respaldos, responsables, tiempo objetivo de recuperación y pérdida máxima aceptable de datos. Se probará la restauración antes del piloto.

Las exportaciones Excel escribirán entradas del usuario como texto para evitar interpretarlas como fórmulas y respetarán los permisos de costos y bodegas.

## 6. AVIS

Primero se requiere una muestra anonimizada del formato de exportación o documentación de una interfaz autorizada. El diseño de integración deberá incluir identificadores de origen, prevención de duplicados, validación de códigos y unidades, vista previa de errores y conciliación de totales. No se asume sincronización automática ni escritura en AVIS.
