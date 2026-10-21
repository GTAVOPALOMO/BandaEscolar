from django import forms
from accounts.models import User
from .models import Student

class StudentCreateForm(forms.ModelForm):
    guardians = forms.ModelMultipleChoiceField(queryset=User.objects.none(), label="Encargados")
    class Meta:
        model = Student; fields = ["name", "admission_date", "guardians"]; widgets = {"admission_date": forms.DateInput(attrs={"type": "date"})}
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs); self.fields["guardians"].queryset = User.objects.filter(role=User.Role.GUARDIAN, is_active=True).order_by("username")

class StudentEditForm(forms.Form):
    name = forms.CharField(label="Nombre", max_length=150)
    admission_date = forms.DateField(label="Fecha de ingreso", widget=forms.DateInput(attrs={"type": "date"}))
    reason = forms.CharField(label="Motivo de la corrección", max_length=500, widget=forms.Textarea(attrs={"rows": 3}))

class WithdrawalForm(forms.Form):
    withdrawal_date = forms.DateField(label="Fecha real de retiro", widget=forms.DateInput(attrs={"type": "date"}))
    reason = forms.CharField(label="Motivo (opcional)", required=False, max_length=500, widget=forms.Textarea(attrs={"rows": 3}))

class ReenrollForm(forms.Form):
    start_date = forms.DateField(label="Fecha de reingreso", widget=forms.DateInput(attrs={"type": "date"}))

class GuardianLinkForm(forms.Form):
    guardian = forms.ModelChoiceField(queryset=User.objects.filter(role=User.Role.GUARDIAN, is_active=True), label="Encargado")
