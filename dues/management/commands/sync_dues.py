from django.core.management.base import BaseCommand
from students.models import Student
from dues.services import sync_student_dues
class Command(BaseCommand):
    help = "Sincroniza de forma idempotente las cuotas hasta el mes actual."
    def handle(self, *args, **options):
        total = 0
        for student in Student.objects.filter(is_active=True): total += len(sync_student_dues(student))
        self.stdout.write(self.style.SUCCESS(f"Cuotas creadas: {total}"))
