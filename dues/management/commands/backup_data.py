import sqlite3
from datetime import datetime
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

class Command(BaseCommand):
    help = "Crea una copia consistente de SQLite mediante la API de backup."
    def add_arguments(self, parser): parser.add_argument("--output", help="Ruta del .sqlite3 de salida")
    def handle(self, *args, **options):
        source = Path(settings.DATABASES["default"]["NAME"])
        if not source.exists(): raise CommandError("No existe la base de datos de origen.")
        target = Path(options["output"] or (Path(settings.DATA_DIR) / "backups" / f"db-{datetime.now():%Y%m%d-%H%M%S}.sqlite3"))
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.resolve() == source.resolve(): raise CommandError("La salida debe ser diferente de la base activa.")
        with sqlite3.connect(source) as src, sqlite3.connect(target) as dst: src.backup(dst)
        self.stdout.write(self.style.SUCCESS(str(target)))
