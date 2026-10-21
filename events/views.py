import calendar
import mimetypes
from datetime import date, timedelta
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.http import FileResponse, Http404
from django.utils import timezone
from audit.services import log
from common.permissions import staff_required
from .forms import EventForm
from .models import Event

def home(request):
    try:
        year, month = map(int, request.GET.get("mes", "").split("-"))
        selected = date(year, month, 1)
    except Exception: selected = timezone.localdate().replace(day=1)
    cal = calendar.Calendar(firstweekday=0)
    weeks = []
    events = Event.objects.filter(is_active=True, date__year=selected.year, date__month=selected.month).order_by("date", "time")
    by_day = {}
    for event in events: by_day.setdefault(event.date.day, []).append(event)
    for week in cal.monthdayscalendar(selected.year, selected.month): weeks.append([(day, by_day.get(day, [])) for day in week])
    prev = (selected.replace(day=1) - timedelta(days=1)).replace(day=1); nxt = (selected.replace(day=28) + timedelta(days=4)).replace(day=1)
    return render(request, "events/home.html", {"weeks": weeks, "events": events, "selected": selected, "prev": prev, "next": nxt})

def event_detail(request, pk): return render(request, "events/detail.html", {"event": get_object_or_404(Event, pk=pk, is_active=True)})

def event_image(request, pk):
    event = get_object_or_404(Event, pk=pk, is_active=True)
    if not event.image: raise Http404
    return FileResponse(event.image.open("rb"), content_type=mimetypes.guess_type(event.image.name)[0] or "application/octet-stream")

@staff_required
def event_list(request): return render(request, "events/manage.html", {"events": Event.objects.all()})

@staff_required
def event_create(request):
    form = EventForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        event = form.save(commit=False); event.created_by = request.user; event.save(); log(actor=request.user, module="events", action="CREATE", entity="Event", entity_id=event.pk, after={"name": event.name, "date": event.date.isoformat(), "ticket_price": event.ticket_price}); messages.success(request, "Evento creado."); return redirect("event_manage")
    return render(request, "generic_form.html", {"form": form, "title": "Crear evento", "multipart": True})

@staff_required
def event_edit(request, pk):
    event = get_object_or_404(Event, pk=pk); old = {"name": event.name, "date": event.date.isoformat(), "ticket_price": event.ticket_price, "is_active": event.is_active}; form = EventForm(request.POST or None, request.FILES or None, instance=event)
    if request.method == "POST" and form.is_valid():
        form.save(); log(actor=request.user, module="events", action="EDIT", entity="Event", entity_id=event.pk, before=old, after={"name": event.name, "date": event.date.isoformat(), "ticket_price": event.ticket_price, "is_active": event.is_active}); messages.success(request, "Evento actualizado."); return redirect("event_manage")
    return render(request, "generic_form.html", {"form": form, "title": "Editar evento", "multipart": True})

@staff_required
def event_toggle(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if request.method != "POST": return render(request, "confirm.html", {"title": "Cambiar visibilidad", "message": "El historial financiero y los tickets no cambiarán."})
    event.is_active = not event.is_active; event.save(update_fields=["is_active", "updated_at"]); log(actor=request.user, module="events", action="TOGGLE", entity="Event", entity_id=pk, after={"is_active": event.is_active}); return redirect("event_manage")
