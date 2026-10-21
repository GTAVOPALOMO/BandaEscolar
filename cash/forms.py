from django import forms
from .models import CashMovement
class OpenCashForm(forms.Form): opening_balance = forms.IntegerField(label="Saldo inicial (solo primera apertura)", min_value=0, required=False, initial=0)
class MovementForm(forms.Form):
    kind = forms.ChoiceField(label="Tipo", choices=[(CashMovement.Kind.IN, "Ingreso"), (CashMovement.Kind.OUT, "Egreso")])
    amount = forms.IntegerField(label="Monto", min_value=1)
    detail = forms.CharField(label="Detalle", max_length=250, widget=forms.Textarea(attrs={"rows": 3}))
class CorrectionForm(forms.Form):
    reason = forms.CharField(label="Motivo obligatorio", max_length=500, widget=forms.Textarea(attrs={"rows": 3}))
