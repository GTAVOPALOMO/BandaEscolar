from datetime import timedelta
from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import User, LoginAttempt

class RateLimitedAuthenticationForm(AuthenticationForm):
    def clean(self):
        username = self.data.get("username", "")[:150]
        recent = LoginAttempt.objects.filter(username=username, successful=False, attempted_at__gte=timezone.now()-timedelta(minutes=15)).count()
        if recent >= 8: raise ValidationError("Demasiados intentos. Espere 15 minutos antes de intentar de nuevo.")
        return super().clean()

class UserCreateForm(forms.ModelForm):
    class Meta:
        model = User; fields = ["username", "first_name", "last_name", "role"]
    def __init__(self, *args, creator=None, **kwargs):
        super().__init__(*args, **kwargs)
        if not creator or creator.role != User.Role.ADMIN:
            self.fields["role"].choices = [(User.Role.GUARDIAN, "Encargado")]

class UserRoleForm(forms.ModelForm):
    class Meta: model = User; fields = ["role"]

class ForcedPasswordForm(PasswordChangeForm): pass
