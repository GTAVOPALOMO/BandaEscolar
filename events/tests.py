from datetime import date, time
from unittest.mock import patch
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from accounts.models import User
from .forms import EventForm
from .models import Event, validate_image_size

class EventInputTests(TestCase):
    def setUp(self): self.user = User.objects.create_user("events", password="long-password!", role="COMMITTEE")
    def test_malicious_fake_image_rejected(self):
        upload = SimpleUploadedFile("ataque.jpg", b"<html><script>alert(1)</script></html>", content_type="image/jpeg")
        form = EventForm({"name":"Evento", "date":date(2026,12,1), "time":time(10), "place":"Escuela", "description":"x", "is_active":True, "has_tickets":False}, {"image":upload})
        self.assertFalse(form.is_valid()); self.assertIn("image", form.errors)
    def test_zero_ticket_price_rejected(self):
        form = EventForm({"name":"Evento", "date":date(2026,12,1), "time":time(10), "place":"Escuela", "description":"x", "is_active":True, "has_tickets":True, "ticket_price":0})
        self.assertFalse(form.is_valid())

    def test_image_limit_leaves_room_for_vercel_multipart_request(self):
        upload = SimpleUploadedFile("grande.jpg", b"x" * (4 * 1024 * 1024 + 1), content_type="image/jpeg")
        with self.assertRaisesMessage(ValidationError, "4 MB"):
            validate_image_size(upload)


class EventImageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("image-owner", password="long-password!", role="COMMITTEE")

    @override_settings(USE_SUPABASE_STORAGE=True, EVENT_IMAGE_URL_TTL=123)
    def test_active_event_redirects_to_short_lived_signed_storage_url(self):
        event = Event.objects.create(
            name="Concierto", date=date(2026, 12, 1), time=time(10), place="Escuela",
            description="x", image="events/concierto.jpg", created_by=self.user,
        )
        with patch.object(event.image.storage, "url", return_value="https://storage.example/signed") as signed_url:
            response = self.client.get(reverse("event_image", args=[event.pk]))
        self.assertRedirects(response, "https://storage.example/signed", fetch_redirect_response=False)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        signed_url.assert_called_once_with("events/concierto.jpg", expire=123)

    @override_settings(USE_SUPABASE_STORAGE=True)
    def test_inactive_event_is_rejected_before_generating_storage_url(self):
        event = Event.objects.create(
            name="Oculto", date=date(2026, 12, 1), time=time(10), place="Escuela",
            description="x", image="events/oculto.jpg", is_active=False, created_by=self.user,
        )
        with patch.object(event.image.storage, "url") as signed_url:
            response = self.client.get(reverse("event_image", args=[event.pk]))
        self.assertEqual(response.status_code, 404)
        signed_url.assert_not_called()
