# Decisiones técnicas y de negocio

## Integridad financiera

- El crédito se deriva de `pago vigente - asignaciones vigentes`; no hay un saldo mutable independiente que pueda desincronizarse.
- Una reconstrucción invalida asignaciones anteriores de forma trazable y crea nuevas asignaciones deterministas: pagos por fecha/ID y cuotas por año/mes/ID.
- Al retirar a un estudiante solo se liberan las asignaciones de las cuotas convertidas a `SIN_CARGO_POR_RETIRO`. No se trasladan silenciosamente a deudas anteriores en ese acto. Al reingresar o crear una cuota nueva, todo crédito disponible vuelve a aplicarse por antigüedad.
- Los importes son enteros positivos en CRC. El saldo inicial puede ser cero. El saldo de caja se deriva de movimientos append-only y el resumen del cierre queda congelado.
- Las operaciones combinadas usan `transaction.atomic()`. SQLite usa `transaction_mode=IMMEDIATE` y `timeout=20`; además hay unicidad de tokens y fuentes de movimientos. Railway debe ejecutar una sola réplica.
- `select_for_update()` no se considera suficiente en SQLite: la validación de ticket usa además una actualización condicional `estado=VÁLIDO`, y las operaciones monetarias tienen claves idempotentes únicas.

## Fechas y cuotas

- Un período activo cobra el mes de inicio completo y excluye por completo el mes de retiro. Un reingreso en el mismo mes reactiva la única cuota existente.
- La primera tarifa puede indicar un mes histórico explícito, necesario para una matrícula retroactiva. Toda decisión posterior se fija al primer día del mes siguiente. Varias decisiones para el mismo mes actualizan esa versión y cada decisión queda auditada.
- La sincronización ocurre en paneles/estados y antes de registrar pagos; el calendario público nunca la ejecuta.

## Seguridad y archivos

- Las imágenes se validan por extensión, tamaño y decodificación con Pillow. En producción se entregan desde una vista pública limitada al ID de un evento activo; no se expone todo el volumen.
- Los PDF financieros y de tickets se generan bajo autorización y nunca se guardan en rutas públicas.
- La protección de login bloquea un usuario durante 15 minutos después de ocho fallos recientes. No requiere Redis ni procesos auxiliares.
- El lector usa una copia local fijada de `qr-scanner` 1.4.2 (MIT), que aprovecha `BarcodeDetector` cuando existe y usa su worker local como respaldo; siempre existe captura manual del código visible. No depende de una CDN en producción. Conviene probar cámara y permisos HTTPS en los teléfonos reales antes del evento.

## Alcance operativo

- No se expone edición directa de pagos, caja o auditoría en Django Admin. Las correcciones pasan por servicios y contramovimientos.
- La anulación de tickets no devuelve dinero automáticamente. Si corresponde, el comité registra un egreso manual, preservando la política explícita.
- No se ejecutó un despliegue real en Railway porque no se proporcionaron credenciales. La persistencia se verifica localmente y queda documentado el control manual del volumen.
