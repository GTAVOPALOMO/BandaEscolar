# Plan de implementación

- [x] Crear configuración Django, modelos, restricciones y migraciones.
- [x] Implementar servicios transaccionales de auditoría, cuotas, pagos, caja y tickets.
- [x] Añadir autenticación, permisos por rol, formularios y pantallas móviles.
- [x] Generar PDFs privados y QR individuales; lector local con cámara y código manual.
- [x] Cubrir invariantes y criterios de aceptación con pruebas automatizadas.
- [x] Preparar Vercel, PostgreSQL/Supabase Storage, recuperación, documentación y verificaciones finales.

## Estado comprobado

- Configuración Vercel validada automáticamente: exige `DATABASE_URL`, selecciona PostgreSQL, SSL, conexiones no persistentes, prepared statements desactivados, cursores del servidor desactivados y bucket privado lógico `eventos` con enlaces firmados.
- Suite Django completa: 37 pruebas en verde tanto con SQLite como con PostgreSQL 16 local desechable. Todas las migraciones se aplicaron desde cero en PostgreSQL. `check --deploy` no produjo advertencias con variables equivalentes a producción; `makemigrations --check --dry-run` no detectó cambios y `collectstatic` generó 136 archivos (408 postprocesados).
- La instalación reproducible y la compilación de estáticos también finalizaron correctamente dentro de una imagen limpia de Python 3.13.
- SQLite continúa cubierto como desarrollo local, pero `backup_data` rechaza explícitamente PostgreSQL.
- Pendiente manual externo: crear/configurar Supabase y Vercel, ejecutar migraciones y administrador inicial desde un proceso externo, comprobar conexión real, persistencia del bucket y cámara HTTPS en teléfonos reales.
