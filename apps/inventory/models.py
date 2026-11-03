import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Product(models.Model):
    code = models.CharField("Código", max_length=40, unique=True)
    name = models.CharField("Nombre", max_length=200)
    unit = models.CharField("Unidad base", max_length=30, default="unidad")
    category = models.CharField("Categoría", max_length=80, blank=True)
    avis_code = models.CharField("Código AVIS", max_length=80, blank=True)
    active = models.BooleanField("Activo", default=True)

    class Meta:
        ordering = ["name", "pk"]
        verbose_name = "producto"

    def __str__(self):
        return f"{self.code} · {self.name}"


class Warehouse(models.Model):
    code = models.CharField("Código", max_length=40, unique=True)
    name = models.CharField("Nombre", max_length=150)
    active = models.BooleanField("Activa", default=True)

    class Meta:
        ordering = ["name", "pk"]
        verbose_name = "bodega"

    def __str__(self):
        return self.name


class WarehouseAccess(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, verbose_name="Bodega")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "warehouse"], name="access_unique")]
        verbose_name = "acceso a bodega"
        verbose_name_plural = "accesos a bodegas"

    def __str__(self):
        return f"{self.user} · {self.warehouse}"


class Lot(models.Model):
    product = models.ForeignKey(Product, on_delete=models.PROTECT, verbose_name="Producto")
    code = models.CharField("Lote", max_length=80)
    expires_on = models.DateField("Vencimiento")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["product", "code"], name="lot_unique")]
        ordering = ["expires_on", "pk"]
        verbose_name = "lote"

    def __str__(self):
        return f"{self.product.code} / {self.code}"


class Balance(models.Model):
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=18, decimal_places=3, default=0)
    value = models.DecimalField(max_digits=30, decimal_places=6, default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["warehouse", "product"], name="balance_unique"),
            models.CheckConstraint(
                condition=Q(quantity__gte=0), name="balance_quantity_nonnegative"
            ),
            models.CheckConstraint(condition=Q(value__gte=0), name="balance_value_nonnegative"),
            models.CheckConstraint(
                condition=Q(quantity__gt=0) | Q(value=0), name="empty_balance_zero"
            ),
        ]

    @property
    def average_cost(self):
        return self.value / self.quantity if self.quantity else Decimal("0")


class LotBalance(models.Model):
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT)
    lot = models.ForeignKey(Lot, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=18, decimal_places=3, default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["warehouse", "lot"], name="lot_balance_unique"),
            models.CheckConstraint(condition=Q(quantity__gte=0), name="lot_quantity_nonnegative"),
        ]

    @property
    def expired(self):
        return self.lot.expires_on < timezone.localdate()

    @property
    def available(self):
        return (
            self.quantity
            if not self.expired and self.lot.product.active and self.warehouse.active
            else Decimal("0")
        )


class Movement(models.Model):
    class Kind(models.TextChoices):
        OPENING = "OPENING", "Saldo inicial"
        RECEIPT = "RECEIPT", "Ingreso"
        ISSUE = "ISSUE", "Salida"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Borrador"
        CONFIRMED = "CONFIRMED", "Confirmado"
        CANCELLED = "CANCELLED", "Borrador cancelado"

    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, verbose_name="Bodega")
    kind = models.CharField("Tipo", max_length=15, choices=Kind.choices)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.DRAFT)
    effective_date = models.DateField("Fecha efectiva", default=timezone.localdate)
    reference = models.CharField("Referencia documental", max_length=150)
    reason = models.CharField("Motivo", max_length=300)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="confirmations",
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    request_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    payload_hash = models.CharField(max_length=64, editable=False)

    class Meta:
        ordering = ["-pk"]
        permissions = [
            ("record_movement", "Registrar y confirmar movimientos"),
            ("view_stock", "Consultar existencias"),
            ("view_costs", "Consultar costos y valorización"),
            ("view_audit", "Consultar auditoría de existencias"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(kind__in=["OPENING", "RECEIPT", "ISSUE"]), name="valid_kind"
            ),
            models.CheckConstraint(
                condition=(
                    Q(status="CONFIRMED", confirmed_at__isnull=False, confirmed_by__isnull=False)
                    | Q(
                        status__in=["DRAFT", "CANCELLED"],
                        confirmed_at__isnull=True,
                        confirmed_by__isnull=True,
                    )
                ),
                name="movement_confirmation_consistent",
            ),
        ]

    def __str__(self):
        return f"#{self.pk} · {self.get_kind_display()}"


class MovementLine(models.Model):
    movement = models.ForeignKey(Movement, on_delete=models.PROTECT, related_name="lines")
    lot = models.ForeignKey(Lot, on_delete=models.PROTECT)
    quantity = models.DecimalField("Cantidad", max_digits=15, decimal_places=3)
    unit_cost = models.DecimalField("Costo unitario", max_digits=18, decimal_places=6, default=0)
    applied_value = models.DecimalField(max_digits=30, decimal_places=6, default=0)
    quantity_after = models.DecimalField(max_digits=18, decimal_places=3, default=0)
    value_after = models.DecimalField(max_digits=30, decimal_places=6, default=0)

    class Meta:
        ordering = ["pk"]
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="line_positive_quantity"),
            models.CheckConstraint(condition=Q(unit_cost__gte=0), name="line_nonnegative_cost"),
            models.CheckConstraint(
                condition=Q(applied_value__gte=0), name="line_nonnegative_value"
            ),
        ]


class AuditEvent(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    occurred_at = models.DateTimeField(default=timezone.now, editable=False)
    action = models.CharField(max_length=60)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, null=True)
    movement = models.ForeignKey(Movement, on_delete=models.PROTECT, null=True)
    detail = models.JSONField(default=dict)

    class Meta:
        ordering = ["-pk"]

    @property
    def action_label(self):
        return {
            "product.created": "Producto creado",
            "product.updated": "Producto actualizado",
            "movement.created": "Borrador registrado",
            "movement.confirmed": "Movimiento confirmado",
            "movement.cancelled": "Borrador cancelado",
        }.get(self.action, self.action)
