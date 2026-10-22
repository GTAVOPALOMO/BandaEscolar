"""Public event timing uses the school's timezone and scheduled start."""
from django.db.models import Q
from django.utils import timezone

from .models import Event


def event_clock():
    return timezone.localtime(timezone.now(), timezone.get_default_timezone())


def upcoming_events(now=None):
    # There is no end time in Event. Once its start is reached, it is no
    # longer upcoming; it remains available in the historical calendar.
    now = now or event_clock()
    return Event.objects.filter(is_active=True).filter(
        Q(date__gt=now.date()) | Q(date=now.date(), time__gt=now.time())
    ).order_by("date", "time", "pk")
