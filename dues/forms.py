import uuid
from django import forms
from django.utils import timezone
from .models import MonthlyDue

class InitialRateForm(forms.Form):
    amount = forms.IntegerField(label="Mensualidad en colones", min_value=1)
    initial_effective_month = forms.DateField(
        label="Mes inicial de vigencia",
        input_formats=["%Y-%m", "%Y-%m-%d"],
        widget=forms.DateInput(format="%Y-%m", attrs={"type": "month"}),
        help_text="Se aplicará desde el primer día del mes elegido y continuará hasta que entre a regir otra tarifa.",
    )
    decision_token = forms.CharField(max_length=64, widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.initial["decision_token"] = uuid.uuid4().hex

    def clean_initial_effective_month(self):
        effective_month = self.cleaned_data["initial_effective_month"].replace(day=1)
        current_month = timezone.localdate().replace(day=1)
        if effective_month > current_month:
            raise forms.ValidationError(
                "La vigencia inicial debe corresponder al mes actual o a un mes anterior."
            )
        return effective_month


class NextRateForm(forms.Form):
    amount = forms.IntegerField(label="Nueva mensualidad en colones", min_value=1)
    reason = forms.CharField(
        label="Motivo de la sustitución",
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    decision_token = forms.CharField(max_length=64, widget=forms.HiddenInput)

    def __init__(self, *args, replacing=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.replacing = replacing
        if replacing:
            self.fields["reason"].required = True
            self.fields["reason"].help_text = "Obligatorio: la decisión programada actual quedará como sustituida en el historial."
        else:
            self.fields["reason"].label = "Motivo de la decisión"
            self.fields["reason"].help_text = "Opcional. Ayuda a comprender por qué se cambió la tarifa."
        if not self.is_bound:
            self.initial["decision_token"] = uuid.uuid4().hex


class CancelRateForm(forms.Form):
    reason = forms.CharField(
        label="Motivo de la cancelación",
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="La tarifa y esta explicación permanecerán en el historial.",
    )

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
