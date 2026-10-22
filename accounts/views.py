import secrets
from datetime import timedelta
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from audit.services import log
from cash.models import CashPeriod, CashMovement
from common.permissions import staff_required, admin_required
from dues.services import sync_student_dues, student_summary
from events.models import Event
from events.queries import upcoming_events
from students.models import Student
from tickets.models import Ticket, TicketSale
from .forms import RateLimitedAuthenticationForm, UserCreateForm, UserRoleForm, ForcedPasswordForm
from .models import User, LoginAttempt

class SecureLoginView(LoginView):
    template_name = "registration/login.html"; authentication_form = RateLimitedAuthenticationForm
    def form_valid(self, form):
        LoginAttempt.objects.create(username=form.cleaned_data.get("username", ""), ip_address=self.request.META.get("REMOTE_ADDR"), successful=True)
        return super().form_valid(form)
    def form_invalid(self, form):
        LoginAttempt.objects.create(username=self.request.POST.get("username", "")[:150], ip_address=self.request.META.get("REMOTE_ADDR"), successful=False)
        return super().form_invalid(form)

class ForcedPasswordChangeView(PasswordChangeView):
    template_name = "registration/password_change.html"; form_class = ForcedPasswordForm; success_url = reverse_lazy("dashboard")
    def form_valid(self, form):
        response = super().form_valid(form)
        self.request.user.must_change_password = False; self.request.user.save(update_fields=["must_change_password"])
        update_session_auth_hash(self.request, self.request.user)
        log(actor=self.request.user, module="accounts", action="PASSWORD_CHANGE", entity="User", entity_id=self.request.user.pk)
        messages.success(self.request, "Contraseña actualizada.")
        return response

@login_required
def dashboard(request):
    if request.user.role == User.Role.GUARDIAN:
        cards = []
        for student in request.user.students.all():
            try: sync_student_dues(student, actor=request.user)
            except ValidationError as exc: messages.warning(request, f"{student.name}: {'; '.join(exc.messages)}")
            cards.append((student, student_summary(student)))
        return render(request, "accounts/guardian_dashboard.html", {"cards": cards, "events": upcoming_events()[:6]})
    if not request.user.is_committee: raise PermissionDenied
    for student in Student.objects.filter(is_active=True):
        try: sync_student_dues(student, actor=request.user)
        except ValidationError as exc: messages.warning(request, f"{student.name}: {'; '.join(exc.messages)}")
    open_period = CashPeriod.objects.filter(status="OPEN").first()
    dues_summary = [student_summary(s) for s in Student.objects.all()]
    ticket_stats = [{"event": e, "sold": e.sales.aggregate(total=Sum("quantity"))["total"] or 0,
                     "used": Ticket.objects.filter(sale__event=e, status=Ticket.Status.USED).count()} for e in Event.objects.filter(has_tickets=True).order_by("-date")[:6]]
    return render(request, "accounts/staff_dashboard.html", {
        "cash": open_period, "active_students": Student.objects.filter(is_active=True).count(),
        "pending_total": sum(x["pending"] for x in dues_summary), "pending_dues": sum(x["pending_count"] for x in dues_summary),
        "students_pending": sum(x["pending"] > 0 for x in dues_summary), "payments": __import__("dues.models", fromlist=["StudentPayment"]).StudentPayment.objects.order_by("-created_at")[:5],
        "movements": CashMovement.objects.order_by("-created_at")[:8], "events": upcoming_events()[:6], "ticket_stats": ticket_stats,
    })

@staff_required
def user_list(request): return render(request, "accounts/user_list.html", {"users": User.objects.order_by("username")})

@staff_required
def user_create(request):
    form = UserCreateForm(request.POST or None, creator=request.user)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            user = form.save(commit=False); password = secrets.token_urlsafe(12); user.set_password(password); user.must_change_password = True; user.save()
            log(actor=request.user, module="accounts", action="CREATE", entity="User", entity_id=user.pk, after={"username": user.username, "role": user.role})
        return render(request, "accounts/temporary_password.html", {"created_user": user, "temporary_password": password})
    return render(request, "generic_form.html", {"form": form, "title": "Crear cuenta", "submit_label": "Crear cuenta", "cancel_url": reverse("user_list")})

@admin_required
def user_role(request, pk):
    user = get_object_or_404(User, pk=pk); form = UserRoleForm(request.POST or None, instance=user)
    if request.method == "POST" and form.is_valid():
        old = user.role
        if old == User.Role.ADMIN and form.cleaned_data["role"] != User.Role.ADMIN and User.objects.filter(role=User.Role.ADMIN, is_active=True).count() <= 1:
            form.add_error("role", "No se puede dejar el sistema sin administradores activos.")
        else:
            form.save(); log(actor=request.user, module="accounts", action="ROLE_CHANGE", entity="User", entity_id=user.pk, before={"role": old}, after={"role": user.role}); return redirect("user_list")
    return render(request, "generic_form.html", {"form": form, "title": f"Cambiar rol de {user.username}", "submit_label": "Cambiar rol", "cancel_url": reverse("user_list"), "dangerous": True})

@staff_required
def user_reset_password(request, pk):
    user = get_object_or_404(User, pk=pk)
    if request.user.role != User.Role.ADMIN and user.role != User.Role.GUARDIAN: raise PermissionDenied
    if request.method != "POST": return render(request, "confirm.html", {"title": "Restablecer contraseña", "message": f"Se generará una contraseña temporal para {user.username}.", "cancel_url": reverse("user_list"), "submit_label": "Restablecer contraseña"})
    password = secrets.token_urlsafe(12); user.set_password(password); user.must_change_password = True; user.save(update_fields=["password", "must_change_password"])
    log(actor=request.user, module="accounts", action="PASSWORD_RESET", entity="User", entity_id=user.pk)
    return render(request, "accounts/temporary_password.html", {"created_user": user, "temporary_password": password})

@admin_required
def user_toggle(request, pk):
    user = get_object_or_404(User, pk=pk)
    if request.method != "POST": return render(request, "confirm.html", {"title": "Cambiar estado", "message": f"Cambiar estado de {user.username}.", "cancel_url": reverse("user_list"), "submit_label": "Cambiar estado"})
    if user.is_active and user.role == User.Role.ADMIN and User.objects.filter(role=User.Role.ADMIN, is_active=True).count() <= 1:
        messages.error(request, "No se puede desactivar el último administrador activo.")
    else:
        user.is_active = not user.is_active; user.save(update_fields=["is_active"]); log(actor=request.user, module="accounts", action="TOGGLE_ACTIVE", entity="User", entity_id=user.pk, after={"is_active": user.is_active})
    return redirect("user_list")
