import uuid
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from audit.services import log
from .models import CashPeriod, CashMovement

def get_open_period():
    return CashPeriod.objects.filter(status=CashPeriod.Status.OPEN).first()

@transaction.atomic
def open_cash(*, actor, opening_balance=None):
    if get_open_period(): raise ValidationError("Ya existe una caja abierta.")
    last = CashPeriod.objects.filter(status=CashPeriod.Status.CLOSED).order_by("-closed_at", "-pk").first()
    if last:
        amount = last.closing_balance
        if opening_balance is not None and opening_balance != amount:
            raise ValidationError("La nueva caja debe heredar el último saldo final.")
    else:
        amount = 0 if opening_balance is None else opening_balance
        if amount < 0: raise ValidationError("El saldo inicial no puede ser negativo.")
    try:
        with transaction.atomic():
            period = CashPeriod.objects.create(opening_balance=amount, opened_by=actor)
    except IntegrityError as error:
        if get_open_period():
            raise ValidationError("Ya existe una caja abierta.") from error
        raise
    log(actor=actor, module="cash", action="OPEN", entity="CashPeriod", entity_id=period.pk, after={"opening_balance": amount})
    return period

@transaction.atomic
def add_movement(*, actor, kind, origin, amount, detail, source_key=None, original=None):
    if amount <= 0: raise ValidationError("El monto debe ser un entero positivo.")
    detail = (detail or "").strip()
    if not detail: raise ValidationError("El detalle es obligatorio.")
    if source_key:
        existing = CashMovement.objects.filter(source_key=source_key).first()
        if existing: return existing
    period = CashPeriod.objects.select_for_update().filter(status=CashPeriod.Status.OPEN).first()
    if not period: raise ValidationError("La caja está cerrada. Abra una caja para continuar.")
    if kind == CashMovement.Kind.OUT and period.current_balance < amount:
        raise ValidationError("Saldo de caja insuficiente; no se registró ningún movimiento.")
    movement = CashMovement.objects.create(period=period, kind=kind, origin=origin, amount=amount,
        detail=detail[:250], created_by=actor, source_key=source_key, original_movement=original)
    log(actor=actor, module="cash", action="MOVEMENT", entity="CashMovement", entity_id=movement.pk,
        after={"kind": kind, "origin": origin, "amount": amount, "detail": detail})
    return movement

@transaction.atomic
def close_cash(*, actor):
    period = CashPeriod.objects.select_for_update().filter(status=CashPeriod.Status.OPEN).first()
    if not period: raise ValidationError("No hay una caja abierta.")
    income, expense, balance = period.total_income, period.total_expense, period.current_balance
    period.status = CashPeriod.Status.CLOSED
    period.closed_at, period.closed_by = timezone.now(), actor
    period.closing_income, period.closing_expense, period.closing_balance = income, expense, balance
    period.save(update_fields=["status", "closed_at", "closed_by", "closing_income", "closing_expense", "closing_balance"])
    log(actor=actor, module="cash", action="CLOSE", entity="CashPeriod", entity_id=period.pk,
        after={"income": income, "expense": expense, "balance": balance})
    return period

@transaction.atomic
def reverse_manual_movement(*, movement, actor, reason):
    reason = (reason or "").strip()
    if not reason: raise ValidationError("El motivo es obligatorio.")
    movement = CashMovement.objects.select_for_update().get(pk=movement.pk)
    if movement.origin != CashMovement.Origin.MANUAL: raise ValidationError("Esta corrección solo aplica a movimientos manuales.")
    if hasattr(movement, "counter_movement"): raise ValidationError("El movimiento ya fue corregido.")
    opposite = CashMovement.Kind.OUT if movement.kind == CashMovement.Kind.IN else CashMovement.Kind.IN
    return add_movement(actor=actor, kind=opposite, origin=CashMovement.Origin.REVERSAL, amount=movement.amount,
        detail=f"Corrección de movimiento #{movement.pk}: {reason}", source_key=f"movement-reversal:{movement.pk}", original=movement)
