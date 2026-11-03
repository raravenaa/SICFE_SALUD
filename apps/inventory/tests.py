import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.db import DatabaseError, close_old_connections, connection, transaction
from django.db.models import Sum
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    AuditEvent,
    Balance,
    Lot,
    LotBalance,
    Movement,
    MovementLine,
    Product,
    Warehouse,
    WarehouseAccess,
)
from .services import cancel_draft, confirm_movement, create_draft, save_product


class Scenario:
    def setup_scenario(self):
        call_command("bootstrap_roles", stdout=StringIO())
        self.user = get_user_model().objects.create_user(username="operador")
        self.user.groups.add(Group.objects.get(name="Operador"))
        self.warehouse = Warehouse.objects.create(code="FARM", name="Farmacia de prueba")
        WarehouseAccess.objects.create(user=self.user, warehouse=self.warehouse)
        self.product = Product.objects.create(code="DEMO", name="Producto de prueba", unit="unidad")
        self.expiry = timezone.localdate() + timedelta(days=365)

    def line(self, quantity="100", cost="1000", lot="A", expiry=None, product=None):
        return {
            "product_id": (product or self.product).pk,
            "lot_code": lot,
            "expires_on": expiry or self.expiry,
            "quantity": Decimal(quantity),
            "unit_cost": Decimal(cost) if cost is not None else None,
        }

    def draft(self, kind=Movement.Kind.RECEIPT, lines=None, **kwargs):
        return create_draft(
            user=kwargs.pop("user", self.user),
            warehouse_id=kwargs.pop("warehouse_id", self.warehouse.pk),
            kind=kind,
            reference="Documento de prueba",
            reason="Prueba automatizada",
            lines=lines or [self.line()],
            request_key=kwargs.pop("request_key", uuid.uuid4()),
            **kwargs,
        )

    def confirm(self, movement):
        return confirm_movement(user=self.user, movement_id=movement.pk)


class InventoryTests(Scenario, TestCase):
    def setUp(self):
        self.setup_scenario()

    def test_weighted_average_example_and_lot_totals(self):
        self.confirm(self.draft())
        self.confirm(self.draft(lines=[self.line("50", "1300", "B")]))
        balance = Balance.objects.get()
        self.assertEqual(
            (balance.quantity, balance.value, balance.average_cost),
            (Decimal("150"), Decimal("165000"), Decimal("1100")),
        )
        issue = self.confirm(self.draft(Movement.Kind.ISSUE, [self.line("20", None)]))
        balance.refresh_from_db()
        self.assertEqual((balance.quantity, balance.value), (Decimal("130"), Decimal("143000")))
        self.assertEqual(LotBalance.objects.get(lot__code="A").quantity, Decimal("80"))
        self.assertEqual(
            LotBalance.objects.aggregate(total=Sum("quantity"))["total"], balance.quantity
        )
        self.assertEqual(issue.lines.get().applied_value, Decimal("22000"))
        self.assertEqual(issue.confirmed_by, self.user)

    def test_draft_and_cancel_do_not_change_stock(self):
        draft = self.draft()
        self.assertFalse(Balance.objects.exists())
        cancel_draft(user=self.user, movement_id=draft.pk)
        with self.assertRaises(ValidationError):
            self.confirm(draft)
        self.assertFalse(Balance.objects.exists())

    def test_request_and_confirmation_are_idempotent(self):
        key = uuid.uuid4()
        first = self.draft(request_key=key)
        second = self.draft(request_key=key)
        self.assertEqual(first.pk, second.pk)
        self.confirm(first)
        self.confirm(first)
        self.assertEqual(Balance.objects.get().quantity, Decimal("100"))
        self.assertEqual(AuditEvent.objects.filter(action="movement.confirmed").count(), 1)
        with self.assertRaises(ValidationError):
            self.draft(request_key=key, lines=[self.line("101")])

    def test_insufficient_lot_rolls_back_all_lines(self):
        self.confirm(self.draft(lines=[self.line("10"), self.line("90", lot="B")]))
        issue = self.draft(Movement.Kind.ISSUE, [self.line("5", None, "B"), self.line("11", None)])
        with self.assertRaises(ValidationError):
            self.confirm(issue)
        self.assertEqual(Balance.objects.get().quantity, Decimal("100"))
        self.assertEqual(LotBalance.objects.get(lot__code="B").quantity, Decimal("90"))
        self.assertEqual(list(issue.lines.values_list("applied_value", flat=True)), [0, 0])
        issue.refresh_from_db()
        self.assertEqual(issue.status, Movement.Status.DRAFT)
        self.assertFalse(
            AuditEvent.objects.filter(movement=issue, action="movement.confirmed").exists()
        )

    def test_duplicate_lot_lines_cannot_overdraw(self):
        self.confirm(self.draft(lines=[self.line("10")]))
        issue = self.draft(Movement.Kind.ISSUE, [self.line("6", None), self.line("6", None)])
        with self.assertRaises(ValidationError):
            self.confirm(issue)
        self.assertEqual(Balance.objects.get().quantity, Decimal("10"))

    def test_rounding_residual_is_removed_on_full_depletion(self):
        self.confirm(self.draft(lines=[self.line("1", "1"), self.line("2", "0", "B")]))
        self.confirm(self.draft(Movement.Kind.ISSUE, [self.line("1", None)]))
        self.confirm(self.draft(Movement.Kind.ISSUE, [self.line("2", None, "B")]))
        balance = Balance.objects.get()
        self.assertEqual((balance.quantity, balance.value), (0, 0))
        total = MovementLine.objects.filter(movement__kind=Movement.Kind.ISSUE).aggregate(
            value=Sum("applied_value")
        )["value"]
        self.assertEqual(total, Decimal("1"))

    def test_expired_stock_remains_physical_but_cannot_be_issued(self):
        expiry = timezone.localdate() - timedelta(days=1)
        self.confirm(self.draft(lines=[self.line(expiry=expiry)]))
        stock = LotBalance.objects.select_related("lot__product").get()
        self.assertEqual((stock.quantity, stock.available), (100, 0))
        issue = self.draft(Movement.Kind.ISSUE, [self.line("1", None, expiry=expiry)])
        with self.assertRaises(ValidationError):
            self.confirm(issue)

    def test_expiry_today_is_available(self):
        today = timezone.localdate()
        self.confirm(self.draft(lines=[self.line(expiry=today)]))
        self.confirm(self.draft(Movement.Kind.ISSUE, [self.line("1", None, expiry=today)]))
        self.assertEqual(Balance.objects.get().quantity, 99)

    def test_wrong_expiry_and_missing_lot_data_are_rejected_atomically(self):
        self.draft()
        for row in [
            self.line(expiry=self.expiry + timedelta(days=1)),
            {**self.line(), "expires_on": None},
            {**self.line(), "lot_code": ""},
            self.line("0"),
            self.line("-1"),
            self.line(cost="-1"),
        ]:
            with self.subTest(row=row), self.assertRaises(ValidationError):
                self.draft(lines=[row])
        self.assertEqual(Movement.objects.count(), 1)
        self.assertEqual(Lot.objects.count(), 1)

    def test_inactive_product_and_backdated_draft_are_rejected(self):
        draft = self.draft()
        Product.objects.filter(pk=self.product.pk).update(active=False)
        with self.assertRaises(ValidationError):
            self.confirm(draft)
        Product.objects.filter(pk=self.product.pk).update(active=True)
        with patch(
            "apps.inventory.services.timezone.localdate",
            return_value=timezone.localdate() + timedelta(days=1),
        ):
            with self.assertRaises(ValidationError):
                self.confirm(draft)

    def test_opening_balance_only_before_first_confirmed_movement(self):
        self.confirm(self.draft(Movement.Kind.OPENING))
        with self.assertRaises(ValidationError):
            self.confirm(self.draft(Movement.Kind.OPENING))
        self.assertEqual(Balance.objects.get().quantity, 100)

    def test_failed_audit_rolls_back_confirmation(self):
        draft = self.draft()
        with patch(
            "apps.inventory.services.AuditEvent.objects.create", side_effect=RuntimeError("audit")
        ):
            with self.assertRaises(RuntimeError):
                self.confirm(draft)
        draft.refresh_from_db()
        self.assertEqual(draft.status, Movement.Status.DRAFT)
        self.assertFalse(Balance.objects.exists())

    def test_database_protects_confirmed_history_and_lot(self):
        movement = self.confirm(self.draft())
        mutations = [
            lambda: Movement.objects.filter(pk=movement.pk).update(reason="Cambio"),
            lambda: movement.lines.update(quantity=1),
            lambda: movement.lines.all().delete(),
            lambda: AuditEvent.objects.all().update(action="Cambio"),
            lambda: AuditEvent.objects.all().delete(),
            lambda: Lot.objects.all().update(expires_on=timezone.localdate()),
            lambda: Product.objects.filter(pk=self.product.pk).update(unit="caja"),
        ]
        for mutate in mutations:
            with (
                self.subTest(mutate=mutate),
                self.assertRaises(DatabaseError),
                transaction.atomic(),
            ):
                mutate()

    def test_read_only_profile_and_foreign_warehouse_cannot_write(self):
        auditor = get_user_model().objects.create_user(username="auditor")
        auditor.groups.add(Group.objects.get(name="Auditor"))
        WarehouseAccess.objects.create(user=auditor, warehouse=self.warehouse)
        with self.assertRaises(PermissionDenied):
            self.draft(user=auditor)
        other = Warehouse.objects.create(code="OTRA", name="Bodega ajena")
        with self.assertRaises(PermissionDenied):
            self.draft(warehouse_id=other.pk)

    def test_catalog_updates_are_audited_and_unit_is_protected(self):
        admin = get_user_model().objects.create_user(username="catalogo")
        admin.groups.add(Group.objects.get(name="Administrador"))
        product = save_product(user=admin, data={"code": "P2", "name": "Segundo", "unit": "unidad"})
        self.assertTrue(AuditEvent.objects.filter(action="product.created", actor=admin).exists())
        self.confirm(self.draft(lines=[self.line(product=product)]))
        with self.assertRaises(ValidationError):
            save_product(user=admin, data={"unit": "caja"}, product_id=product.pk)

    def test_all_screens_render_and_costs_are_hidden_from_operator(self):
        movement = self.confirm(self.draft())
        self.client.force_login(self.user)
        for name in ["stock", "products", "movements", "movement_create", "ledger"]:
            with self.subTest(screen=name):
                self.assertEqual(self.client.get(reverse(f"inventory:{name}")).status_code, 200)
        response = self.client.get(reverse("inventory:movement_detail", args=[movement.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Costo unitario CLP")
        self.assertNotContains(self.client.get(reverse("inventory:stock")), "Valor total")
        self.assertEqual(self.client.get(reverse("inventory:audit")).status_code, 403)
        auditor = get_user_model().objects.create_user(username="audit_screen")
        auditor.groups.add(Group.objects.get(name="Auditor"))
        WarehouseAccess.objects.create(user=auditor, warehouse=self.warehouse)
        self.client.force_login(auditor)
        self.assertContains(self.client.get(reverse("inventory:stock")), "Valor total")
        self.assertEqual(self.client.get(reverse("inventory:audit")).status_code, 200)

    def test_anonymous_and_cross_warehouse_access_is_denied(self):
        movement = self.confirm(self.draft())
        self.assertEqual(self.client.get(reverse("inventory:stock")).status_code, 302)
        outsider = get_user_model().objects.create_user(username="sin_bodega")
        outsider.groups.add(Group.objects.get(name="Operador"))
        self.client.force_login(outsider)
        self.assertEqual(
            self.client.get(reverse("inventory:movement_detail", args=[movement.pk])).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(reverse("inventory:movement_confirm", args=[movement.pk])).status_code,
            404,
        )
        self.assertNotContains(self.client.get(reverse("inventory:stock")), "Farmacia de prueba")

    def test_confirmation_requires_post_and_csrf(self):
        draft = self.draft()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        url = reverse("inventory:movement_confirm", args=[draft.pk])
        self.assertEqual(client.get(url).status_code, 405)
        self.assertEqual(client.post(url).status_code, 403)
        self.assertFalse(Balance.objects.exists())

    def test_browser_form_creates_then_confirms_and_rejects_missing_expiry(self):
        self.client.force_login(self.user)
        data = {
            "warehouse": self.warehouse.pk,
            "kind": "RECEIPT",
            "reference": "Formulario",
            "reason": "Ingreso",
            "request_key": str(uuid.uuid4()),
            "lines-TOTAL_FORMS": "1",
            "lines-INITIAL_FORMS": "0",
            "lines-0-product": self.product.pk,
            "lines-0-lot_code": "WEB",
            "lines-0-expires_on": "",
            "lines-0-quantity": "10",
            "lines-0-unit_cost": "1000",
        }
        url = reverse("inventory:movement_create")
        self.assertEqual(self.client.post(url, data).status_code, 200)
        self.assertFalse(Movement.objects.exists())
        data["lines-0-expires_on"] = self.expiry.isoformat()
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        movement = Movement.objects.get()
        self.assertFalse(Balance.objects.exists())
        response = self.client.post(
            reverse("inventory:movement_confirm", args=[movement.pk]), follow=True
        )
        self.assertContains(response, "Movimiento confirmado.")
        self.assertEqual(Balance.objects.get().quantity, 10)

    def test_bootstrap_preserves_existing_group_configuration(self):
        group = Group.objects.get(name="Operador")
        group.permissions.clear()
        call_command("bootstrap_roles", stdout=StringIO())
        self.assertFalse(group.permissions.exists())

    def test_operator_can_review_own_draft_cost_but_not_another_operators(self):
        draft = self.draft()
        self.client.force_login(self.user)
        url = reverse("inventory:movement_detail", args=[draft.pk])
        self.assertContains(self.client.get(url), "Costo unitario CLP")
        other = get_user_model().objects.create_user(username="otro_operador")
        other.groups.add(Group.objects.get(name="Operador"))
        WarehouseAccess.objects.create(user=other, warehouse=self.warehouse)
        self.client.force_login(other)
        self.assertNotContains(self.client.get(url), "Costo unitario CLP")

    def test_auditor_cannot_post_movements_or_confirm(self):
        draft = self.draft()
        auditor = get_user_model().objects.create_user(username="solo_lectura")
        auditor.groups.add(Group.objects.get(name="Auditor"))
        WarehouseAccess.objects.create(user=auditor, warehouse=self.warehouse)
        self.client.force_login(auditor)
        self.assertEqual(
            self.client.post(reverse("inventory:movement_create"), {}).status_code, 403
        )
        self.assertEqual(
            self.client.post(reverse("inventory:movement_confirm", args=[draft.pk])).status_code,
            403,
        )
        self.assertFalse(Balance.objects.exists())

    def test_inactive_warehouse_has_no_available_stock_and_cannot_confirm(self):
        self.confirm(self.draft())
        draft = self.draft()
        Warehouse.objects.filter(pk=self.warehouse.pk).update(active=False)
        self.assertEqual(LotBalance.objects.get().available, 0)
        with self.assertRaises(ValidationError):
            self.confirm(draft)

    def test_login_and_logout(self):
        self.user.set_password("Sicfe-test-only-2026!")
        self.user.save()
        response = self.client.post(
            reverse("login"),
            {
                "username": self.user.username,
                "password": "Sicfe-test-only-2026!",
            },
        )
        self.assertRedirects(response, reverse("home"))
        self.assertEqual(self.client.get(reverse("inventory:stock")).status_code, 200)
        self.client.post(reverse("logout"))
        self.assertEqual(self.client.get(reverse("inventory:stock")).status_code, 302)


class ConcurrencyTests(Scenario, TransactionTestCase):
    def setUp(self):
        self.setup_scenario()

    def parallel_confirm(self, movements):
        barrier = Barrier(len(movements))
        user_id = self.user.pk

        def worker(movement_id):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                user = get_user_model().objects.get(pk=user_id)
                barrier.wait(timeout=10)
                confirm_movement(user=user, movement_id=movement_id)
                return "confirmed"
            except ValidationError:
                return "rejected"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=len(movements)) as executor:
            return list(executor.map(worker, [movement.pk for movement in movements]))

    def test_concurrent_issues_cannot_consume_same_units(self):
        self.confirm(self.draft(lines=[self.line("10")]))
        first = self.draft(Movement.Kind.ISSUE, [self.line("7", None)])
        second = self.draft(Movement.Kind.ISSUE, [self.line("7", None)])
        self.assertCountEqual(self.parallel_confirm([first, second]), ["confirmed", "rejected"])
        self.assertEqual(Balance.objects.get().quantity, 3)
        self.assertEqual(LotBalance.objects.get().quantity, 3)

    def test_concurrent_confirmation_of_same_movement_is_idempotent(self):
        draft = self.draft()
        self.assertEqual(self.parallel_confirm([draft, draft]), ["confirmed", "confirmed"])
        self.assertEqual(Balance.objects.get().quantity, 100)
        self.assertEqual(AuditEvent.objects.filter(action="movement.confirmed").count(), 1)

    def test_concurrent_draft_submission_creates_only_one_movement(self):
        barrier = Barrier(2)
        key = uuid.uuid4()
        user_id, warehouse_id = self.user.pk, self.warehouse.pk
        lines = [self.line()]

        def worker():
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                user = get_user_model().objects.get(pk=user_id)
                barrier.wait(timeout=10)
                return create_draft(
                    user=user,
                    warehouse_id=warehouse_id,
                    kind=Movement.Kind.RECEIPT,
                    reference="Concurrente",
                    reason="Reintento",
                    lines=lines,
                    request_key=key,
                ).pk
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(worker), executor.submit(worker)]
            ids = [future.result(timeout=15) for future in futures]
        self.assertEqual(ids[0], ids[1])
        self.assertEqual(Movement.objects.count(), 1)
