import uuid
from django import forms
from events.models import Event
class SaleForm(forms.Form):
    event = forms.ModelChoiceField(queryset=Event.objects.none(), label="Evento")
    buyer_name = forms.CharField(label="Nombre del comprador", max_length=150)
    buyer_id = forms.CharField(label="Cédula del comprador", max_length=40)
    quantity = forms.IntegerField(label="Cantidad", min_value=1, max_value=500)
    idempotency_token = forms.CharField(max_length=64, widget=forms.HiddenInput)
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs); self.fields["event"].queryset = Event.objects.filter(is_active=True, has_tickets=True).order_by("date")
        if not self.is_bound: self.initial["idempotency_token"] = uuid.uuid4().hex
class ScanForm(forms.Form):
    event = forms.ModelChoiceField(queryset=Event.objects.filter(has_tickets=True).order_by("-date"), label="Evento que se está validando")
    code = forms.CharField(label="Código del ticket", max_length=64)
    request_token = forms.CharField(max_length=64, widget=forms.HiddenInput)
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound: self.initial["request_token"] = uuid.uuid4().hex
class TicketReasonForm(forms.Form):
    reason = forms.CharField(label="Motivo obligatorio", max_length=500, widget=forms.Textarea(attrs={"rows": 3}))
