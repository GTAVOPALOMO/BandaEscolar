from django import forms
from PIL import Image, UnidentifiedImageError
from .models import Event
class EventForm(forms.ModelForm):
    class Meta:
        model = Event; fields = ["name", "date", "time", "place", "description", "image", "is_active", "has_tickets", "ticket_price"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"}), "time": forms.TimeInput(attrs={"type": "time"}), "description": forms.Textarea(attrs={"rows": 5})}
    def clean_image(self):
        image = self.cleaned_data.get("image")
        if image and hasattr(image, "temporary_file_path") or (image and not getattr(image, "_committed", False)):
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
