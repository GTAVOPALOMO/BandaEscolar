from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

class FeeRateHistory(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Activa"
        SUPERSEDED = "SUPERSEDED", "Sustituida"
        CANCELED = "CANCELED", "Cancelada"

    class DecisionKind(models.TextChoices):
        INITIAL = "INITIAL", "Tarifa inicial"
        SCHEDULED = "SCHEDULED", "Programación"
        REPLACEMENT = "REPLACEMENT", "Sustitución"

    amount = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    effective_from_month = models.DateField(db_index=True)
    decided_at = models.DateTimeField(auto_now_add=True)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    decision_kind = models.CharField(max_length=12, choices=DecisionKind.choices, default=DecisionKind.SCHEDULED)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    reason = models.TextField(blank=True)
    replaces = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="replacement_versions")
    canceled_at = models.DateTimeField(null=True, blank=True)
    canceled_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="fee_rates_canceled")
    cancellation_reason = models.TextField(blank=True)
    decision_token = models.CharField(max_length=64, unique=True, null=True, blank=True)

    class Meta:
        ordering = ["effective_from_month", "decided_at", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["decision_kind"],
                condition=models.Q(decision_kind="INITIAL"),
                name="unique_initial_fee_rate_decision",
            ),
            models.UniqueConstraint(
                fields=["effective_from_month"],
                condition=models.Q(status="ACTIVE"),
                name="unique_active_fee_rate_month",
            ),
        ]

class MonthlyDue(models.Model):
    class Status(models.TextChoices):
        ORDINARY = "ORDINARY", "Ordinaria"
        WAIVED = "WAIVED", "Perdonada/regularizada"
        NO_CHARGE = "NO_CHARGE", "Sin cargo por retiro"
    student = models.ForeignKey("students.Student", on_delete=models.PROTECT, related_name="dues")
    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()
    original_amount = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ORDINARY)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ["year", "month"]
        constraints = [models.UniqueConstraint(fields=["student", "year", "month"], name="unique_student_due_month"), models.CheckConstraint(condition=models.Q(month__gte=1, month__lte=12), name="valid_due_month")]

    @property
    def applied_amount(self):
        return sum(a.amount for a in self.allocations.filter(is_active=True))
    @property
    def pending_amount(self):
        return 0 if self.status != self.Status.ORDINARY else max(0, self.original_amount - self.applied_amount)
    @property
    def display_status(self):
        if self.status == self.Status.WAIVED: return "PERDONADA"
        if self.status == self.Status.NO_CHARGE: return "SIN_CARGO_POR_RETIRO"
        paid = self.applied_amount
        if paid == 0: return "PENDIENTE"
        if paid < self.original_amount: return "PARCIAL"
        return "PAGADA"

class DueWaiverGroup(models.Model):
    reason = models.TextField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

class DueWaiver(models.Model):
    due = models.ForeignKey(MonthlyDue, on_delete=models.PROTECT, related_name="waivers")
    group = models.ForeignKey(DueWaiverGroup, on_delete=models.PROTECT, related_name="waivers")
    reason = models.TextField()
    waived_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="waivers_made")
    waived_at = models.DateTimeField(auto_now_add=True)
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="waivers_reversed")
    reversal_reason = models.TextField(blank=True)

class StudentPayment(models.Model):
    student = models.ForeignKey("students.Student", on_delete=models.PROTECT, related_name="payments")
    amount = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    concept = models.CharField(max_length=200, default="Abono de mensualidad")
    idempotency_token = models.CharField(max_length=64, unique=True)
    registered_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payments_registered")
    created_at = models.DateTimeField(auto_now_add=True)
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="payments_reversed")
    reversal_reason = models.TextField(blank=True)
    class Meta: ordering = ["created_at", "pk"]
    @property
    def active_allocated(self): return sum(a.amount for a in self.allocations.filter(is_active=True))
    @property
    def credit(self): return 0 if self.reversed_at else self.amount - self.active_allocated

class PaymentAllocation(models.Model):
    payment = models.ForeignKey(StudentPayment, on_delete=models.PROTECT, related_name="allocations")
    due = models.ForeignKey(MonthlyDue, on_delete=models.PROTECT, related_name="allocations")
    amount = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    reason = models.CharField(max_length=120, blank=True)
    class Meta: indexes = [models.Index(fields=["due", "is_active"]), models.Index(fields=["payment", "is_active"])]
