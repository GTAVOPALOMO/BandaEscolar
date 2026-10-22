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


class AgendaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.committee = User.objects.create_user("agenda-committee", role="COMMITTEE", must_change_password=False)
        cls.guardian = User.objects.create_user("agenda-guardian", role="GUARDIAN", must_change_password=False)
        cls.admin = User.objects.create_user("agenda-admin", role="ADMIN", must_change_password=False)

    def setUp(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        # UTC is already January 1; Costa Rica is still December 31.
        self.now = datetime(2027, 1, 1, 2, 0, tzinfo=ZoneInfo("UTC"))
        self.clock = patch("events.queries.timezone.now", return_value=self.now)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def event(self, name, day=date(2026, 12, 31), hour=time(21), **kwargs):
        return Event.objects.create(name=name, date=day, time=hour, place="Escuela",
                                    description="Actividad de prueba", created_by=self.committee, **kwargs)

    def test_next_activity_uses_local_date_and_time_and_active_only(self):
        self.event("Ayer", date(2026, 12, 30))
        self.event("Ya comenzó", hour=time(19, 59))
        self.event("Empieza ahora", hour=time(20))
        self.event("Oculto", hour=time(20, 1), is_active=False)
        later = self.event("Más tarde", hour=time(22))
        first = self.event("Siguiente", hour=time(20, 30))
        tomorrow = self.event("Mañana", date(2027, 1, 1), time(8))
        response = self.client.get(reverse("home"))
        self.assertEqual(response.context["selected"], date(2026, 12, 1))
        self.assertEqual(response.context["next_event"], first)
        from .queries import upcoming_events
        self.assertEqual(list(upcoming_events()), [first, later, tomorrow])
        self.assertNotContains(response, "Oculto")

    def test_historical_month_keeps_all_active_events_in_order(self):
        second = self.event("Ensayo de tarde", date(2026, 2, 12), time(16))
        first = self.event("Ensayo de mañana", date(2026, 2, 12), time(8))
        self.event("Archivado", date(2026, 2, 13), is_active=False)
        self.event("Otro mes", date(2026, 3, 1))
        response = self.client.get(reverse("home"), {"mes": "2026-02"})
        self.assertEqual(list(response.context["events"]), [first, second])
        self.assertTrue(all(event.start_passed for event in response.context["events"]))
        day_events = [items for week in response.context["weeks"] for day, items in week if day == 12][0]
        self.assertEqual(day_events, [first, second])
        self.assertNotContains(response, "Archivado")
        self.assertNotContains(response, "Otro mes")
        self.assertContains(response, "Hora transcurrida")

    def test_no_next_event_and_empty_selected_month(self):
        self.event("Pasado", date(2026, 1, 1))
        response = self.client.get(reverse("home"), {"mes": "2027-02"})
        self.assertIsNone(response.context["next_event"])
        self.assertContains(response, "No hay próximas actividades publicadas")
        self.assertContains(response, "No hay actividades publicadas en febrero 2027")

    def test_month_navigation_year_boundary_and_view_preserved(self):
        response = self.client.get(reverse("home"), {"mes": "2026-12", "vista": "mes"})
        self.assertEqual(response.context["prev"], date(2026, 11, 1))
        self.assertEqual(response.context["next"], date(2027, 1, 1))
        self.assertContains(response, '?mes=2027-01&amp;vista=mes#agenda')
        self.assertContains(response, '?mes=2026-12&amp;vista=mes#agenda">Hoy')
        response = self.client.get(reverse("home"), {"mes": "2027-01"})
        self.assertEqual(response.context["prev"], date(2026, 12, 1))
        self.assertIsNone(response.context["today_day"])

    def test_bad_month_and_view_fall_back_safely(self):
        for month in ["invalid", "2026-13", "0-01", "10000-01"]:
            with self.subTest(month=month):
                response = self.client.get(reverse("home"), {"mes": month, "vista": '<script>'})
                self.assertEqual(response.context["selected"], date(2026, 12, 1))
                self.assertEqual(response.context["agenda_view"], "auto")
        for month in ["0001-01", "9999-12"]:
            self.assertEqual(self.client.get(reverse("home"), {"mes": month}).status_code, 200)

    def test_calendar_supports_four_five_six_weeks_and_leap_day(self):
        for month, count in [("2021-02", 4), ("2026-04", 5), ("2026-03", 6)]:
            with self.subTest(month=month):
                response = self.client.get(reverse("home"), {"mes": month})
                self.assertEqual(len(response.context["weeks"]), count)
        leap = self.event("Día adicional", date(2028, 2, 29))
        response = self.client.get(reverse("home"), {"mes": "2028-02"})
        self.assertIn(leap, response.context["events"])

    def test_today_has_non_color_indicator(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, 'aria-current="date"')
        self.assertContains(response, ", hoy</span>")

    def test_detail_has_facts_before_image_and_month_return(self):
        event = self.event("Desfile", image="events/test.jpg", has_tickets=True, ticket_price=3000)
        response = self.client.get(reverse("event_detail", args=[event.pk]))
        content = response.content.decode()
        self.assertLess(content.index('class="event-facts"'), content.index('class="event-image-wrap"'))
        self.assertContains(response, '?mes=2026-12#agenda')
        self.assertContains(response, "₡3.000")
        self.assertContains(response, "Actividad de prueba")

    def test_inactive_detail_and_image_are_unavailable_for_every_role(self):
        event = self.event("Privado", is_active=False)
        for user in [None, self.guardian, self.committee, self.admin]:
            with self.subTest(user=user):
                if user:
                    self.client.force_login(user)
                else:
                    self.client.logout()
                for route in ["event_detail", "event_image"]:
                    self.assertEqual(self.client.get(reverse(route, args=[event.pk])).status_code, 404)

    def test_both_dashboards_exclude_past_and_inactive_events(self):
        self.event("Ayer", date(2026, 12, 30))
        self.event("Temprano", hour=time(8))
        self.event("Sin publicar", hour=time(21), is_active=False)
        future = self.event("Esta noche", hour=time(21))
        for user in [self.guardian, self.committee, self.admin]:
            with self.subTest(role=user.role):
                self.client.force_login(user)
                response = self.client.get(reverse("dashboard"))
                self.assertEqual(list(response.context["events"]), [future])
                self.assertContains(response, "21:00")
                self.assertContains(response, "Escuela")

    def test_dashboard_empty_state(self):
        self.client.force_login(self.guardian)
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "No hay próximas actividades publicadas")
        self.assertContains(response, "No tiene estudiantes vinculados")

    def test_event_management_permissions_and_navigation(self):
        event = self.event("Concierto")
        routes = [reverse("event_manage"), reverse("event_create"), reverse("event_edit", args=[event.pk]), reverse("event_toggle", args=[event.pk])]
        for url in routes:
            self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.guardian)
        for url in routes:
            self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.post(url, {}).status_code, 403)
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Mis estudiantes y cuotas")
        self.assertNotContains(response, "Administración")
        for user in [self.committee, self.admin]:
            self.client.force_login(user)
            for url in routes:
                self.assertEqual(self.client.get(url).status_code, 200)
            response = self.client.get(reverse("event_create"))
            self.assertContains(response, 'type="submit">Crear evento')
            self.assertContains(response, f'href="{reverse("event_manage")}"')
            self.assertContains(response, "Administración")

    def test_public_page_does_not_contain_private_student_or_cash_data(self):
        from students.models import Student
        Student.objects.create(name="Estudiante privado", admission_date=date(2026, 1, 1))
        response = self.client.get(reverse("home"))
        self.assertNotContains(response, "Estudiante privado")
        self.assertNotContains(response, "Total pendiente")
        self.assertNotContains(response, 'href="/caja/"')

    def test_event_edit_renders_iso_inputs_and_saves_existing_date(self):
        event = self.event("Nombre anterior")
        self.client.force_login(self.committee)
        response = self.client.get(reverse("event_edit", args=[event.pk]))
        self.assertContains(response, 'value="2026-12-31"')
        self.assertContains(response, 'value="21:00"')
        response = self.client.post(reverse("event_edit", args=[event.pk]), {
            "name": "Nombre actualizado", "date": "2026-12-31", "time": "21:00",
            "place": "Escuela", "description": "Detalle", "is_active": "on",
        })
        self.assertRedirects(response, reverse("event_manage"))
        event.refresh_from_db()
        self.assertEqual(event.name, "Nombre actualizado")
        self.assertEqual(event.date, date(2026, 12, 31))
        self.assertEqual(event.time, time(21))

    def test_invalid_form_preserves_field_errors_and_safe_cancel(self):
        self.client.force_login(self.committee)
        response = self.client.post(reverse("event_create"), {
            "name": "Evento inválido", "date": "2027-01-02", "time": "09:00",
            "place": "Escuela", "description": "Detalle", "has_tickets": "on", "ticket_price": "0",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="id_ticket_price_error"')
        self.assertContains(response, 'aria-invalid="true"')
        self.assertContains(response, f'href="{reverse("event_manage")}">Cancelar')
        self.assertFalse(Event.objects.filter(name="Evento inválido").exists())
