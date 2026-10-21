# Banda Escolar Esquipulas

Monolito Django 5.2 para calendario, matrícula, mensualidades, caja, tickets QR y auditoría de una banda escolar. La interfaz está en español, los importes son enteros en CRC y la zona horaria es `America/Costa_Rica`.

## Desarrollo local

El despliegue usa Python 3.13 (fijado en `.python-version`). Para desarrollo, si no existe `DATABASE_URL`, Django usa SQLite y guarda las imágenes localmente.

```bash
python3.13 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Django no carga `.env` por sí mismo: exporte las variables necesarias en la shell. Luego ejecute:

```bash
DEBUG=1 python manage.py migrate
DEBUG=1 python manage.py create_initial_admin
DEBUG=1 python manage.py runserver
```

`create_initial_admin` lee `INITIAL_ADMIN_USERNAME` y `INITIAL_ADMIN_PASSWORD`, exige 12 caracteres y nunca reemplaza un administrador existente. El primer ingreso obliga a cambiar la contraseña.

Verificación local:

```bash
DEBUG=1 python manage.py check
DEBUG=1 python manage.py test
DEBUG=1 python manage.py makemigrations --check --dry-run
DEBUG=1 python manage.py collectstatic --noinput
```

La sincronización mensual es idempotente y también puede ejecutarse con `python manage.py sync_dues`.

## Supabase

### PostgreSQL

Use la cadena del **Transaction Pooler** de Supabase, normalmente en el puerto `6543`, como `DATABASE_URL`. La configuración obliga SSL, abre una conexión por solicitud (`CONN_MAX_AGE=0`), desactiva prepared statements de psycopg 3 y desactiva cursores del servidor, condiciones necesarias para el modo transaccional del pooler.

SQLite queda disponible solo cuando `DATABASE_URL` no está definida y nunca se acepta como persistencia en Vercel.

Para probar contra un PostgreSQL local sin TLS puede usarse `DATABASE_SSL_REQUIRE=0` únicamente junto con `DEBUG=1`. Producción rechaza expresamente esa combinación y siempre exige SSL.

### Storage

En Supabase Storage cree manualmente un bucket **privado** llamado exactamente `eventos`. En la configuración S3 de Storage genere un access key y secret key, y configure:

- `SUPABASE_S3_ENDPOINT_URL`: `https://<project-ref>.storage.supabase.co/storage/v1/s3`
- `SUPABASE_S3_ACCESS_KEY_ID`
- `SUPABASE_S3_SECRET_ACCESS_KEY`
- `SUPABASE_S3_REGION_NAME`: la región indicada por el proyecto
- `EVENT_IMAGE_URL_TTL`: duración del enlace firmado; el valor predeterminado es 300 segundos

No use las claves `anon` o `service_role` como credenciales S3. El bucket conserva sus objetos privados. La ruta pública `/eventos/<id>/imagen/` primero confirma que el evento está activo y después redirige a una URL S3 firmada temporalmente.

Las imágenes se limitan a 4 MiB para dejar margen al envoltorio multipart bajo el límite de 4.5 MB de una solicitud a Vercel. En producción no se guardan imágenes, bases de datos ni backups en el sistema de archivos efímero; `/tmp` se usa únicamente para archivos temporales de una invocación.

## Despliegue en Vercel

Vercel detecta `manage.py` y `config/wsgi.py`; no se incluye `vercel.json` ni un adaptador API. `.python-version` selecciona Python 3.13 y la integración de Django recopila y entrega los archivos estáticos durante la construcción.

1. Importe este repositorio en Vercel.
2. Configure el bucket privado `eventos` y las credenciales S3 descritas arriba.
3. Añada estas variables a Production (y Preview si allí se ejecutará la aplicación):
   - `SECRET_KEY`: valor largo, aleatorio y exclusivo.
   - `DEBUG=0`.
   - `DATABASE_URL`: Transaction Pooler de Supabase, puerto 6543.
   - `ALLOWED_HOSTS`: dominio de Vercel y cualquier dominio propio, separados por comas.
   - `CSRF_TRUSTED_ORIGINS`: los mismos orígenes completos con `https://`.
   - las cuatro variables `SUPABASE_S3_*`.
   - opcionalmente `EVENT_IMAGE_URL_TTL=300`.
4. Mantenga `SECURE_SSL_REDIRECT=1` y `SECURE_HSTS_SECONDS=31536000` en producción.
5. Despliegue y verifique `/health/`, inicio de sesión, una imagen de evento y los flujos financieros autorizados.

`DATABASE_URL` y Supabase Storage son obligatorios en producción, incluido Vercel. La aplicación falla al iniciar si faltan, evitando que una instancia parezca funcionar con datos efímeros.

### Migraciones y administrador inicial

No se ejecutan migraciones ni se crea un administrador durante las solicitudes HTTP, en `wsgi.py` ni en `start.sh`. Hágalo una sola vez desde una máquina confiable, un job manual de CI o un proceso administrativo externo con las mismas variables de producción:

```bash
export DEBUG=0
export DATABASE_URL='postgresql://...cadena-directa-o-session-pooler...'
export SECRET_KEY='...'
export SUPABASE_S3_ENDPOINT_URL='https://<project-ref>.storage.supabase.co/storage/v1/s3'
export SUPABASE_S3_ACCESS_KEY_ID='...'
export SUPABASE_S3_SECRET_ACCESS_KEY='...'
export SUPABASE_S3_REGION_NAME='...'
python manage.py migrate --noinput

export INITIAL_ADMIN_USERNAME='administrador'
export INITIAL_ADMIN_PASSWORD='una-clave-temporal-de-al-menos-12-caracteres'
python manage.py create_initial_admin
unset INITIAL_ADMIN_PASSWORD
```

Para tareas administrativas y `pg_dump`, prefiera la conexión directa de Supabase o su Session Pooler; no sustituya por error la `DATABASE_URL` de Vercel si esta debe seguir usando Transaction Pooler. Ejecute `showmigrations` antes y después de cada cambio. Elimine las variables del administrador una vez creado y cambie la contraseña en el primer ingreso.

## Backup y restauración

`python manage.py backup_data` respalda **únicamente SQLite local** mediante la API consistente de SQLite. El comando rechaza PostgreSQL y no debe presentarse como un backup de Supabase.

Para producción, active y verifique la política de backups de base de datos de Supabase. Si su plan y conectividad permiten una copia externa, use una URL directa o Session Pooler con las herramientas de PostgreSQL compatibles con la versión del servidor, por ejemplo:

```bash
pg_dump --dbname="$SUPABASE_DIRECT_DATABASE_URL" --format=custom --file=banda-escolar.dump
```

Pruebe la restauración en un proyecto separado antes de depender de ella. Los objetos del bucket `eventos` no forman parte de `pg_dump`; respáldelos aparte con una herramienta S3 compatible y el endpoint de Supabase. Nunca use `/tmp` de Vercel como destino de backup persistente.

Para SQLite local sí puede ejecutar:

```bash
DEBUG=1 python manage.py backup_data --output ./backups/db.sqlite3
```

## Guía rápida del comité

1. En **Cuentas**, cree al encargado y entregue una sola vez su contraseña temporal.
2. En **Tarifas**, registre la primera tarifa y su mes histórico. Luego, en **Estudiantes**, matricule y vincule al encargado.
3. En **Caja**, haga la primera apertura con el efectivo preexistente. Aperturas posteriores heredan el último cierre.
4. En el estudiante, use **Registrar abono**. El sistema aplica a la cuota más antigua y conserva el excedente como saldo a favor.
5. Para carga inicial, use **Perdonar/regularizar cuotas**, seleccione meses sin abonos y escriba el motivo. Esto no crea dinero en caja.
6. Cree un evento y habilite entradas con precio único. Con caja abierta use **Tickets → Nueva venta**, descargue el PDF y compártalo o imprímalo.
7. En la entrada seleccione el evento en **Validar ingreso**, active cámara o escriba el código, revise y confirme. La lectura sola no marca el ticket.
8. En **Caja**, revise el resumen, cierre y, cuando corresponda, abra el período siguiente. Los cierres históricos no se modifican.

## Módulos

- `accounts`: roles, cuentas, contraseñas temporales y límite de login.
- `students`: vínculos y períodos de matrícula/retiro/reingreso.
- `dues`: tarifas, cuotas, asignaciones, crédito, perdones, reversión y PDF.
- `cash`: períodos, movimientos append-only, cierre y arrastre.
- `events`: calendario público e imágenes validadas.
- `tickets`: venta presencial, QR/PDF, validación, anulación y reemplazo.
- `audit`: bitácora inmutable y consulta con filtros.

La copia vendorizada de `qr-scanner` es 1.4.2 (MIT), fijada al commit `abcfe1bce2703721408d8ce7ebde94a359998506`; no se carga desde CDN. Las decisiones de consistencia y el alcance exacto de las verificaciones están en [DECISIONES.md](DECISIONES.md) y [PLAN.md](PLAN.md).
