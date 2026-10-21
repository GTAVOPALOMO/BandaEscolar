from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

class Student(models.Model):
    name = models.CharField(max_length=150, db_index=True)
    admission_date = models.DateField()
    is_active = models.BooleanField(default=True, db_index=True)
    guardians = models.ManyToManyField(settings.AUTH_USER_MODEL, through="StudentGuardian", through_fields=("student", "guardian"), related_name="students")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self): return self.name

class StudentGuardian(models.Model):
    student = models.ForeignKey(Student, on_delete=models.PROTECT)
    guardian = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    linked_at = models.DateTimeField(auto_now_add=True)
    linked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="guardian_links_created")
    class Meta:
        constraints = [models.UniqueConstraint(fields=["student", "guardian"], name="unique_student_guardian")]

    def clean(self):
        if self.guardian_id and self.guardian.role != "GUARDIAN":
            raise ValidationError("Solo una cuenta de encargado puede vincularse al estudiante.")

class EnrollmentPeriod(models.Model):
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="enrollment_periods")
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    withdrawal_reason = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="enrollments_created")
    ended_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="enrollments_ended")
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["start_date", "pk"]
        constraints = [models.CheckConstraint(condition=models.Q(end_date__isnull=True) | models.Q(end_date__gte=models.F("start_date")), name="period_dates_valid")]
