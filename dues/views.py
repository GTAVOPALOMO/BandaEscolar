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
from audit.services import log
from common.permissions import staff_required
from students.models import Student
from students.views import accessible_student
from .forms import RateForm, PaymentForm, WaiveForm, ReasonForm
from .models import FeeRateHistory, StudentPayment, DueWaiver
from .services import set_next_rate, register_payment, waive_dues, reverse_waiver, reverse_payment, sync_student_dues, student_summary, month_start

def crc(value): return f"₡{value:,.0f}".replace(",", ".")

@staff_required
def rates(request):
    form = RateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            if FeeRateHistory.objects.exists(): rate = set_next_rate(amount=form.cleaned_data["amount"], actor=request.user)
            else:
                effective = month_start(form.cleaned_data["initial_effective_month"] or timezone.localdate())
                rate = FeeRateHistory.objects.create(amount=form.cleaned_data["amount"], effective_from_month=effective, decided_by=request.user)
                log(actor=request.user, module="dues", action="INITIAL_RATE", entity="FeeRateHistory", entity_id=rate.pk, after={"amount": rate.amount, "effective": effective.isoformat()})
            messages.success(request, "Tarifa registrada."); return redirect("rates")
        except ValidationError as exc: form.add_error(None, exc)
    return render(request, "dues/rates.html", {"form": form, "rates": FeeRateHistory.objects.all()})

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
