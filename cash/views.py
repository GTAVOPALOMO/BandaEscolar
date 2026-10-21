from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from common.permissions import staff_required
from .forms import OpenCashForm, MovementForm, CorrectionForm
from .models import CashPeriod, CashMovement
from .services import open_cash, close_cash, add_movement, get_open_period, reverse_manual_movement

@staff_required
def cash_home(request):
    period_id = request.GET.get("period"); periods = CashPeriod.objects.order_by("-opened_at")
    selected = CashPeriod.objects.filter(pk=period_id).first() if period_id else get_open_period() or periods.first()
    movements = selected.movements.all() if selected else CashMovement.objects.none()
    running, rows = (selected.opening_balance if selected else 0), []
    for movement in movements:
        running += movement.amount if movement.kind == "IN" else -movement.amount; rows.append((movement, running))
    return render(request, "cash/home.html", {"cash": get_open_period(), "selected": selected, "periods": periods, "rows": rows})

@staff_required
def cash_open(request):
    form = OpenCashForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try: open_cash(actor=request.user, opening_balance=form.cleaned_data["opening_balance"]); messages.success(request, "Caja abierta."); return redirect("cash_home")
        except ValidationError as exc: form.add_error(None, exc)
    return render(request, "generic_form.html", {"form": form, "title": "Abrir caja"})

@staff_required
def cash_movement(request):
    form = MovementForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try: add_movement(actor=request.user, kind=form.cleaned_data["kind"], origin=CashMovement.Origin.MANUAL, amount=form.cleaned_data["amount"], detail=form.cleaned_data["detail"]); messages.success(request, "Movimiento registrado."); return redirect("cash_home")
        except ValidationError as exc: form.add_error(None, exc)
    return render(request, "generic_form.html", {"form": form, "title": "Registrar movimiento manual"})

@staff_required
def cash_close(request):
    if request.method != "POST": return render(request, "cash/close.html", {"cash": get_open_period()})
    try: close_cash(actor=request.user); messages.success(request, "Caja cerrada; el resumen quedó inmutable.")
    except ValidationError as exc: messages.error(request, "; ".join(exc.messages))
    return redirect("cash_home")

@staff_required
def cash_correct(request, pk):
    movement = get_object_or_404(CashMovement, pk=pk)
    form = CorrectionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try: reverse_manual_movement(movement=movement, actor=request.user, reason=form.cleaned_data["reason"]); messages.success(request, "Corrección asentada en la caja abierta."); return redirect("cash_home")
        except ValidationError as exc: form.add_error(None, exc)
    return render(request, "generic_form.html", {"form": form, "title": f"Corregir movimiento #{pk}"})
