import io
import qrcode
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from common.permissions import staff_required
from .forms import SaleForm, ScanForm, TicketReasonForm
from .models import TicketSale, Ticket
from .services import sell_tickets, validate_ticket, void_ticket, replace_ticket

@staff_required
def sale_list(request): return render(request, "tickets/sales.html", {"sales": TicketSale.objects.select_related("event").order_by("-sold_at")})

@staff_required
def sale_create(request):
    form = SaleForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            sale, created = sell_tickets(event=form.cleaned_data["event"], buyer_name=form.cleaned_data["buyer_name"], buyer_id=form.cleaned_data["buyer_id"], quantity=form.cleaned_data["quantity"], actor=request.user, idempotency_token=form.cleaned_data["idempotency_token"])
            messages.success(request, "Venta confirmada." if created else "La venta ya estaba registrada; no se duplicó."); return redirect("sale_detail", pk=sale.pk)
        except ValidationError as exc: form.add_error(None, exc)
    return render(request, "tickets/sale_form.html", {"form": form, "prices": {str(e.pk): e.ticket_price for e in form.fields["event"].queryset}})

@staff_required
def sale_detail(request, pk): return render(request, "tickets/sale_detail.html", {"sale": get_object_or_404(TicketSale.objects.select_related("event"), pk=pk)})

@staff_required
def sale_pdf(request, pk):
    sale = get_object_or_404(TicketSale.objects.select_related("event"), pk=pk); buffer = io.BytesIO(); c = canvas.Canvas(buffer, pagesize=A4); width, height = A4
    printable = list(sale.tickets.filter(replacement__isnull=True).order_by("pk"))
    for index, ticket in enumerate(printable, start=1):
        if index > 1: c.showPage()
        c.setFont("Helvetica-Bold", 18); c.drawString(20*mm, height-25*mm, "Banda Escolar Esquipulas")
        c.setFont("Helvetica-Bold", 15); c.drawString(20*mm, height-38*mm, sale.event.name)
        c.setFont("Helvetica", 11); c.drawString(20*mm, height-49*mm, f"Fecha: {sale.event.date:%d/%m/%Y}  Hora: {sale.event.time:%H:%M}")
        c.drawString(20*mm, height-57*mm, f"Lugar: {sale.event.place}"); c.drawString(20*mm, height-65*mm, f"Comprador: {sale.buyer_name}")
        qr = qrcode.make(ticket.code); qrbuf = io.BytesIO(); qr.save(qrbuf, format="PNG"); qrbuf.seek(0)
        c.drawImage(ImageReader(qrbuf), 55*mm, height-150*mm, 100*mm, 100*mm, preserveAspectRatio=True)
        c.setFont("Courier-Bold", 10); c.drawCentredString(width/2, height-160*mm, ticket.code)
        c.setFont("Helvetica", 9); c.drawCentredString(width/2, height-169*mm, f"Entrada {index} de {len(printable)} · Estado al emitir: {ticket.get_status_display()}")
        c.drawCentredString(width/2, 18*mm, "Presente este QR en la entrada. El código no contiene la cédula del comprador.")
    c.save(); buffer.seek(0); return FileResponse(buffer, as_attachment=True, filename=f"entradas-{sale.pk}.pdf", content_type="application/pdf")

@staff_required
def scan(request):
    form = ScanForm(request.POST or None)
    result = None
    if request.method == "POST" and form.is_valid():
        try:
            ticket, accepted = validate_ticket(event=form.cleaned_data["event"], code=form.cleaned_data["code"].strip(), actor=request.user, request_token=form.cleaned_data["request_token"])
            result = ("success", f"Ticket válido. Acceso confirmado para {ticket.sale.event.name}.")
        except ValidationError as exc: result = ("error", "; ".join(exc.messages))
    return render(request, "tickets/scan.html", {"form": form, "result": result})

@staff_required
def ticket_void(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk); form = TicketReasonForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try: void_ticket(ticket=ticket, actor=request.user, reason=form.cleaned_data["reason"]); messages.success(request, "Ticket anulado; no se modificó la caja."); return redirect("sale_detail", pk=ticket.sale_id)
        except ValidationError as exc: form.add_error(None, exc)
    return render(request, "generic_form.html", {"form": form, "title": "Anular ticket", "submit_label": "Anular ticket", "cancel_url": reverse("sale_detail", args=[ticket.sale_id]), "dangerous": True, "action_note": "El ticket dejará de permitir el ingreso. Esta acción no devuelve dinero ni modifica la caja."})

@staff_required
def ticket_replace(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk); form = TicketReasonForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try: new = replace_ticket(ticket=ticket, actor=request.user, reason=form.cleaned_data["reason"]); messages.success(request, f"Ticket reemplazado. Nuevo código: {new.code}"); return redirect("sale_detail", pk=ticket.sale_id)
        except ValidationError as exc: form.add_error(None, exc)
    return render(request, "generic_form.html", {"form": form, "title": "Anular y reemplazar ticket", "submit_label": "Anular y reemplazar", "cancel_url": reverse("sale_detail", args=[ticket.sale_id]), "dangerous": True, "action_note": "El código anterior dejará de ser válido y se emitirá uno nuevo. No se modificará la caja."})
