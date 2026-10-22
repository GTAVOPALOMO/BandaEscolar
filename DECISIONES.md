# Decisiones técnicas y de negocio

## Integridad financiera

- El crédito se deriva de `pago vigente - asignaciones vigentes`; no hay un saldo mutable independiente que pueda desincronizarse.
- Una reconstrucción invalida asignaciones anteriores de forma trazable y crea nuevas asignaciones deterministas: pagos por fecha/ID y cuotas por año/mes/ID.
- Al retirar a un estudiante solo se liberan las asignaciones de las cuotas convertidas a `SIN_CARGO_POR_RETIRO`. No se trasladan silenciosamente a deudas anteriores en ese acto. Al reingresar o crear una cuota nueva, todo crédito disponible vuelve a aplicarse por antigüedad.
- Los importes son enteros positivos en CRC. El saldo inicial puede ser cero. El saldo de caja se deriva de movimientos append-only y el resumen del cierre queda congelado.
- Las operaciones combinadas usan `transaction.atomic()`. PostgreSQL bloquea la caja, el estudiante o el evento antes de modificar flujos relacionados; esto serializa saldos, reasignaciones de cuotas y el precio usado en una venta. Las claves idempotentes y fuentes de movimientos siguen teniendo unicidad en base de datos.
- En PostgreSQL, `select_for_update()` protege pagos, caja, cuotas y tickets. La validación de ticket vuelve a consultar el token después de adquirir el bloqueo y conserva además una actualización condicional `estado=VÁLIDO`. En desarrollo, SQLite mantiene `transaction_mode=IMMEDIATE` y `timeout=20` como alternativa local.
- Los intentos concurrentes de abrir caja o crear pagos/ventas con el mismo token transforman la restricción única en el resultado de negocio esperado, sin duplicar dinero. La auditoría continúa dentro de la misma transacción que la operación registrada.

## Fechas y cuotas

- Un período activo cobra el mes de inicio completo y excluye por completo el mes de retiro. Un reingreso en el mismo mes reactiva la única cuota existente.
- La primera tarifa exige un mes histórico explícito, se normaliza al día 1 y no puede comenzar después del mes actual. Toda decisión posterior se fija en el servidor al primer día del mes siguiente según `America/Costa_Rica`; el cliente no decide esa fecha.
- Las tarifas son decisiones versionadas. Si se sustituye una programación del mismo mes, la versión anterior pasa a `SUSTITUIDA` y la nueva referencia a la anterior; no se sobrescribe ni se borra el registro. Una restricción parcial permite una sola versión activa por mes y otra restricción garantiza una única decisión inicial.
- Solo puede cancelarse una tarifa activa cuya vigencia aún no comenzó, con un motivo obligatorio y una tarifa anterior que continúe vigente. La cancelación se rechaza si ya existen cuotas materializadas en el intervalo que esa tarifa cubriría. La versión queda como `CANCELADA` y puede registrarse una nueva decisión para el mismo mes.
- Las cuotas almacenan su `original_amount` al crearse. Sustituir o cancelar una decisión nunca recalcula cuotas existentes ni modifica pagos, asignaciones o movimientos de caja.
- La sincronización ocurre en paneles/estados y antes de registrar pagos; el calendario público nunca la ejecuta.

## Seguridad y archivos

- Las imágenes se validan por extensión, tamaño máximo de 4 MiB y decodificación con Pillow. En Vercel se guardan en el bucket privado `eventos` de Supabase Storage. La vista limitada al ID de un evento activo genera una URL firmada de corta duración; no expone el bucket.
- Los PDF financieros y de tickets se generan bajo autorización y nunca se guardan en rutas públicas.
- La protección de login bloquea un usuario durante 15 minutos después de ocho fallos recientes. No requiere Redis ni procesos auxiliares.
- El lector usa una copia local fijada de `qr-scanner` 1.4.2 (MIT), que aprovecha `BarcodeDetector` cuando existe y usa su worker local como respaldo; siempre existe captura manual del código visible. No depende de una CDN en producción. Conviene probar cámara y permisos HTTPS en los teléfonos reales antes del evento.

## Alcance operativo

- No se expone edición directa de pagos, caja o auditoría en Django Admin. Las correcciones pasan por servicios y contramovimientos.
- La anulación de tickets no devuelve dinero automáticamente. Si corresponde, el comité registra un egreso manual, preservando la política explícita.
- El sistema de archivos de Vercel se considera efímero. PostgreSQL y Supabase Storage son obligatorios allí; `/tmp` solo se usa como espacio temporal.
- No se ejecutó una conexión real a Supabase Storage/PostgreSQL ni un despliegue real en Vercel porque no se proporcionaron credenciales. Sí se aplicaron desde cero todas las migraciones y se ejecutó la suite contra PostgreSQL 16 local desechable, además de verificar la configuración resultante, los estáticos y SQLite local.
