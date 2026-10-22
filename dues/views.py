import io
from datetime import date
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from audit.models import AuditLog
from common.permissions import staff_required
from students.models import Student
from students.views import accessible_student
from .forms import CancelRateForm, InitialRateForm, NextRateForm, PaymentForm, WaiveForm, ReasonForm
from .models import FeeRateHistory, StudentPayment, DueWaiver
from .services import cancel_scheduled_rate, create_initial_rate, next_month, rate_for, scheduled_rate_cancellation_error, set_next_rate, register_payment, waive_dues, reverse_waiver, reverse_payment, sync_student_dues, student_summary, month_start

def crc(value): return f"₡{value:,.0f}".replace(",", ".")

@staff_required
def rates(request):
    today = month_start(timezone.localdate())
    active_rates = FeeRateHistory.objects.filter(status=FeeRateHistory.Status.ACTIVE)
    has_rate = active_rates.exists()
    next_effective = next_month(today)
    replacement = active_rates.filter(effective_from_month=next_effective).first() if has_rate else None
    form = (NextRateForm(request.POST or None, replacing=bool(replacement)) if has_rate else InitialRateForm(request.POST or None))
    if request.method == "POST" and form.is_valid():
        try:
            if has_rate:
                result = set_next_rate(
                    amount=form.cleaned_data["amount"], actor=request.user,
                    reason=form.cleaned_data.get("reason", ""), decision_token=form.cleaned_data["decision_token"],
                )
            else:
                result = create_initial_rate(
                    amount=form.cleaned_data["amount"], effective_from_month=form.cleaned_data["initial_effective_month"],
                    actor=request.user, decision_token=form.cleaned_data["decision_token"],
                )
            rate = result.rate
            if not result.created:
                messages.info(request, "Esta decisión ya había sido registrada; no se duplicó.")
            elif rate.decision_kind == FeeRateHistory.DecisionKind.INITIAL:
                messages.success(request, f"Tarifa inicial de {crc(rate.amount)} vigente desde {rate.effective_from_month:%m/%Y}.")
            elif result.replaced:
                messages.success(request, f"Tarifa programada actualizada a {crc(rate.amount)} para {rate.effective_from_month:%m/%Y}; la decisión anterior permanece en el historial.")
            else:
                messages.success(request, f"Tarifa de {crc(rate.amount)} programada para {rate.effective_from_month:%m/%Y}.")
            return redirect("rates")
        except ValidationError as exc:
            if hasattr(exc, "error_dict"):
                for field, errors in exc.error_dict.items():
                    for error in errors:
                        form.add_error(field if field in form.fields else None, error)
            else:
                form.add_error(None, exc)

    versions = list(FeeRateHistory.objects.select_related("decided_by", "canceled_by", "replaces"))
    current = rate_for(today)
    upcoming = active_rates.filter(effective_from_month__gt=today).order_by("effective_from_month", "pk").first()
    ordered_active = list(active_rates.order_by("effective_from_month", "pk"))
    for version in versions:
        if version.status == FeeRateHistory.Status.CANCELED:
            version.display_state = "Cancelada"
        elif version.status == FeeRateHistory.Status.SUPERSEDED:
            version.display_state = "Sustituida"
        elif current and version.pk == current.pk:
            version.display_state = "Vigente"
        elif version.effective_from_month > today:
            version.display_state = "Programada"
        else:
            version.display_state = "Histórica"
        version.valid_until = None
        if version.status == FeeRateHistory.Status.ACTIVE:
            later = next((item for item in ordered_active if item.effective_from_month > version.effective_from_month), None)
            if later:
                version.valid_until = later.effective_from_month - date.resolution
        version.cancellation_error = scheduled_rate_cancellation_error(rate=version, today=today)
        version.can_cancel = not version.cancellation_error
    if upcoming and current:
        upcoming.amount_difference = upcoming.amount - current.amount
    decisions = list(AuditLog.objects.filter(
        module="dues", entity="FeeRateHistory",
        action__in=["INITIAL_RATE", "SET_RATE", "SCHEDULE_RATE", "REPLACE_RATE", "CANCEL_RATE"],
    ).select_related("actor")[:200])
    for decision in decisions:
        decision.effective_month = decision.after.get("effective_from_month") or decision.after.get("effective") or "—"
    return render(request, "dues/rates.html", {
        "form": form, "versions": versions, "current_rate": current, "upcoming_rate": upcoming,
        "next_effective": next_effective, "replacement": replacement, "has_rate": has_rate, "decisions": decisions,
        "today": today,
    })


@staff_required
def rate_cancel(request, pk):
    rate = get_object_or_404(FeeRateHistory.objects.select_related("decided_by"), pk=pk)
    today = month_start(timezone.localdate())
    cancellation_error = scheduled_rate_cancellation_error(rate=rate, today=today)
    if cancellation_error:
        messages.error(request, cancellation_error)
        return redirect("rates")
    prior = FeeRateHistory.objects.filter(
        status=FeeRateHistory.Status.ACTIVE,
        effective_from_month__lt=rate.effective_from_month,
    ).order_by("-effective_from_month", "-pk").first()
    form = CancelRateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            cancel_scheduled_rate(rate=rate, actor=request.user, reason=form.cleaned_data["reason"])
            messages.success(request, f"Tarifa de {crc(rate.amount)} para {rate.effective_from_month:%m/%Y} cancelada; la decisión permanece en el historial.")
            return redirect("rates")
        except ValidationError as exc:
            if hasattr(exc, "error_dict"):
                for field, errors in exc.error_dict.items():
                    for error in errors:
                        form.add_error(field if field in form.fields else None, error)
            else:
                form.add_error(None, exc)
    return render(request, "dues/rate_cancel.html", {"form": form, "rate": rate, "prior": prior})

@staff_required
def payment_create(request, student_pk):
    student = get_object_or_404(Student, pk=student_pk); form = PaymentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            payment, created = register_payment(student=student, amount=form.cleaned_data["amount"], actor=request.user, idempotency_token=form.cleaned_data["idempotency_token"], concept=form.cleaned_data["concept"])
            messages.success(request, "Abono registrado." if created else "Este abono ya había sido registrado; no se duplicó."); return redirect("student_detail", pk=student.pk)
        except ValidationError as exc: form.add_error(None, exc)
    return render(request, "generic_form.html", {"form": form, "title": f"Registrar abono para {student.name}", "submit_label": "Registrar abono", "cancel_url": reverse("student_detail", args=[student.pk])})

@staff_required
def payment_reverse(request, pk):
    payment = get_object_or_404(StudentPayment, pk=pk); form = ReasonForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try: reverse_payment(payment=payment, actor=request.user, reason=form.cleaned_data["reason"]); messages.success(request, "Pago revertido mediante contramovimiento."); return redirect("student_detail", pk=payment.student_id)
        except ValidationError as exc: form.add_error(None, exc)
    return render(request, "generic_form.html", {"form": form, "title": f"Revertir abono #{payment.pk}", "submit_label": "Revertir abono", "cancel_url": reverse("student_detail", args=[payment.student_id]), "dangerous": True, "action_note": "Se registrará una corrección en caja y se recalcularán las cuotas. El abono original permanecerá en el historial."})

@staff_required
def waive(request, student_pk):
    student = get_object_or_404(Student, pk=student_pk); sync_student_dues(student, actor=request.user); form = WaiveForm(request.POST or None, student=student)
    if request.method == "POST" and form.is_valid():
        try: waive_dues(dues=form.cleaned_data["dues"], actor=request.user, reason=form.cleaned_data["reason"]); messages.success(request, "Cuotas perdonadas/regularizadas sin ingreso de caja."); return redirect("student_detail", pk=student.pk)
        except ValidationError as exc: form.add_error(None, exc)
    return render(request, "generic_form.html", {"form": form, "title": f"Perdonar/regularizar cuotas de {student.name}", "submit_label": "Regularizar cuotas", "cancel_url": reverse("student_detail", args=[student.pk]), "dangerous": True, "action_note": "Las cuotas seleccionadas quedarán sin cobro. Esta operación no registra un ingreso en caja."})

@staff_required
def waiver_reverse(request, pk):
    waiver = get_object_or_404(DueWaiver, pk=pk); form = ReasonForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try: reverse_waiver(waiver=waiver, actor=request.user, reason=form.cleaned_data["reason"]); messages.success(request, "Perdón revertido."); return redirect("student_detail", pk=waiver.due.student_id)
        except ValidationError as exc: form.add_error(None, exc)
    return render(request, "generic_form.html", {"form": form, "title": "Revertir perdón", "submit_label": "Revertir perdón", "cancel_url": reverse("student_detail", args=[waiver.due.student_id]), "dangerous": True, "action_note": "La cuota volverá a calcularse como pendiente, aplicando el saldo a favor disponible."})

@login_required
def statement_pdf(request, student_pk):
    student = accessible_student(request.user, student_pk); sync_student_dues(student, actor=request.user); summary = student_summary(student)
    buffer = io.BytesIO(); doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=14*mm, leftMargin=14*mm, topMargin=15*mm, bottomMargin=15*mm)
    styles = getSampleStyleSheet(); story = [Paragraph("Banda Escolar Esquipulas", styles["Title"]), Paragraph(f"Estado de cuotas: {student.name}", styles["Heading2"]),
        Paragraph(f"Ingreso: {student.admission_date:%d/%m/%Y} · Corte: {timezone.localdate():%d/%m/%Y}", styles["Normal"]), Spacer(1, 5*mm)]
    rows = [["Período", "Importe", "Aplicado", "Pendiente", "Estado / motivo"]]
    for due in summary["dues"]:
        waiver = due.waivers.filter(reversed_at__isnull=True).last(); detail = due.display_status
        if waiver: detail += f" — {waiver.reason}"
        rows.append([f"{due.month:02d}/{due.year}", crc(due.original_amount), crc(due.applied_amount), crc(due.pending_amount), detail])
    table = Table(rows, repeatRows=1, colWidths=[25*mm, 28*mm, 28*mm, 28*mm, 65*mm]); table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#173f35")), ("TEXTCOLOR", (0,0), (-1,0), colors.white), ("GRID", (0,0), (-1,-1), .3, colors.grey), ("FONTSIZE", (0,0), (-1,-1), 8), ("VALIGN", (0,0), (-1,-1), "TOP")]))
    story += [table, Spacer(1, 5*mm), Paragraph(f"Pendiente total: {crc(summary['pending'])} · Cuotas pendientes: {summary['pending_count']} · Saldo a favor: {crc(summary['credit'])}", styles["Heading3"]), Paragraph("Pagos cobrados (diferentes de perdones/regularizaciones)", styles["Heading2"])]
    payment_rows = [["Fecha", "Concepto", "Monto", "Estado"]]
    for p in student.payments.all(): payment_rows.append([timezone.localtime(p.created_at).strftime("%d/%m/%Y %H:%M"), p.concept, crc(p.amount), "REVERTIDO" if p.reversed_at else "VIGENTE"])
    if len(payment_rows) == 1: payment_rows.append(["—", "Sin pagos registrados", "—", "—"])
    pt = Table(payment_rows, repeatRows=1, colWidths=[38*mm, 75*mm, 30*mm, 30*mm]); pt.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#e3eee9")), ("GRID", (0,0), (-1,-1), .3, colors.grey), ("FONTSIZE", (0,0), (-1,-1), 8)])); story.append(pt)
    doc.build(story); buffer.seek(0)
    return FileResponse(buffer, as_attachment=True, filename=f"estado-cuotas-{student.pk}.pdf", content_type="application/pdf")
