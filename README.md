# Banda Escolar Esquipulas

Monolito Django 5.2 para calendario, matrícula, mensualidades, caja, tickets QR y auditoría de una banda escolar. Interfaz en español, importes enteros en CRC y zona horaria `America/Costa_Rica`.

## Desarrollo local

Requiere Python 3.11–3.14. No requiere Node, PostgreSQL ni Redis.

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Exporte las variables de `.env` en su shell (Django no carga archivos `.env` automáticamente) y ejecute:

```bash
python manage.py migrate
python manage.py create_initial_admin
python manage.py runserver
```

`create_initial_admin` lee `INITIAL_ADMIN_USERNAME` y `INITIAL_ADMIN_PASSWORD`, exige 12 caracteres y nunca reemplaza un administrador existente. El primer ingreso obliga a cambiar la contraseña.

Verificación completa:

```bash
DEBUG=1 python manage.py check
DEBUG=1 python manage.py test
DEBUG=1 python manage.py makemigrations --check --dry-run
```

La sincronización mensual es idempotente y también puede ejecutarse manualmente con `python manage.py sync_dues`.

Las dependencias están fijadas: Django para el monolito; Gunicorn y WhiteNoise para servir en producción; Pillow para validar imágenes; `qrcode` para los códigos; ReportLab para los PDF. Las otras entradas de `requirements.txt` fijan dependencias transitivas de esos paquetes para que la construcción sea reproducible.

## Guía rápida del comité

1. En **Cuentas**, cree al encargado y entregue una sola vez su contraseña temporal.
2. En **Tarifas**, registre la primera tarifa y su mes histórico. Luego, en **Estudiantes**, matricule y vincule al encargado.
3. En **Caja**, haga la primera apertura con el efectivo preexistente. Aperturas posteriores heredan el último cierre.
4. En el estudiante, use **Registrar abono**. El sistema aplica a la cuota más antigua y conserva el excedente como saldo a favor.
5. Para carga inicial, use **Perdonar/regularizar cuotas**, seleccione meses sin abonos y escriba el motivo. Esto no crea dinero en caja.
6. Cree un evento y habilite entradas con precio único. Con caja abierta use **Tickets → Nueva venta**, descargue el PDF y compártalo o imprímalo.
7. En la entrada seleccione el evento en **Validar ingreso**, active cámara o escriba el código, revise y confirme. La lectura sola no marca el ticket.
8. En **Caja**, revise el resumen, cierre y, cuando corresponda, abra el período siguiente. Los cierres históricos no se modifican.

## Docker

```bash
docker build -t banda-escolar .
docker volume create banda_data
docker run --rm -p 8000:8000 -v banda_data:/data \
  -e PORT=8000 -e SECRET_KEY='valor-largo-aleatorio' \
  -e ALLOWED_HOSTS=localhost -e DEBUG=0 -e DATA_DIR=/data -e SECURE_SSL_REDIRECT=0 \
  -e INITIAL_ADMIN_USERNAME=administrador \
  -e INITIAL_ADMIN_PASSWORD='clave-inicial-muy-segura' banda-escolar
```

`start.sh` crea directorios sin borrar datos, normaliza la propiedad del volumen y baja al usuario no privilegiado `app` antes de ejecutar migraciones y Gunicorn. La base queda en `/data/db.sqlite3` y las imágenes en `/data/media/events/`.

## Despliegue en Railway

1. Cree un proyecto y un servicio desde este repositorio. Railway detectará el `Dockerfile`.
2. Añada **un volumen** y móntelo exactamente en `/data`.
3. Mantenga **una sola réplica/instancia**. Varias instancias no pueden escribir de forma segura el mismo SQLite.
4. Configure `SECRET_KEY` aleatoria, `DEBUG=0`, `DATA_DIR=/data`, `ALLOWED_HOSTS=<dominio>.up.railway.app`, `CSRF_TRUSTED_ORIGINS=https://<dominio>.up.railway.app`, `SECURE_SSL_REDIRECT=1` y `SECURE_HSTS_SECONDS=31536000`.
5. Para el primer despliegue agregue temporalmente `INITIAL_ADMIN_USERNAME` e `INITIAL_ADMIN_PASSWORD` (mínimo 12 caracteres). Ingrese, cambie la clave y luego elimine esas dos variables.
6. Genere el dominio HTTPS, visite `/health/` y compruebe `{"status":"ok"}`. Luego cree una imagen de evento y un dato de prueba autorizado, reinicie/redeploy y confirme que ambos siguen presentes.

No se ejecutó el paso 6 en Railway desde este entorno: requiere la cuenta y el dominio del propietario.

### Costos

Use un solo servicio pequeño, una réplica y un volumen; no agregue base gestionada, Redis ni workers. El precio real depende del consumo y de las tarifas vigentes de Railway: revise **Usage** del proyecto y configure los límites/alertas de gasto disponibles para sostener el objetivo de menos de US$10/mes. No se garantiza un importe fijo.

## Backup y restauración

Active los backups del volumen que ofrezca Railway y mantenga además una copia fuera del proyecto. Un backup dentro del mismo volumen no protege contra borrar ese volumen.

Para una copia lógica consistente de SQLite, sin copiar a ciegas el archivo activo:

```bash
python manage.py backup_data --output /data/backups/db-$(date +%Y%m%d).sqlite3
tar -C /data -czf /data/backups/media-$(date +%Y%m%d).tgz media
```

Descargue ambos archivos a almacenamiento externo. Para restaurar: detenga el servicio o escálelo temporalmente a cero; conserve una copia del estado actual; coloque el `.sqlite3` verificado como `/data/db.sqlite3`; restaure `media/` manteniendo `/data/media/events/`; inicie una sola instancia; ejecute `python manage.py migrate`, `python manage.py check` y verifique login, caja, un PDF y una imagen. Nunca restaure mientras Gunicorn escribe.

## Módulos

- `accounts`: roles, cuentas, contraseñas temporales y límite de login.
- `students`: vínculos y períodos de matrícula/retiro/reingreso.
- `dues`: tarifas, cuotas, asignaciones, crédito, perdones, reversión y PDF.
- `cash`: períodos, movimientos append-only, cierre y arrastre.
- `events`: calendario público e imágenes validadas.
- `tickets`: venta presencial, QR/PDF, validación, anulación y reemplazo.
- `audit`: bitácora inmutable y consulta con filtros.

La única dependencia JavaScript vendorizada es `static/js/vendor/qr-scanner*`, versión 1.4.2 y licencia MIT incluida. Se fijó al commit `abcfe1bce2703721408d8ce7ebde94a359998506`; no se carga desde CDN.

Las decisiones abiertas y garantías de consistencia están en [DECISIONES.md](DECISIONES.md); el avance planificado está en [PLAN.md](PLAN.md).
