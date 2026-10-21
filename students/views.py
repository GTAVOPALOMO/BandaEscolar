from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from audit.services import log
from common.permissions import staff_required
from dues.services import sync_student_dues, student_summary
from .forms import StudentCreateForm, StudentEditForm, WithdrawalForm, ReenrollForm, GuardianLinkForm
from .models import Student, StudentGuardian
from .services import enroll_student, withdraw_student, reenroll_student, correct_admission_date

def accessible_student(user, pk):
    qs = Student.objects.all()
    if not user.is_committee: qs = qs.filter(guardians=user)
    return get_object_or_404(qs, pk=pk)

@staff_required
def student_list(request): return render(request, "students/list.html", {"students": Student.objects.order_by("name")})

@staff_required
def student_create(request):
    form = StudentCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            student = enroll_student(name=form.cleaned_data["name"], admission_date=form.cleaned_data["admission_date"], guardians=form.cleaned_data["guardians"], actor=request.user)
            messages.success(request, "Estudiante matriculado y cuotas sincronizadas."); return redirect("student_detail", pk=student.pk)
        except ValidationError as exc: form.add_error(None, exc)
    return render(request, "students/form.html", {"form": form})

@login_required
def student_detail(request, pk):
    student = accessible_student(request.user, pk)
    try: sync_student_dues(student, actor=request.user)
    except ValidationError as exc: messages.warning(request, "; ".join(exc.messages))
    return render(request, "students/detail.html", {"student": student, "summary": student_summary(student)})

@staff_required
def student_edit(request, pk):
    student = get_object_or_404(Student, pk=pk); form = StudentEditForm(request.POST or None, initial={"name": student.name, "admission_date": student.admission_date})
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                old_name = student.name; student.name = form.cleaned_data["name"].strip(); student.save(update_fields=["name"])
                correct_admission_date(student=student, admission_date=form.cleaned_data["admission_date"], actor=request.user, reason=form.cleaned_data["reason"])
                log(actor=request.user, module="students", action="EDIT_NAME", entity="Student", entity_id=student.pk, before={"name": old_name}, after={"name": student.name})
            return redirect("student_detail", pk=pk)
        except ValidationError as exc: form.add_error(None, exc)
    return render(request, "generic_form.html", {"form": form, "title": "Editar estudiante"})

@staff_required
def student_withdraw(request, pk):
    student = get_object_or_404(Student, pk=pk); form = WithdrawalForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try: withdraw_student(student=student, withdrawal_date=form.cleaned_data["withdrawal_date"], actor=request.user, reason=form.cleaned_data["reason"]); messages.success(request, "Retiro registrado; las asignaciones liberadas quedaron como crédito."); return redirect("student_detail", pk=pk)
        except ValidationError as exc: form.add_error(None, exc)
    return render(request, "generic_form.html", {"form": form, "title": f"Retirar a {student.name}"})

@staff_required
def student_reenroll(request, pk):
    student = get_object_or_404(Student, pk=pk); form = ReenrollForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try: reenroll_student(student=student, start_date=form.cleaned_data["start_date"], actor=request.user); messages.success(request, "Reingreso registrado."); return redirect("student_detail", pk=pk)
        except ValidationError as exc: form.add_error(None, exc)
    return render(request, "generic_form.html", {"form": form, "title": f"Reingresar a {student.name}"})

@staff_required
def guardian_link(request, pk):
    student = get_object_or_404(Student, pk=pk); form = GuardianLinkForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        link, created = StudentGuardian.objects.get_or_create(student=student, guardian=form.cleaned_data["guardian"], defaults={"linked_by": request.user})
        if created: log(actor=request.user, module="students", action="LINK_GUARDIAN", entity="Student", entity_id=pk, after={"guardian": link.guardian_id})
        return redirect("student_detail", pk=pk)
    return render(request, "generic_form.html", {"form": form, "title": "Vincular encargado"})

@staff_required
def guardian_unlink(request, pk, link_pk):
    link = get_object_or_404(StudentGuardian, pk=link_pk, student_id=pk)
    if request.method != "POST": return render(request, "confirm.html", {"title": "Desvincular encargado", "message": "Esta persona dejará de ver al estudiante."})
    if StudentGuardian.objects.filter(student_id=pk).count() <= 1: messages.error(request, "El estudiante debe conservar al menos un encargado.")
    else:
        gid = link.guardian_id; link.delete(); log(actor=request.user, module="students", action="UNLINK_GUARDIAN", entity="Student", entity_id=pk, before={"guardian": gid})
    return redirect("student_detail", pk=pk)
