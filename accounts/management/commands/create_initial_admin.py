import os
from django.core.management.base import BaseCommand, CommandError
from accounts.models import User

class Command(BaseCommand):
    help = "Crea el administrador inicial usando INITIAL_ADMIN_USERNAME y INITIAL_ADMIN_PASSWORD."
    def handle(self, *args, **options):
        username, password = os.getenv("INITIAL_ADMIN_USERNAME"), os.getenv("INITIAL_ADMIN_PASSWORD")
        if not username or not password: raise CommandError("Defina INITIAL_ADMIN_USERNAME e INITIAL_ADMIN_PASSWORD.")
        if len(password) < 12: raise CommandError("La contraseña inicial debe tener al menos 12 caracteres.")
        if User.objects.filter(role=User.Role.ADMIN).exists():
            self.stdout.write("Ya existe un administrador; no se realizó ningún cambio."); return
        user = User.objects.create_user(username=username, password=password, role=User.Role.ADMIN, must_change_password=True)
        self.stdout.write(self.style.SUCCESS(f"Administrador {user.username} creado; deberá cambiar su contraseña."))
