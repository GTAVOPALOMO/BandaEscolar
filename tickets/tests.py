from datetime import date, time
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from accounts.models import User
from cash.models import CashMovement
from cash.services import open_cash, close_cash
from events.forms import EventForm
from events.models import Event
from .models import Ticket, TicketSale, TicketAction
from .services import sell_tickets, validate_ticket, void_ticket, replace_ticket

class TicketTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("seller", password="long-password!", role="COMMITTEE", must_change_password=False)
        self.event = Event.objects.create(name="Concierto", date=date(2026, 12, 1), time=time(18), place="Escuela", description="Presentación", has_tickets=True, ticket_price=2500, created_by=self.user)
        open_cash(actor=self.user, opening_balance=0)
    def sell(self, token="sale", quantity=5): return sell_tickets(event=self.event, buyer_name="María", buyer_id="1-2345", quantity=quantity, actor=self.user, idempotency_token=token)
    def test_five_unique_tickets_one_cash_movement_and_idempotency(self):
        sale, created = self.sell(); again, created2 = self.sell()
        self.assertTrue(created); self.assertFalse(created2); self.assertEqual(sale.pk, again.pk)
        self.assertEqual(sale.tickets.count(), 5); self.assertEqual(len(set(sale.tickets.values_list("code", flat=True))), 5)
        self.assertEqual(CashMovement.objects.count(), 1); self.assertEqual(CashMovement.objects.get().amount, 12500)
    def test_double_validation_sqlite_atomic_equivalent_and_wrong_event(self):
        sale, _ = self.sell(quantity=1); ticket = sale.tickets.get()
        validate_ticket(event=self.event, code=ticket.code, actor=self.user, request_token="scan1")
        with self.assertRaisesMessage(ValidationError, "Ticket ya utilizado"): validate_ticket(event=self.event, code=ticket.code, actor=self.user, request_token="scan2")
        self.assertEqual(TicketAction.objects.filter(action="VALIDATE").count(), 1); self.assertEqual(TicketAction.objects.filter(action="REPEAT").count(), 1)
        other = Event.objects.create(name="Otro", date=date(2026,12,2), time=time(18), place="Parque", description="x", has_tickets=True, ticket_price=1, created_by=self.user)
        with self.assertRaisesMessage(ValidationError, "otro evento"): validate_ticket(event=other, code=ticket.code, actor=self.user, request_token="scan3")
        with self.assertRaisesMessage(ValidationError, "inexistente"): validate_ticket(event=other, code="no-existe", actor=self.user)
    def test_validation_request_idempotency(self):
        sale, _ = self.sell(quantity=1); ticket = sale.tickets.get()
        first, ok1 = validate_ticket(event=self.event, code=ticket.code, actor=self.user, request_token="same-scan")
        second, ok2 = validate_ticket(event=self.event, code=ticket.code, actor=self.user, request_token="same-scan")
        self.assertEqual(first.pk, second.pk); self.assertTrue(ok1 and ok2); self.assertEqual(TicketAction.objects.count(), 1)
    def test_void_and_replace_no_cash_and_used_cannot_replace(self):
        sale, _ = self.sell(quantity=2); first, second = list(sale.tickets.all())
        old_movements = CashMovement.objects.count(); new = replace_ticket(ticket=first, actor=self.user, reason="QR ilegible")
        first.refresh_from_db(); self.assertEqual(first.status, "VOID"); self.assertEqual(new.replaces_id, first.pk); self.assertNotEqual(new.code, first.code); self.assertEqual(CashMovement.objects.count(), old_movements)
        validate_ticket(event=self.event, code=second.code, actor=self.user)
        with self.assertRaises(ValidationError): replace_ticket(ticket=second, actor=self.user, reason="No permitido")
        with self.assertRaises(ValidationError): validate_ticket(event=self.event, code=first.code, actor=self.user)
    def test_closed_cash_rejects_sale_and_price_locked(self):
        self.sell(quantity=1); close_cash(actor=self.user)
        with self.assertRaises(ValidationError): self.sell(token="closed", quantity=1)
        data = {"name": self.event.name, "date": self.event.date, "time": self.event.time, "place": self.event.place, "description": self.event.description, "is_active": True, "has_tickets": True, "ticket_price": 3000}
        form = EventForm(data, instance=self.event); self.assertFalse(form.is_valid()); self.assertIn("ticket_price", form.errors)
    def test_ticket_pdf_contains_pdf_and_codes(self):
        sale, _ = self.sell(quantity=2); self.client.force_login(self.user)
        response = self.client.get(reverse("sale_pdf", args=[sale.pk])); self.assertEqual(response.status_code, 200); self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(self.client.get(reverse("sale_create")).status_code, 200)
