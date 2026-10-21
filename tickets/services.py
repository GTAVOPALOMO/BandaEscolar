from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from audit.services import log
from cash.models import CashMovement
from cash.services import add_movement, get_open_period
from .models import TicketSale, Ticket, TicketAction

@transaction.atomic
def sell_tickets(*, event, buyer_name, buyer_id, quantity, actor, idempotency_token):
    existing = TicketSale.objects.filter(idempotency_token=idempotency_token).first()
    if existing: return existing, False
    if not event.is_active or not event.has_tickets or not event.ticket_price:
        raise ValidationError("Este evento no tiene venta de entradas habilitada.")
    if quantity <= 0: raise ValidationError("La cantidad debe ser positiva.")
    if not buyer_name.strip() or not buyer_id.strip(): raise ValidationError("Nombre y cédula del comprador son obligatorios.")
    if not get_open_period(): raise ValidationError("La caja está cerrada. Abra una caja para vender.")
    total = event.ticket_price * quantity
    sale = TicketSale.objects.create(event=event, buyer_name=buyer_name.strip(), buyer_id=buyer_id.strip(), quantity=quantity,
        unit_price=event.ticket_price, total=total, idempotency_token=idempotency_token, sold_by=actor)
    Ticket.objects.bulk_create([Ticket(sale=sale) for _ in range(quantity)])
    movement = add_movement(actor=actor, kind=CashMovement.Kind.IN, origin=CashMovement.Origin.TICKET, amount=total,
        detail=f"Venta de {quantity} entrada(s) para {event.name}", source_key=f"ticket-sale:{sale.pk}")
    sale.cash_movement = movement; sale.save(update_fields=["cash_movement"])
    log(actor=actor, module="tickets", action="SALE", entity="TicketSale", entity_id=sale.pk,
        after={"event": event.pk, "quantity": quantity, "unit_price": event.ticket_price, "total": total}, correlation_id=idempotency_token)
    return sale, True

def validate_ticket(*, event, code, actor, request_token=None):
    if request_token:
        prior = TicketAction.objects.filter(request_token=request_token).first()
        if prior: return prior.ticket, prior.action == TicketAction.Type.VALIDATE
    ticket = Ticket.objects.select_related("sale__event").filter(code=code).first()
    if not ticket: raise ValidationError("Código de ticket inexistente.")
    error = None
    with transaction.atomic():
        ticket = Ticket.objects.select_for_update().select_related("sale__event").get(pk=ticket.pk)
        if ticket.sale.event_id != event.pk:
            TicketAction.objects.create(ticket=ticket, action=TicketAction.Type.WRONG_EVENT, actor=actor, request_token=request_token); error = "El ticket pertenece a otro evento."
        elif ticket.status == Ticket.Status.USED:
            TicketAction.objects.create(ticket=ticket, action=TicketAction.Type.REPEAT, actor=actor, request_token=request_token); error = "Ticket ya utilizado."
        elif ticket.status == Ticket.Status.VOID: error = "El ticket está anulado."
        else:
            updated = Ticket.objects.filter(pk=ticket.pk, status=Ticket.Status.VALID).update(status=Ticket.Status.USED, used_at=timezone.now(), used_by=actor)
            if updated != 1: error = "Ticket ya utilizado."
            else:
                ticket.refresh_from_db(); TicketAction.objects.create(ticket=ticket, action=TicketAction.Type.VALIDATE, actor=actor, request_token=request_token)
                log(actor=actor, module="tickets", action="VALIDATE", entity="Ticket", entity_id=ticket.pk, after={"event": event.pk})
    if error: raise ValidationError(error)
    return ticket, True

@transaction.atomic
def void_ticket(*, ticket, actor, reason):
    reason = (reason or "").strip()
    if not reason: raise ValidationError("El motivo es obligatorio.")
    ticket = Ticket.objects.select_for_update().get(pk=ticket.pk)
    if ticket.status != Ticket.Status.VALID: raise ValidationError("Solo puede anularse un ticket válido y no utilizado.")
    ticket.status, ticket.voided_at, ticket.voided_by, ticket.void_reason = Ticket.Status.VOID, timezone.now(), actor, reason
    ticket.save(update_fields=["status", "voided_at", "voided_by", "void_reason"])
    TicketAction.objects.create(ticket=ticket, action=TicketAction.Type.VOID, actor=actor, reason=reason)
    log(actor=actor, module="tickets", action="VOID", entity="Ticket", entity_id=ticket.pk, reason=reason)
    return ticket

@transaction.atomic
def replace_ticket(*, ticket, actor, reason):
    old = void_ticket(ticket=ticket, actor=actor, reason=reason)
    new = Ticket.objects.create(sale=old.sale, replaces=old)
    TicketAction.objects.create(ticket=new, action=TicketAction.Type.REPLACE, actor=actor, reason=reason)
    log(actor=actor, module="tickets", action="REPLACE", entity="Ticket", entity_id=new.pk, reason=reason, before={"ticket": old.pk})
    return new
