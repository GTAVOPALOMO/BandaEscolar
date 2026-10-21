from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from audit.services import log
from dues.models import MonthlyDue
from dues.models import PaymentAllocation
from dues.services import sync_student_dues, rebuild_allocations, month_start, active_months
from .models import Student, StudentGuardian, EnrollmentPeriod

@transaction.atomic
def enroll_student(*, name, admission_date, guardians, actor):
    if not name.strip(): raise ValidationError("El nombre es obligatorio.")
    if admission_date > timezone.localdate(): raise ValidationError("La fecha de ingreso no puede estar en el futuro.")
    guardians = list(guardians)
    if not guardians: raise ValidationError("Vincule al menos un encargado.")
    student = Student.objects.create(name=name.strip(), admission_date=admission_date)
    EnrollmentPeriod.objects.create(student=student, start_date=admission_date, created_by=actor)
    for guardian in guardians:
        link = StudentGuardian(student=student, guardian=guardian, linked_by=actor); link.full_clean(); link.save()
    sync_student_dues(student, actor=actor)
    log(actor=actor, module="students", action="ENROLL", entity="Student", entity_id=student.pk,
        after={"name": student.name, "admission_date": admission_date.isoformat(), "guardians": [g.pk for g in guardians]})
    return student

@transaction.atomic
def withdraw_student(*, student, withdrawal_date, actor, reason=""):
    if withdrawal_date > timezone.localdate(): raise ValidationError("La fecha de retiro no puede estar en el futuro.")
    student = Student.objects.select_for_update().get(pk=student.pk)
    period = student.enrollment_periods.filter(end_date__isnull=True).order_by("-start_date").first()
    if not period: raise ValidationError("El estudiante no tiene un período activo.")
    if withdrawal_date < period.start_date: raise ValidationError("La fecha de retiro no puede preceder al ingreso.")
    period.end_date, period.ended_by, period.withdrawal_reason = withdrawal_date, actor, reason
    period.save(update_fields=["end_date", "ended_by", "withdrawal_reason"])
    student.is_active = False; student.save(update_fields=["is_active"])
    affected = student.dues.filter(year__gt=withdrawal_date.year) | student.dues.filter(year=withdrawal_date.year, month__gte=withdrawal_date.month)
    for due in affected:
        if due.status != MonthlyDue.Status.WAIVED:
            due.status = MonthlyDue.Status.NO_CHARGE; due.save(update_fields=["status", "updated_at"])
    PaymentAllocation.objects.filter(due__in=affected, is_active=True).update(is_active=False, voided_at=timezone.now(), reason="Retiro del estudiante")
    log(actor=actor, module="students", action="WITHDRAW", entity="Student", entity_id=student.pk, reason=reason,
        after={"withdrawal_date": withdrawal_date.isoformat()})
    return student

@transaction.atomic
def reenroll_student(*, student, start_date, actor):
    if start_date > timezone.localdate(): raise ValidationError("La fecha de reingreso no puede estar en el futuro.")
    student = Student.objects.select_for_update().get(pk=student.pk)
    if student.is_active: raise ValidationError("El estudiante ya está activo.")
    last = student.enrollment_periods.order_by("-end_date").first()
    if last and last.end_date and start_date < last.end_date: raise ValidationError("El reingreso no puede preceder al último retiro.")
    EnrollmentPeriod.objects.create(student=student, start_date=start_date, created_by=actor)
    student.is_active = True; student.save(update_fields=["is_active"])
    sync_student_dues(student, actor=actor)
    log(actor=actor, module="students", action="REENROLL", entity="Student", entity_id=student.pk,
        after={"start_date": start_date.isoformat()})
    return student

@transaction.atomic
def correct_admission_date(*, student, admission_date, actor, reason):
    reason = (reason or "").strip()
    if not reason: raise ValidationError("El motivo de la corrección es obligatorio.")
    if admission_date > timezone.localdate(): raise ValidationError("La fecha de ingreso no puede estar en el futuro.")
    student = Student.objects.select_for_update().get(pk=student.pk)
    first = student.enrollment_periods.order_by("start_date", "pk").first()
    if not first: raise ValidationError("No existe un período de matrícula que corregir.")
    if first.end_date and admission_date > first.end_date: raise ValidationError("La admisión no puede quedar después del retiro.")
    old = student.admission_date
    student.admission_date = admission_date; student.save(update_fields=["admission_date"])
    first.start_date = admission_date; first.save(update_fields=["start_date"])
    valid = {(m.year, m.month) for m in active_months(student, timezone.localdate())}
    to_disable = list(student.dues.filter(status=MonthlyDue.Status.ORDINARY))
    affected = [d for d in to_disable if (d.year, d.month) not in valid]
    for due in affected:
        due.status = MonthlyDue.Status.NO_CHARGE; due.save(update_fields=["status", "updated_at"])
    PaymentAllocation.objects.filter(due__in=affected, is_active=True).update(is_active=False, voided_at=timezone.now(), reason="Corrección de ingreso")
    sync_student_dues(student, actor=actor)
    rebuild_allocations(student, reason="Corrección de fecha de ingreso", actor=actor)
    log(actor=actor, module="students", action="CORRECT_ADMISSION", entity="Student", entity_id=student.pk, reason=reason,
        before={"admission_date": old.isoformat()}, after={"admission_date": admission_date.isoformat()})
    return student
