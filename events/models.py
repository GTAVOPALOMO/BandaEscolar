from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, FileExtensionValidator
from django.db import models

def validate_image_size(value):
    if value.size > settings.MAX_EVENT_IMAGE_BYTES:
        raise ValidationError("La imagen no puede superar 4 MB.")

class Event(models.Model):
    name = models.CharField(max_length=150)
    date = models.DateField(db_index=True)
    time = models.TimeField()
    place = models.CharField(max_length=180)
    description = models.TextField(max_length=3000)
    image = models.ImageField(upload_to="events/%Y/%m/", null=True, blank=True, validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp"]), validate_image_size])
    is_active = models.BooleanField(default=True, db_index=True)
    has_tickets = models.BooleanField(default=False)
    ticket_price = models.PositiveIntegerField(null=True, blank=True, validators=[MinValueValidator(1)])
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="events_created")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta: ordering = ["date", "time"]
    def clean(self):
        if self.has_tickets and not self.ticket_price: raise ValidationError({"ticket_price": "Indique un precio positivo."})
        if not self.has_tickets and self.ticket_price is not None: raise ValidationError({"ticket_price": "Un evento sin entradas no lleva precio."})

    def __str__(self): return self.name
