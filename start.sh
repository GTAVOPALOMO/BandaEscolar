#!/bin/sh
set -eu
APP_DATA_DIR="${DATA_DIR:-/data}"
export DATA_DIR="$APP_DATA_DIR"
mkdir -p "$APP_DATA_DIR/media/events" "$APP_DATA_DIR/backups"
chown -R app:app "$APP_DATA_DIR"
runuser -u app -m -- python manage.py migrate --noinput
if [ -n "${INITIAL_ADMIN_USERNAME:-}" ] && [ -n "${INITIAL_ADMIN_PASSWORD:-}" ]; then
  runuser -u app -m -- python manage.py create_initial_admin
fi
exec runuser -u app -m -- gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-8000}" --workers 1 --threads 4 --timeout 60 --access-logfile - --error-logfile -
