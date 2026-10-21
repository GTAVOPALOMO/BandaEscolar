from django.core.exceptions import ValidationError
from django.test import TestCase
from accounts.models import User
from .models import CashMovement, CashPeriod
from .services import open_cash, add_movement, close_cash, reverse_manual_movement

class CashTests(TestCase):
    def setUp(self): self.user = User.objects.create_user("cash", password="long-password!", role="COMMITTEE")
    def test_close_and_carry_without_duplicate(self):
        first = open_cash(actor=self.user, opening_balance=50000)
        add_movement(actor=self.user, kind="IN", origin="MANUAL", amount=2000, detail="Ingreso")
        add_movement(actor=self.user, kind="OUT", origin="MANUAL", amount=10000, detail="Egreso")
        close_cash(actor=self.user); first.refresh_from_db(); self.assertEqual(first.closing_balance, 42000)
        second = open_cash(actor=self.user); self.assertEqual(second.opening_balance, 42000); self.assertEqual(second.movements.count(), 0)
    def test_closed_rejects_and_overspend_atomic(self):
        with self.assertRaises(ValidationError): add_movement(actor=self.user, kind="IN", origin="MANUAL", amount=1, detail="No")
        period = open_cash(actor=self.user, opening_balance=10)
        with self.assertRaises(ValidationError): add_movement(actor=self.user, kind="OUT", origin="MANUAL", amount=11, detail="Exceso")
        self.assertEqual(period.movements.count(), 0)
    def test_one_open_period_constraint_service(self):
        open_cash(actor=self.user, opening_balance=0)
        with self.assertRaises(ValidationError): open_cash(actor=self.user, opening_balance=0)
    def test_manual_correction_is_countermovement(self):
        period = open_cash(actor=self.user, opening_balance=100)
        original = add_movement(actor=self.user, kind="OUT", origin="MANUAL", amount=40, detail="Compra errónea")
        correction = reverse_manual_movement(movement=original, actor=self.user, reason="Digitación")
        self.assertEqual((correction.kind, correction.amount, correction.original_movement_id), ("IN", 40, original.pk))
        self.assertEqual(period.current_balance, 100)
        with self.assertRaises(ValidationError): reverse_manual_movement(movement=original, actor=self.user, reason="Doble")
