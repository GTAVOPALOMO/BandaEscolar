from dataclasses import dataclass
from datetime import date, timedelta
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
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
    return FeeRateHistory.objects.filter(
        status=FeeRateHistory.Status.ACTIVE,
        effective_from_month__lte=month_start(month),
    ).order_by("-effective_from_month", "-pk").first()


@dataclass(frozen=True)
class RateChange:
    rate: FeeRateHistory
    created: bool
    replaced: FeeRateHistory | None = None


def _validate_rate_amount(amount):
    if amount <= 0:
        raise ValidationError({"amount": "La tarifa debe ser un entero positivo."})


@transaction.atomic
def create_initial_rate(*, amount, effective_from_month, actor, decision_token=None, today=None):
    _validate_rate_amount(amount)
    effective = month_start(effective_from_month)
    if effective > month_start(today or timezone.localdate()):
        raise ValidationError({"initial_effective_month": "La vigencia inicial debe corresponder al mes actual o a un mes anterior."})
    list(FeeRateHistory.objects.select_for_update().order_by("pk"))
    if decision_token:
        repeated = FeeRateHistory.objects.filter(decision_token=decision_token).first()
        if repeated:
            return RateChange(repeated, False)
    if FeeRateHistory.objects.filter(status=FeeRateHistory.Status.ACTIVE).exists():
        raise ValidationError("La tarifa inicial ya fue definida. Los cambios posteriores rigen desde el mes siguiente.")
    try:
        with transaction.atomic():
            rate = FeeRateHistory.objects.create(
                amount=amount,
                effective_from_month=effective,
                decided_by=actor,
                decision_kind=FeeRateHistory.DecisionKind.INITIAL,
                decision_token=decision_token or None,
            )
    except IntegrityError as exc:
        if decision_token:
            repeated = FeeRateHistory.objects.filter(decision_token=decision_token).first()
            if repeated:
                return RateChange(repeated, False)
        raise ValidationError("La tarifa inicial fue registrada por otra solicitud. Actualice la página.") from exc
    log(
        actor=actor, module="dues", action="INITIAL_RATE", entity="FeeRateHistory", entity_id=rate.pk,
        after={"amount": amount, "effective_from_month": effective.isoformat(), "status": rate.status},
    )
    return RateChange(rate, True)

@transaction.atomic
def set_next_rate(*, amount, actor, reason="", today=None, decision_token=None):
    _validate_rate_amount(amount)
    today = today or timezone.localdate()
    effective = next_month(today)
    reason = (reason or "").strip()
    list(FeeRateHistory.objects.select_for_update().order_by("pk"))
    if decision_token:
        repeated = FeeRateHistory.objects.filter(decision_token=decision_token).first()
        if repeated:
            return RateChange(repeated, False, repeated.replaces)
    if not FeeRateHistory.objects.filter(status=FeeRateHistory.Status.ACTIVE).exists():
        raise ValidationError("Primero debe registrar la tarifa inicial con su mes de vigencia.")
    previous = FeeRateHistory.objects.filter(
        status=FeeRateHistory.Status.ACTIVE,
        effective_from_month=effective,
    ).first()
    if previous and not reason:
        raise ValidationError({"reason": "Explique por qué sustituye la tarifa ya programada para este mes."})
    if previous:
        previous.status = FeeRateHistory.Status.SUPERSEDED
        previous.save(update_fields=["status"])
    try:
        with transaction.atomic():
            rate = FeeRateHistory.objects.create(
                amount=amount,
                effective_from_month=effective,
                decided_by=actor,
                decision_kind=(FeeRateHistory.DecisionKind.REPLACEMENT if previous else FeeRateHistory.DecisionKind.SCHEDULED),
                reason=reason,
                replaces=previous,
                decision_token=decision_token or None,
            )
    except IntegrityError as exc:
        if decision_token:
            repeated = FeeRateHistory.objects.filter(decision_token=decision_token).first()
            if repeated:
                return RateChange(repeated, False, repeated.replaces)
        raise ValidationError("Otra solicitud modificó la tarifa programada. Actualice la página e inténtelo de nuevo.") from exc
    action = "REPLACE_RATE" if previous else "SCHEDULE_RATE"
    before = ({"rate_id": previous.pk, "amount": previous.amount, "status": FeeRateHistory.Status.ACTIVE} if previous else {})
    log(
        actor=actor, module="dues", action=action, entity="FeeRateHistory", entity_id=rate.pk,
        reason=reason, before=before,
        after={"amount": amount, "effective_from_month": effective.isoformat(), "status": rate.status,
               "replaces_rate_id": previous.pk if previous else None},
    )
    return RateChange(rate, True, previous)


def _dues_exist_between(start, end=None):
    after_start = Q(year__gt=start.year) | Q(year=start.year, month__gte=start.month)
    query = MonthlyDue.objects.filter(after_start)
    if end:
        before_end = Q(year__lt=end.year) | Q(year=end.year, month__lt=end.month)
        query = query.filter(before_end)
    return query.exists()


def scheduled_rate_cancellation_error(*, rate, today=None):
    """Explain why a scheduled rate cannot be canceled, or return an empty string."""
    current_month = month_start(today or timezone.localdate())
    if rate.status == FeeRateHistory.Status.CANCELED:
        return "Esta tarifa programada ya fue cancelada."
    if rate.status != FeeRateHistory.Status.ACTIVE:
        return "Esta versión ya no es la tarifa programada activa."
    if rate.effective_from_month <= current_month:
        return "Una tarifa vigente o histórica no puede cancelarse retroactivamente. Registre una nueva tarifa para el mes siguiente."
    prior = FeeRateHistory.objects.filter(
        status=FeeRateHistory.Status.ACTIVE,
        effective_from_month__lt=rate.effective_from_month,
    ).order_by("-effective_from_month", "-pk").first()
    if not prior:
        return "No se puede cancelar porque quedaría un período sin tarifa aplicable."
    following = FeeRateHistory.objects.filter(
        status=FeeRateHistory.Status.ACTIVE,
        effective_from_month__gt=rate.effective_from_month,
    ).order_by("effective_from_month", "pk").first()
    if _dues_exist_between(
        rate.effective_from_month,
        following.effective_from_month if following else None,
    ):
        return "No se puede cancelar: ya existen cuotas materializadas dentro de su período de aplicación. Sus importes permanecerán intactos."
    return ""


@transaction.atomic
def cancel_scheduled_rate(*, rate, actor, reason, today=None):
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError({"reason": "El motivo de la cancelación es obligatorio."})
    today = month_start(today or timezone.localdate())
    list(FeeRateHistory.objects.select_for_update().order_by("pk"))
    rate = FeeRateHistory.objects.get(pk=rate.pk)
    cancellation_error = scheduled_rate_cancellation_error(rate=rate, today=today)
    if cancellation_error:
        raise ValidationError(cancellation_error)
    prior = FeeRateHistory.objects.filter(
        status=FeeRateHistory.Status.ACTIVE,
        effective_from_month__lt=rate.effective_from_month,
    ).order_by("-effective_from_month", "-pk").first()
    rate.status = FeeRateHistory.Status.CANCELED
    rate.canceled_at = timezone.now()
    rate.canceled_by = actor
    rate.cancellation_reason = reason
    rate.save(update_fields=["status", "canceled_at", "canceled_by", "cancellation_reason"])
    log(
        actor=actor, module="dues", action="CANCEL_RATE", entity="FeeRateHistory", entity_id=rate.pk,
        reason=reason,
        before={"amount": rate.amount, "effective_from_month": rate.effective_from_month.isoformat(), "status": FeeRateHistory.Status.ACTIVE},
        after={"amount": rate.amount, "effective_from_month": rate.effective_from_month.isoformat(), "status": rate.status,
               "continuing_rate_id": prior.pk, "continuing_amount": prior.amount},
    )
    return rate

def active_months(student, through):
    months = set()
    for period in student.enrollment_periods.all():
        start = month_start(period.start_date)
        final = through if period.end_date is None else min(through, month_start(period.end_date) - timedelta(days=1))
        if final >= start:
            months.update(iter_months(start, final))
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
