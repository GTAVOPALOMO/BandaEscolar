#!/bin/sh
set -eu
APP_DATA_DIR="${DATA_DIR:-/data}"
export DATA_DIR="$APP_DATA_DIR"
mkdir -p "$APP_DATA_DIR"
chown -R app:app "$APP_DATA_DIR"
exec runuser -u app -m -- gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-8000}" --workers 1 --threads 4 --timeout 60 --access-logfile - --error-logfile -
