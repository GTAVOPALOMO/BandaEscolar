from datetime import date
from importlib import import_module
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from accounts.models import User
from audit.models import AuditLog
from cash.models import CashMovement, CashPeriod
from cash.services import open_cash, close_cash
from students.models import Student, EnrollmentPeriod
from students.services import withdraw_student, reenroll_student, correct_admission_date
from .models import FeeRateHistory, MonthlyDue, PaymentAllocation, StudentPayment
from .services import cancel_scheduled_rate, create_initial_rate, rate_for, register_payment, student_summary, sync_student_dues, set_next_rate, waive_dues, reverse_waiver, reverse_payment, next_month, month_start

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


class FeeRateDecisionTests(TestCase):
    today = date(2025, 10, 20)

    def setUp(self):
        self.actor = User.objects.create_user(
            "committee-rates",
            password="long-password!",
            role=User.Role.COMMITTEE,
            must_change_password=False,
        )
        self.guardian = User.objects.create_user(
            "guardian-rates",
            password="long-password!",
            role=User.Role.GUARDIAN,
            must_change_password=False,
        )

    def initial(self, amount=2000, effective=date(2025, 1, 18), token="initial-token"):
        return create_initial_rate(
            amount=amount,
            effective_from_month=effective,
            actor=self.actor,
            decision_token=token,
            today=self.today,
        ).rate

    def test_initial_rate_normalizes_month_and_is_idempotent(self):
        first = self.initial()
        repeated = create_initial_rate(
            amount=2000,
            effective_from_month=date(2025, 1, 18),
            actor=self.actor,
            decision_token="initial-token",
            today=self.today,
        )
        self.assertEqual(first.effective_from_month, date(2025, 1, 1))
        self.assertEqual(repeated.rate.pk, first.pk)
        self.assertFalse(repeated.created)
        self.assertEqual(FeeRateHistory.objects.count(), 1)
        audit = AuditLog.objects.get(action="INITIAL_RATE")
        self.assertEqual(audit.actor, self.actor)
        self.assertEqual(audit.after["effective_from_month"], "2025-01-01")

    def test_initial_mid_month_rate_applies_to_the_whole_month(self):
        self.initial(amount=2750, effective=date(2025, 8, 19))
        student = Student.objects.create(name="Sofía", admission_date=date(2025, 8, 25))
        EnrollmentPeriod.objects.create(
            student=student,
            start_date=date(2025, 8, 25),
            created_by=self.actor,
        )
        sync_student_dues(student, through=date(2025, 8, 31), actor=self.actor)
        due = student.dues.get(year=2025, month=8)
        self.assertEqual(due.original_amount, 2750)

    @patch("dues.views.timezone.localdate", return_value=today)
    def test_empty_screen_explains_initial_month(self, _localdate):
        self.client.force_login(self.actor)
        response = self.client.get(reverse("rates"))
        self.assertContains(response, "Sin definir")
        self.assertContains(response, "Registrar tarifa inicial")
        self.assertContains(response, 'type="month"')
        self.assertNotContains(response, "Vigente a partir de")

    def test_initial_rate_cannot_start_in_future(self):
        with self.assertRaisesMessage(ValidationError, "mes actual o a un mes anterior"):
            self.initial(effective=date(2025, 11, 1))

    def test_invalid_amount_is_rejected_without_persistence(self):
        with self.assertRaisesMessage(ValidationError, "entero positivo"):
            self.initial(amount=0)
        self.assertFalse(FeeRateHistory.objects.exists())

    def test_data_migration_marks_earliest_existing_rate_initial(self):
        later = FeeRateHistory.objects.create(
            amount=3000,
            effective_from_month=date(2025, 6, 1),
            decided_by=self.actor,
        )
        earlier = FeeRateHistory.objects.create(
            amount=2000,
            effective_from_month=date(2025, 1, 1),
            decided_by=self.actor,
        )
        migration = import_module("dues.migrations.0002_version_fee_rate_decisions")
        from django.apps import apps
        migration.mark_existing_initial_rate(apps, None)
        earlier.refresh_from_db()
        later.refresh_from_db()
        self.assertEqual(earlier.decision_kind, FeeRateHistory.DecisionKind.INITIAL)
        self.assertEqual(later.decision_kind, FeeRateHistory.DecisionKind.SCHEDULED)

    def test_month_boundaries_and_distinct_consecutive_rates(self):
        self.initial()
        november = set_next_rate(amount=3000, actor=self.actor, today=self.today, decision_token="nov")
        december = set_next_rate(
            amount=4000,
            actor=self.actor,
            today=date(2025, 11, 30),
            decision_token="dec",
        )
        january = set_next_rate(
            amount=5000,
            actor=self.actor,
            today=date(2025, 12, 31),
            decision_token="jan",
        )
        self.assertEqual(november.rate.effective_from_month, date(2025, 11, 1))
        self.assertEqual(december.rate.effective_from_month, date(2025, 12, 1))
        self.assertEqual(january.rate.effective_from_month, date(2026, 1, 1))
        self.assertEqual(rate_for(date(2025, 10, 31)).amount, 2000)
        self.assertEqual(rate_for(date(2025, 11, 30)).amount, 3000)
        self.assertEqual(rate_for(date(2025, 12, 31)).amount, 4000)
        self.assertEqual(rate_for(date(2026, 1, 1)).amount, 5000)

    def test_replacement_requires_reason_and_preserves_both_versions(self):
        self.initial()
        old = set_next_rate(
            amount=3000,
            actor=self.actor,
            today=self.today,
            decision_token="old-schedule",
        ).rate
        with self.assertRaisesMessage(ValidationError, "Explique por qué"):
            set_next_rate(amount=3500, actor=self.actor, today=self.today, decision_token="bad-replacement")
        replacement = set_next_rate(
            amount=3500,
            actor=self.actor,
            today=self.today,
            reason="Acuerdo corregido",
            decision_token="replacement",
        )
        old.refresh_from_db()
        self.assertEqual(old.status, FeeRateHistory.Status.SUPERSEDED)
        self.assertEqual(replacement.rate.replaces, old)
        self.assertEqual(replacement.rate.decision_kind, FeeRateHistory.DecisionKind.REPLACEMENT)
        self.assertEqual(FeeRateHistory.objects.filter(effective_from_month=date(2025, 11, 1)).count(), 2)
        audit = AuditLog.objects.get(action="REPLACE_RATE")
        self.assertEqual(audit.reason, "Acuerdo corregido")
        self.assertEqual(audit.before["amount"], 3000)
        self.assertEqual(audit.after["amount"], 3500)

    def test_only_one_active_version_per_month(self):
        self.initial()
        set_next_rate(amount=3000, actor=self.actor, today=self.today)
        with self.assertRaises(IntegrityError), transaction.atomic():
            FeeRateHistory.objects.create(
                amount=3500,
                effective_from_month=date(2025, 11, 1),
                decided_by=self.actor,
            )

    def test_cancel_future_rate_falls_back_and_keeps_financial_records(self):
        initial = self.initial()
        student = Student.objects.create(name="Lucía", admission_date=date(2025, 10, 1))
        EnrollmentPeriod.objects.create(student=student, start_date=date(2025, 10, 1), created_by=self.actor)
        open_cash(actor=self.actor, opening_balance=0)
        sync_student_dues(student, through=self.today, actor=self.actor)
        with patch("dues.services.timezone.localdate", return_value=self.today):
            payment, _ = register_payment(
                student=student,
                amount=500,
                actor=self.actor,
                idempotency_token="payment-before-cancel",
            )
        cash_ids = list(CashMovement.objects.values_list("pk", flat=True))
        future = set_next_rate(amount=3000, actor=self.actor, today=self.today).rate
        canceled = cancel_scheduled_rate(
            rate=future,
            actor=self.actor,
            reason="El comité dejó sin efecto el aumento",
            today=self.today,
        )
        self.assertEqual(canceled.status, FeeRateHistory.Status.CANCELED)
        self.assertEqual(rate_for(date(2025, 11, 1)), initial)
        self.assertEqual(student.dues.get(year=2025, month=10).original_amount, 2000)
        self.assertEqual(student.payments.get(), payment)
        self.assertEqual(list(CashMovement.objects.values_list("pk", flat=True)), cash_ids)
        audit = AuditLog.objects.get(action="CANCEL_RATE")
        self.assertEqual(audit.reason, "El comité dejó sin efecto el aumento")
        self.assertEqual(audit.after["continuing_rate_id"], initial.pk)

    def test_cancellation_guards_and_new_decision_after_cancel(self):
        initial = self.initial()
        future = set_next_rate(amount=3000, actor=self.actor, today=self.today).rate
        cancel_scheduled_rate(rate=future, actor=self.actor, reason="Cambio de acuerdo", today=self.today)
        with self.assertRaisesMessage(ValidationError, "ya fue cancelada"):
            cancel_scheduled_rate(rate=future, actor=self.actor, reason="Otra vez", today=self.today)
        replacement = set_next_rate(amount=3200, actor=self.actor, today=self.today).rate
        self.assertEqual(replacement.effective_from_month, future.effective_from_month)
        self.assertIsNone(replacement.replaces)
        future.refresh_from_db()
        self.assertEqual(future.status, FeeRateHistory.Status.CANCELED)
        with self.assertRaisesMessage(ValidationError, "no puede cancelarse retroactivamente"):
            cancel_scheduled_rate(rate=initial, actor=self.actor, reason="No procede", today=self.today)

    def test_cancellation_is_blocked_when_dues_were_materialized(self):
        self.initial()
        future = set_next_rate(amount=3000, actor=self.actor, today=self.today).rate
        student = Student.objects.create(name="Mario", admission_date=date(2025, 11, 1))
        MonthlyDue.objects.create(student=student, year=2025, month=11, original_amount=3000)
        with self.assertRaisesMessage(ValidationError, "cuotas materializadas"):
            cancel_scheduled_rate(rate=future, actor=self.actor, reason="No debería", today=self.today)
        future.refresh_from_db()
        self.assertEqual(future.status, FeeRateHistory.Status.ACTIVE)

    @patch("dues.views.timezone.localdate", return_value=today)
    def test_view_ignores_manipulated_effective_date_after_initial(self, _localdate):
        self.initial()
        self.client.force_login(self.actor)
        response = self.client.post(reverse("rates"), {
            "amount": 3100,
            "initial_effective_month": "2030-06-01",
            "reason": "",
            "decision_token": "view-schedule",
        })
        self.assertRedirects(response, reverse("rates"))
        rate = FeeRateHistory.objects.get(decision_token="view-schedule")
        self.assertEqual(rate.effective_from_month, date(2025, 11, 1))

    @patch("dues.views.timezone.localdate", return_value=today)
    def test_screen_states_and_cancel_get_do_not_mutate(self, _localdate):
        self.initial()
        set_next_rate(amount=2500, actor=self.actor, today=date(2025, 9, 15))
        superseded = set_next_rate(amount=3000, actor=self.actor, today=self.today).rate
        canceled = set_next_rate(
            amount=3500,
            actor=self.actor,
            today=self.today,
            reason="Corrección",
        ).rate
        cancel_scheduled_rate(
            rate=canceled,
            actor=self.actor,
            reason="Acuerdo descartado",
            today=self.today,
        )
        scheduled = set_next_rate(amount=3400, actor=self.actor, today=self.today).rate
        self.client.force_login(self.actor)
        response = self.client.get(reverse("rates"))
        self.assertContains(response, "Vigente")
        self.assertContains(response, "Programada")
        self.assertContains(response, "Histórica")
        self.assertContains(response, "Sustituida")
        self.assertContains(response, "Cancelada")
        self.assertContains(response, "Historial de decisiones")
        cancel_url = reverse("rate_cancel", args=[scheduled.pk])
        response = self.client.get(cancel_url)
        self.assertEqual(response.status_code, 200)
        scheduled.refresh_from_db()
        superseded.refresh_from_db()
        self.assertEqual(scheduled.status, FeeRateHistory.Status.ACTIVE)
        self.assertEqual(superseded.status, FeeRateHistory.Status.SUPERSEDED)

    @patch("dues.views.timezone.localdate", return_value=today)
    def test_cancel_view_requires_reason_and_staff_role(self, _localdate):
        self.initial()
        future = set_next_rate(amount=3000, actor=self.actor, today=self.today).rate
        url = reverse("rate_cancel", args=[future.pk])
        self.client.force_login(self.actor)
        response = self.client.post(url, {"reason": ""})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Este campo es obligatorio")
        future.refresh_from_db()
        self.assertEqual(future.status, FeeRateHistory.Status.ACTIVE)
        self.client.force_login(self.guardian)
        self.assertEqual(self.client.get(reverse("rates")).status_code, 403)
        self.assertEqual(self.client.post(url, {"reason": "No autorizado"}).status_code, 403)
