from datetime import date
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from accounts.models import User
from audit.models import AuditLog
from cash.models import CashMovement, CashPeriod
from cash.services import open_cash, close_cash
from students.models import Student, EnrollmentPeriod
from students.services import withdraw_student, reenroll_student, correct_admission_date
from .models import FeeRateHistory, MonthlyDue, PaymentAllocation, StudentPayment
from .services import register_payment, student_summary, sync_student_dues, set_next_rate, waive_dues, reverse_waiver, reverse_payment, next_month, month_start

class DueServiceTests(TestCase):
    def setUp(self):
        self.actor = User.objects.create_user("committee", password="long-password!", role=User.Role.COMMITTEE, must_change_password=False)
        self.student = Student.objects.create(name="Ana", admission_date=date(2025, 1, 1))
        open_cash(actor=self.actor, opening_balance=0)
    def due(self, month, amount=2000, year=2025): return MonthlyDue.objects.create(student=self.student, year=year, month=month, original_amount=amount)

    def test_partial_payments_count_and_cash(self):
        due = self.due(1)
        register_payment(student=self.student, amount=1000, actor=self.actor, idempotency_token="p1")
        register_payment(student=self.student, amount=500, actor=self.actor, idempotency_token="p2")
        due.refresh_from_db(); summary = student_summary(self.student)
        self.assertEqual((due.display_status, due.applied_amount, due.pending_amount), ("PARCIAL", 1500, 500))
        self.assertEqual(summary["pending_count"], 1); self.assertEqual(CashMovement.objects.filter(origin="DUE").aggregate_total if False else sum(m.amount for m in CashMovement.objects.all()), 1500)

    def test_oldest_first_and_partial_count(self):
        dues = [self.due(m) for m in (1,2,3)]
        register_payment(student=self.student, amount=2500, actor=self.actor, idempotency_token="oldest")
        for d in dues: d.refresh_from_db()
        self.assertEqual([d.display_status for d in dues], ["PAGADA", "PARCIAL", "PENDIENTE"])
        self.assertEqual(student_summary(self.student)["pending"], 3500); self.assertEqual(student_summary(self.student)["pending_count"], 2)

    def test_credit_applies_to_new_due_without_cash(self):
        current = month_start(timezone.localdate()); following = next_month(current)
        EnrollmentPeriod.objects.create(student=self.student, start_date=current, created_by=self.actor)
        FeeRateHistory.objects.create(amount=2000, effective_from_month=current, decided_by=self.actor)
        FeeRateHistory.objects.create(amount=3000, effective_from_month=following, decided_by=self.actor)
        sync_student_dues(self.student, through=current, actor=self.actor)
        register_payment(student=self.student, amount=10000, actor=self.actor, idempotency_token="credit")
        self.assertEqual(student_summary(self.student)["credit"], 8000)
        sync_student_dues(self.student, through=following, actor=self.actor)
        feb = self.student.dues.get(year=following.year, month=following.month)
        self.assertEqual((feb.display_status, student_summary(self.student)["credit"]), ("PAGADA", 5000))
        self.assertEqual(CashMovement.objects.get(origin="DUE").amount, 10000)

    def test_rate_change_only_next_month(self):
        FeeRateHistory.objects.create(amount=2000, effective_from_month=date(2025,1,1), decided_by=self.actor)
        EnrollmentPeriod.objects.create(student=self.student, start_date=date(2025,10,20), created_by=self.actor)
        sync_student_dues(self.student, through=date(2025,10,20), actor=self.actor)
        set_next_rate(amount=3000, actor=self.actor, today=date(2025,10,20))
        sync_student_dues(self.student, through=date(2025,11,1), actor=self.actor)
        self.assertEqual(self.student.dues.get(month=10).original_amount, 2000); self.assertEqual(self.student.dues.get(month=11).original_amount, 3000)

    def test_admission_date_correction_recalculates_without_duplicates(self):
        current = month_start(timezone.localdate())
        previous = date(current.year - (current.month == 1), 12 if current.month == 1 else current.month - 1, 1)
        FeeRateHistory.objects.create(amount=2000, effective_from_month=previous, decided_by=self.actor)
        EnrollmentPeriod.objects.create(student=self.student, start_date=current, created_by=self.actor)
        self.student.admission_date = current; self.student.save(update_fields=["admission_date"])
        sync_student_dues(self.student, actor=self.actor)
        correct_admission_date(student=self.student, admission_date=previous, actor=self.actor, reason="Corrección documental")
        self.assertEqual(self.student.dues.filter(status="ORDINARY").count(), 2)
        sync_student_dues(self.student, actor=self.actor); self.assertEqual(self.student.dues.count(), 2)

    def test_historical_sync_is_idempotent_and_full_entry_month(self):
        FeeRateHistory.objects.create(amount=2000, effective_from_month=date(2025,1,1), decided_by=self.actor)
        EnrollmentPeriod.objects.create(student=self.student, start_date=date(2025,8,20), created_by=self.actor)
        for _ in range(3): sync_student_dues(self.student, through=date(2025,10,1), actor=self.actor)
        self.assertEqual(self.student.dues.count(), 3); self.assertTrue(self.student.dues.filter(month=8, original_amount=2000).exists())

    def test_missing_historical_rate_rejected(self):
        EnrollmentPeriod.objects.create(student=self.student, start_date=date(2024,1,1), created_by=self.actor)
        FeeRateHistory.objects.create(amount=2000, effective_from_month=date(2025,1,1), decided_by=self.actor)
        with self.assertRaisesMessage(ValidationError, "Falta una tarifa"): sync_student_dues(self.student, through=date(2025,1,1))
        self.assertEqual(self.student.dues.count(), 0)

    def test_waive_multiple_reject_partial_and_reverse(self):
        dues = [self.due(m) for m in (1,2,3)]
        group = waive_dues(dues=dues, actor=self.actor, reason="Regularización inicial")
        self.assertEqual(self.student.dues.filter(status="WAIVED").count(), 3); self.assertEqual(CashMovement.objects.count(), 0)
        waiver = group.waivers.first(); reverse_waiver(waiver=waiver, actor=self.actor, reason="Corrección")
        waiver.refresh_from_db(); waiver.due.refresh_from_db(); self.assertEqual(waiver.due.status, "ORDINARY"); self.assertTrue(waiver.reversed_at)
        register_payment(student=self.student, amount=500, actor=self.actor, idempotency_token="part")
        partial = self.student.dues.filter(status="ORDINARY").first()
        with self.assertRaises(ValidationError): waive_dues(dues=[partial], actor=self.actor, reason="No procede")

    def test_retirement_releases_allocations_and_reentry(self):
        period = EnrollmentPeriod.objects.create(student=self.student, start_date=date(2025,9,1), created_by=self.actor)
        sep, octo = self.due(9), self.due(10)
        payment = StudentPayment.objects.create(student=self.student, amount=500, idempotency_token="legacy", registered_by=self.actor)
        PaymentAllocation.objects.create(payment=payment, due=octo, amount=500)
        withdraw_student(student=self.student, withdrawal_date=date(2025,10,15), actor=self.actor, reason="Retiro")
        sep.refresh_from_db(); octo.refresh_from_db(); self.assertEqual(sep.display_status, "PENDIENTE"); self.assertEqual(octo.display_status, "SIN_CARGO_POR_RETIRO")
        self.assertEqual(payment.credit, 500); self.assertEqual(CashMovement.objects.count(), 0)
        FeeRateHistory.objects.create(amount=2000, effective_from_month=date(2025,1,1), decided_by=self.actor)
        reenroll_student(student=self.student, start_date=date(2025,12,1), actor=self.actor)
        sync_student_dues(self.student, through=date(2025,12,1), actor=self.actor)
        self.assertFalse(self.student.dues.filter(month=11).exists()); self.assertTrue(self.student.dues.filter(month=12).exists())

    def test_payment_idempotency(self):
        self.due(1)
        first, created1 = register_payment(student=self.student, amount=1000, actor=self.actor, idempotency_token="same")
        second, created2 = register_payment(student=self.student, amount=1000, actor=self.actor, idempotency_token="same")
        self.assertEqual(first.pk, second.pk); self.assertTrue(created1); self.assertFalse(created2)
        self.assertEqual(StudentPayment.objects.count(), 1); self.assertEqual(CashMovement.objects.count(), 1)

    def test_reverse_closed_payment_in_new_cash_and_insufficient_is_atomic(self):
        self.due(1); payment, _ = register_payment(student=self.student, amount=2000, actor=self.actor, idempotency_token="reverse")
        old = close_cash(actor=self.actor); new = open_cash(actor=self.actor)
        reverse_payment(payment=payment, actor=self.actor, reason="Error de digitación")
        old.refresh_from_db(); self.assertEqual(old.closing_balance, 2000); self.assertEqual(new.movements.get().kind, "OUT")
        with self.assertRaises(ValidationError): reverse_payment(payment=payment, actor=self.actor, reason="Otra vez")
        other = self.due(2); payment2, _ = register_payment(student=self.student, amount=1, actor=self.actor, idempotency_token="tiny")
        close_cash(actor=self.actor); open_cash(actor=self.actor, opening_balance=None)
        # Vaciar la caja actual mediante egreso manual para hacer insuficiente la reversión.
        from cash.services import add_movement
        add_movement(actor=self.actor, kind="OUT", origin="MANUAL", amount=1, detail="Vaciar")
        with self.assertRaises(ValidationError): reverse_payment(payment=payment2, actor=self.actor, reason="Sin saldo")
        payment2.refresh_from_db(); self.assertIsNone(payment2.reversed_at)
