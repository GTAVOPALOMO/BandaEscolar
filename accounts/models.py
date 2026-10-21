from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    class Role(models.TextChoices):
        GUARDIAN = "GUARDIAN", "Encargado"
        COMMITTEE = "COMMITTEE", "Comité"
        ADMIN = "ADMIN", "Administrador"
    role = models.CharField(max_length=12, choices=Role.choices, default=Role.GUARDIAN, db_index=True)
    must_change_password = models.BooleanField(default=True)

    @property
    def is_committee(self):
        return self.is_authenticated and self.is_active and self.role in {self.Role.COMMITTEE, self.Role.ADMIN}

    def save(self, *args, **kwargs):
        self.is_staff = self.role == self.Role.ADMIN
        super().save(*args, **kwargs)

class LoginAttempt(models.Model):
    username = models.CharField(max_length=150, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True, db_index=True)
    attempted_at = models.DateTimeField(auto_now_add=True, db_index=True)
    successful = models.BooleanField(default=False)
