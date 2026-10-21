import calendar
import uuid
from datetime import date, timedelta
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone
from audit.services import log
from cash.models import CashMovement
from cash.services import add_movement, get_open_period
from .models import FeeRateHistory, MonthlyDue, StudentPayment, PaymentAllocation, DueWaiver, DueWaiverGroup

def month_start(value): return value.replace(day=1)

def next_month(value):
    return date(value.year + (value.month == 12), 1 if value.month == 12 else value.month + 1, 1)

def iter_months(start, end):
    current = month_start(start); end = month_start(end)
    while current <= end:
        yield current
        current = next_month(current)

def rate_for(month):
    return FeeRateHistory.objects.filter(effective_from_month__lte=month_start(month)).order_by("-effective_from_month").first()

@transaction.atomic
def set_next_rate(*, amount, actor, today=None):
    if amount <= 0: raise ValidationError("La tarifa debe ser positiva.")
    effective = next_month(today or timezone.localdate())
    previous = FeeRateHistory.objects.filter(effective_from_month=effective).first()
    before = {"amount": previous.amount} if previous else {}
    rate, _ = FeeRateHistory.objects.update_or_create(effective_from_month=effective, defaults={"amount": amount, "decided_by": actor})
    log(actor=actor, module="dues", action="SET_RATE", entity="FeeRateHistory", entity_id=rate.pk, before=before,
        after={"amount": amount, "effective_from_month": effective.isoformat()})
    return rate

def active_months(student, through):
    months = set()
    for period in student.enrollment_periods.all():
        final = through if period.end_date is None else min(through, month_start(period.end_date) - timedelta(days=1))
        if final >= period.start_date:
            months.update(iter_months(period.start_date, final))
    return sorted(months)

@transaction.atomic
def sync_student_dues(student, *, through=None, actor=None):
    student = type(student).objects.select_for_update().get(pk=student.pk)
    through = month_start(through or timezone.localdate())
    created = []
    reactivated = False
    for month in active_months(student, through):
        rate = rate_for(month)
        if not rate:
            raise ValidationError(f"Falta una tarifa aplicable a {month:%m/%Y}. Registre la tarifa histórica inicial.")
        due, was_created = MonthlyDue.objects.get_or_create(student=student, year=month.year, month=month.month,
            defaults={"original_amount": rate.amount})
        if was_created:
            created.append(due)
            log(actor=actor, module="dues", action="AUTO_CREATE", entity="MonthlyDue", entity_id=due.pk,
                after={"student": student.pk, "period": f"{month.year}-{month.month:02d}", "amount": rate.amount})
        elif due.status == MonthlyDue.Status.NO_CHARGE:
            due.status = MonthlyDue.Status.ORDINARY
            due.save(update_fields=["status", "updated_at"])
            reactivated = True
            log(actor=actor, module="dues", action="REACTIVATE", entity="MonthlyDue", entity_id=due.pk)
    if created or reactivated:
        rebuild_allocations(student, reason="Aplicación de crédito a nuevas cuotas", actor=actor)
    return created

def student_summary(student):
    dues = list(student.dues.all())
    pending = sum(d.pending_amount for d in dues)
    count = sum(d.display_status in {"PENDIENTE", "PARCIAL"} for d in dues)
    credit = sum(p.credit for p in student.payments.filter(reversed_at__isnull=True))
    return {"pending": pending, "pending_count": count, "credit": credit, "dues": dues}

def rebuild_allocations(student, *, reason, actor=None):
    student = type(student).objects.select_for_update().get(pk=student.pk)
    now = timezone.now()
    active = PaymentAllocation.objects.filter(payment__student=student, is_active=True)
    active.update(is_active=False, voided_at=now, reason=reason[:120])
    dues = list(MonthlyDue.objects.filter(student=student, status=MonthlyDue.Status.ORDINARY).order_by("year", "month", "pk"))
    payments = StudentPayment.objects.filter(student=student, reversed_at__isnull=True).order_by("created_at", "pk")
    remaining_due = {d.pk: d.original_amount for d in dues}
    allocations = []
    for payment in payments:
        remaining_payment = payment.amount
        for due in dues:
            value = min(remaining_payment, remaining_due[due.pk])
            if value:
                allocations.append(PaymentAllocation(payment=payment, due=due, amount=value))
                remaining_payment -= value; remaining_due[due.pk] -= value
            if not remaining_payment: break
    PaymentAllocation.objects.bulk_create(allocations)
    log(actor=actor, module="dues", action="REALLOCATE", entity="Student", entity_id=student.pk, reason=reason,
        after={"allocations": [{"payment": a.payment_id, "due": a.due_id, "amount": a.amount} for a in allocations]})
    return allocations

@transaction.atomic
def register_payment(*, student, amount, actor, idempotency_token, concept="Abono de mensualidad"):
    if amount <= 0: raise ValidationError("El abono debe ser un entero positivo.")
    concept = (concept or "").strip()
    if not concept: raise ValidationError("El concepto es obligatorio.")
    existing = StudentPayment.objects.filter(idempotency_token=idempotency_token).first()
    if existing: return existing, False
    student = type(student).objects.select_for_update().get(pk=student.pk)
    existing = StudentPayment.objects.filter(idempotency_token=idempotency_token).first()
    if existing: return existing, False
    sync_student_dues(student, actor=actor)
    if not get_open_period(): raise ValidationError("La caja está cerrada. Abra una caja para recibir el abono.")
    try:
        with transaction.atomic():
            payment = StudentPayment.objects.create(student=student, amount=amount, concept=concept[:200], idempotency_token=idempotency_token, registered_by=actor)
    except IntegrityError:
        existing = StudentPayment.objects.filter(idempotency_token=idempotency_token).first()
        if existing: return existing, False
        raise
    movement = add_movement(actor=actor, kind=CashMovement.Kind.IN, origin=CashMovement.Origin.DUE, amount=amount,
        detail=f"Abono de {student.name}", source_key=f"payment:{payment.pk}")
    rebuild_allocations(student, reason="Registro de abono", actor=actor)
    log(actor=actor, module="dues", action="PAYMENT", entity="StudentPayment", entity_id=payment.pk,
        after={"student": student.pk, "amount": amount, "cash_movement": movement.pk}, correlation_id=idempotency_token)
    return payment, True

@transaction.atomic
def reverse_payment(*, payment, actor, reason):
    reason = (reason or "").strip()
    if not reason: raise ValidationError("El motivo es obligatorio.")
    payment = StudentPayment.objects.select_for_update().get(pk=payment.pk)
    student = type(payment.student).objects.select_for_update().get(pk=payment.student_id)
    if payment.reversed_at: raise ValidationError("Este pago ya fue revertido.")
    original = CashMovement.objects.get(source_key=f"payment:{payment.pk}")
    movement = add_movement(actor=actor, kind=CashMovement.Kind.OUT, origin=CashMovement.Origin.REVERSAL, amount=payment.amount,
        detail=f"Reversión de abono #{payment.pk}: {reason}", source_key=f"payment-reversal:{payment.pk}", original=original)
    payment.reversed_at, payment.reversed_by, payment.reversal_reason = timezone.now(), actor, reason
    payment.save(update_fields=["reversed_at", "reversed_by", "reversal_reason"])
    rebuild_allocations(student, reason=f"Reversión de pago #{payment.pk}", actor=actor)
    log(actor=actor, module="dues", action="REVERSE_PAYMENT", entity="StudentPayment", entity_id=payment.pk, reason=reason,
        after={"counter_movement": movement.pk})
    return payment

@transaction.atomic
def waive_dues(*, dues, actor, reason):
    reason = (reason or "").strip()
    if not reason: raise ValidationError("El motivo es obligatorio.")
    due_ids = [d.pk for d in dues]
    student_model = MonthlyDue._meta.get_field("student").remote_field.model
    student_ids = MonthlyDue.objects.filter(pk__in=due_ids).values_list("student_id", flat=True).distinct()
    list(student_model.objects.select_for_update().filter(pk__in=student_ids).order_by("pk"))
    locked = list(MonthlyDue.objects.select_for_update().filter(pk__in=due_ids))
    if not locked: raise ValidationError("Seleccione al menos una cuota.")
    if any(d.status != MonthlyDue.Status.ORDINARY or d.applied_amount for d in locked):
        raise ValidationError("Solo se pueden perdonar cuotas ordinarias sin abonos.")
    group = DueWaiverGroup.objects.create(reason=reason, created_by=actor)
    for due in locked:
        DueWaiver.objects.create(due=due, group=group, reason=reason, waived_by=actor)
        due.status = MonthlyDue.Status.WAIVED; due.save(update_fields=["status", "updated_at"])
        log(actor=actor, module="dues", action="WAIVE", entity="MonthlyDue", entity_id=due.pk, reason=reason)
    return group

@transaction.atomic
def reverse_waiver(*, waiver, actor, reason):
    reason = (reason or "").strip()
    if not reason: raise ValidationError("El motivo es obligatorio.")
    waiver = DueWaiver.objects.select_for_update().get(pk=waiver.pk)
    student = type(waiver.due.student).objects.select_for_update().get(pk=waiver.due.student_id)
    if waiver.reversed_at: raise ValidationError("El perdón ya fue revertido.")
    waiver.reversed_at, waiver.reversed_by, waiver.reversal_reason = timezone.now(), actor, reason
    waiver.save(update_fields=["reversed_at", "reversed_by", "reversal_reason"])
    waiver.due.status = MonthlyDue.Status.ORDINARY; waiver.due.save(update_fields=["status", "updated_at"])
    rebuild_allocations(student, reason="Reversión de perdón", actor=actor)
    log(actor=actor, module="dues", action="REVERSE_WAIVER", entity="MonthlyDue", entity_id=waiver.due_id, reason=reason)
    return waiver
