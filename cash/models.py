from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

class CashPeriod(models.Model):
    class Status(models.TextChoices): OPEN = "OPEN", "Abierta"; CLOSED = "CLOSED", "Cerrada"
    opening_balance = models.PositiveIntegerField(default=0)
    opened_at = models.DateTimeField(auto_now_add=True)
    opened_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="cash_periods_opened")
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.OPEN)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="cash_periods_closed")
    closing_income = models.PositiveIntegerField(null=True, blank=True)
    closing_expense = models.PositiveIntegerField(null=True, blank=True)
    closing_balance = models.PositiveIntegerField(null=True, blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["status"], condition=models.Q(status="OPEN"), name="single_open_cash_period")]
    @property
    def total_income(self): return sum(m.amount for m in self.movements.filter(kind="IN"))
    @property
    def total_expense(self): return sum(m.amount for m in self.movements.filter(kind="OUT"))
    @property
    def current_balance(self): return self.opening_balance + self.total_income - self.total_expense

class CashMovement(models.Model):
    class Kind(models.TextChoices): IN = "IN", "Ingreso"; OUT = "OUT", "Egreso"
    class Origin(models.TextChoices):
        MANUAL = "MANUAL", "Manual"; DUE = "DUE", "Cuota"; TICKET = "TICKET", "Venta de ticket"; REVERSAL = "REVERSAL", "Reversión"
    period = models.ForeignKey(CashPeriod, on_delete=models.PROTECT, related_name="movements")
    kind = models.CharField(max_length=3, choices=Kind.choices)
    origin = models.CharField(max_length=12, choices=Origin.choices)
    amount = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    detail = models.CharField(max_length=250)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    source_key = models.CharField(max_length=100, unique=True, null=True, blank=True)
    original_movement = models.OneToOneField("self", null=True, blank=True, on_delete=models.PROTECT, related_name="counter_movement")
    class Meta: ordering = ["created_at", "pk"]
