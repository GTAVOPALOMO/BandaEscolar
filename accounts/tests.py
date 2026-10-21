from datetime import date, time
from django.test import TestCase
from django.urls import reverse
from accounts.models import User
from cash.services import open_cash
from dues.models import FeeRateHistory, MonthlyDue
from events.models import Event
from students.models import Student, StudentGuardian
from audit.models import AuditLog

class PermissionAndViewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin", password="long-password!", role="ADMIN", must_change_password=False)
        self.committee = User.objects.create_user("committee", password="long-password!", role="COMMITTEE", must_change_password=False)
        self.g1 = User.objects.create_user("guardian1", password="long-password!", role="GUARDIAN", must_change_password=False)
        self.g2 = User.objects.create_user("guardian2", password="long-password!", role="GUARDIAN", must_change_password=False)
        self.s1 = Student.objects.create(name="Niña Uno", admission_date=date(2026,1,1)); self.s2 = Student.objects.create(name="Niño Dos", admission_date=date(2026,1,1))
        StudentGuardian.objects.create(student=self.s1, guardian=self.g1, linked_by=self.committee); StudentGuardian.objects.create(student=self.s2, guardian=self.g2, linked_by=self.committee)
        MonthlyDue.objects.create(student=self.s1, year=2026, month=1, original_amount=2000)
    def test_guest_private_routes_redirect_or_forbid(self):
        for url in [reverse("student_detail", args=[self.s1.pk]), reverse("cash_home"), reverse("audit_list"), reverse("sale_list")]:
            self.assertEqual(self.client.get(url).status_code, 302)
    def test_guardian_cannot_enumerate_other_student(self):
        self.client.force_login(self.g1)
        self.assertEqual(self.client.get(reverse("student_detail", args=[self.s1.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("student_detail", args=[self.s2.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("statement_pdf", args=[self.s2.pk])).status_code, 404)
    def test_committee_cannot_change_roles_admin_can(self):
        self.client.force_login(self.committee); self.assertEqual(self.client.post(reverse("user_role", args=[self.g1.pk]), {"role":"COMMITTEE"}).status_code, 403)
        self.assertEqual(self.client.post(reverse("user_reset_password", args=[self.admin.pk])).status_code, 403)
        self.client.force_login(self.admin); self.assertEqual(self.client.post(reverse("user_role", args=[self.g1.pk]), {"role":"COMMITTEE"}).status_code, 302)
        self.g1.refresh_from_db(); self.assertEqual(self.g1.role, "COMMITTEE")
    def test_cannot_disable_last_admin(self):
        self.client.force_login(self.admin); self.client.post(reverse("user_toggle", args=[self.admin.pk])); self.admin.refresh_from_db(); self.assertTrue(self.admin.is_active)
    def test_statement_pdf_is_private_and_valid(self):
        self.client.force_login(self.g1); response = self.client.get(reverse("statement_pdf", args=[self.s1.pk])); self.assertEqual(response.status_code, 200); self.assertEqual(response["Content-Type"], "application/pdf")
    def test_public_event_visible_without_financial_data(self):
        event = Event.objects.create(name="Desfile", date=date(2026,10,20), time=time(9), place="Centro", description="Público", created_by=self.committee)
        response = self.client.get(reverse("home")+"?mes=2026-10"); self.assertContains(response, "Desfile"); self.assertNotContains(response, "Niña Uno")
    def test_staff_dashboard_renders(self):
        self.client.force_login(self.committee); self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)
    def test_force_password_change(self):
        temp = User.objects.create_user("temp", password="temporary-long!", role="GUARDIAN", must_change_password=True)
        self.client.force_login(temp); response = self.client.get(reverse("dashboard")); self.assertRedirects(response, reverse("force_password_change"))
    def test_audit_log_cannot_be_updated_or_deleted_as_instance(self):
        item = AuditLog.objects.create(actor=self.admin, module="test", action="CREATE", entity="Thing")
        item.reason = "cambio"
        with self.assertRaises(ValueError): item.save()
        with self.assertRaises(ValueError): item.delete()
