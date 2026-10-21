import uuid
from django import forms
from .models import FeeRateHistory, MonthlyDue

class RateForm(forms.Form):
    amount = forms.IntegerField(label="Mensualidad en colones", min_value=1)
    initial_effective_month = forms.DateField(label="Mes inicial de vigencia", required=False, widget=forms.DateInput(attrs={"type": "date"}), help_text="Solo se usa al registrar la primera tarifa histórica.")

class PaymentForm(forms.Form):
    amount = forms.IntegerField(label="Monto del abono", min_value=1)
    concept = forms.CharField(label="Concepto", max_length=200, initial="Abono de mensualidad")
    idempotency_token = forms.CharField(max_length=64, widget=forms.HiddenInput)
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound: self.initial["idempotency_token"] = uuid.uuid4().hex

class WaiveForm(forms.Form):
    dues = forms.ModelMultipleChoiceField(queryset=MonthlyDue.objects.none(), widget=forms.CheckboxSelectMultiple, label="Cuotas sin abonos")
    reason = forms.CharField(label="Motivo obligatorio", max_length=500, widget=forms.Textarea(attrs={"rows": 3}))
    def __init__(self, *args, student=None, **kwargs):
        super().__init__(*args, **kwargs)
        if student: self.fields["dues"].queryset = student.dues.filter(status="ORDINARY").order_by("year", "month")

class ReasonForm(forms.Form):
    reason = forms.CharField(label="Motivo obligatorio", max_length=500, widget=forms.Textarea(attrs={"rows": 3}))
