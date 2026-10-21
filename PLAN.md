# Plan de implementación

- [x] Crear configuración Django, modelos, restricciones y migraciones.
- [x] Implementar servicios transaccionales de auditoría, cuotas, pagos, caja y tickets.
- [x] Añadir autenticación, permisos por rol, formularios y pantallas móviles.
- [x] Generar PDFs privados y QR individuales; lector local con cámara y código manual.
- [x] Cubrir invariantes y criterios de aceptación con pruebas automatizadas.
- [x] Preparar Docker/Railway, recuperación, documentación y verificaciones finales.

## Estado comprobado

- Suite Django completa: 32 pruebas en verde.
- `check --deploy` sin advertencias y migraciones sin cambios pendientes.
- Imagen Docker construida y arrancada con Gunicorn.
- Volumen `/data` probado en dos arranques: SQLite permaneció fuera de la imagen y conservó su checksum; el segundo arranque indicó que no había migraciones nuevas.
- `/health/` y calendario público respondieron HTTP 200 detrás de la cabecera proxy HTTPS.
- Pendiente manual externo: crear el servicio, volumen y dominio en la cuenta Railway del propietario, y probar permiso de cámara en los teléfonos reales del comité.
