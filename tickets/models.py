import secrets
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

def ticket_code(): return secrets.token_urlsafe(24)

class TicketSale(models.Model):
    event = models.ForeignKey("events.Event", on_delete=models.PROTECT, related_name="sales")
    buyer_name = models.CharField(max_length=150)
    buyer_id = models.CharField(max_length=40)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_price = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    total = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    idempotency_token = models.CharField(max_length=64, unique=True)
    sold_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    sold_at = models.DateTimeField(auto_now_add=True)
    cash_movement = models.OneToOneField("cash.CashMovement", null=True, on_delete=models.PROTECT, related_name="ticket_sale")

class Ticket(models.Model):
    class Status(models.TextChoices): VALID = "VALID", "Válido"; USED = "USED", "Usado"; VOID = "VOID", "Anulado"
    sale = models.ForeignKey(TicketSale, on_delete=models.PROTECT, related_name="tickets")
    code = models.CharField(max_length=64, unique=True, default=ticket_code)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.VALID)
    used_at = models.DateTimeField(null=True, blank=True)
    used_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="tickets_used")
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="tickets_voided")
    void_reason = models.TextField(blank=True)
    replaces = models.OneToOneField("self", null=True, blank=True, on_delete=models.PROTECT, related_name="replacement")

class TicketAction(models.Model):
    class Type(models.TextChoices): VALIDATE = "VALIDATE", "Validación"; REPEAT = "REPEAT", "Intento repetido"; VOID = "VOID", "Anulación"; REPLACE = "REPLACE", "Reemplazo"; WRONG_EVENT = "WRONG_EVENT", "Evento incorrecto"
    ticket = models.ForeignKey(Ticket, on_delete=models.PROTECT, related_name="actions")
    action = models.CharField(max_length=12, choices=Type.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    reason = models.TextField(blank=True)
    request_token = models.CharField(max_length=64, null=True, blank=True, unique=True)
