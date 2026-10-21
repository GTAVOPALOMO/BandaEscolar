from django.db.models import Q
from django.shortcuts import render
from common.permissions import staff_required
from .models import AuditLog

@staff_required
def audit_list(request):
    logs = AuditLog.objects.select_related("actor")
    q = request.GET.get("q", "").strip(); module = request.GET.get("module", "").strip(); action = request.GET.get("action", "").strip()
    if q: logs = logs.filter(Q(entity__icontains=q) | Q(entity_id__icontains=q) | Q(reason__icontains=q) | Q(actor__username__icontains=q))
    if module: logs = logs.filter(module=module)
    if action: logs = logs.filter(action__icontains=action)
    return render(request, "audit/list.html", {"logs": logs[:500], "modules": AuditLog.objects.values_list("module", flat=True).distinct(), "filters": request.GET})
