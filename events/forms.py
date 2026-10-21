from django import forms
from django.conf import settings
from PIL import Image, UnidentifiedImageError
from .models import Event
class EventForm(forms.ModelForm):
    class Meta:
        model = Event; fields = ["name", "date", "time", "place", "description", "image", "is_active", "has_tickets", "ticket_price"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"}), "time": forms.TimeInput(attrs={"type": "time"}), "description": forms.Textarea(attrs={"rows": 5})}
    def clean_image(self):
        image = self.cleaned_data.get("image")
        is_new_upload = image and (hasattr(image, "temporary_file_path") or not getattr(image, "_committed", False))
        if is_new_upload and image.size > settings.MAX_EVENT_IMAGE_BYTES:
            raise forms.ValidationError("La imagen no puede superar 4 MB.")
        if is_new_upload:
            try:
                parsed = Image.open(image)
                if parsed.width * parsed.height > 40_000_000: raise forms.ValidationError("La imagen tiene dimensiones excesivas.")
                parsed.verify(); image.seek(0)
            except (UnidentifiedImageError, OSError, ValueError): raise forms.ValidationError("El archivo no es una imagen válida.")
        return image
    def clean_ticket_price(self):
        price = self.cleaned_data.get("ticket_price")
        if self.instance.pk and self.instance.sales.exists() and price != self.instance.ticket_price:
            raise forms.ValidationError("El precio está bloqueado porque ya existe una venta.")
        return price
