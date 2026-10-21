from datetime import date, time
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from accounts.models import User
from .forms import EventForm

class EventInputTests(TestCase):
    def setUp(self): self.user = User.objects.create_user("events", password="long-password!", role="COMMITTEE")
    def test_malicious_fake_image_rejected(self):
        upload = SimpleUploadedFile("ataque.jpg", b"<html><script>alert(1)</script></html>", content_type="image/jpeg")
        form = EventForm({"name":"Evento", "date":date(2026,12,1), "time":time(10), "place":"Escuela", "description":"x", "is_active":True, "has_tickets":False}, {"image":upload})
        self.assertFalse(form.is_valid()); self.assertIn("image", form.errors)
    def test_zero_ticket_price_rejected(self):
        form = EventForm({"name":"Evento", "date":date(2026,12,1), "time":time(10), "place":"Escuela", "description":"x", "is_active":True, "has_tickets":True, "ticket_price":0})
        self.assertFalse(form.is_valid())
