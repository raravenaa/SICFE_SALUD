"""Única entrada de escritura para catálogo y movimientos de la aplicación."""

import hashlib
import json
from decimal import ROUND_HALF_UP, Decimal, localcontext

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .access import require_permission, require_warehouse
from .models import AuditEvent, Balance, Lot, LotBalance, Movement, MovementLine, Product, Warehouse

MONEY = Decimal("0.000001")


def save_validated(instance):
    instance.full_clean()
    instance.save()
    return instance


@transaction.atomic
def save_product(*, user, data, product_id=None):
    require_permission(user, "change_product" if product_id else "add_product")
    product = Product.objects.select_for_update().get(pk=product_id) if product_id else Product()
    before = {key: getattr(product, key) for key in data} if product_id else {}
    if product_id and MovementLine.objects.filter(lot__product=product).exists():
        if any(
            data.get(key, getattr(product, key)) != getattr(product, key)
            for key in ("code", "unit")
        ):
            raise ValidationError(
                "No puedes cambiar código ni unidad de un producto con movimientos."
            )
    for key in ("code", "name", "unit", "category", "avis_code", "active"):
        if key in data:
            setattr(product, key, data[key])
    save_validated(product)
    AuditEvent.objects.create(
        actor=user,
        action="product.updated" if product_id else "product.created",
        detail={
            "product_id": product.pk,
            "before": before,
            "after": {key: getattr(product, key) for key in data},
        },
    )
    return product


@transaction.atomic
def create_draft(*, user, warehouse_id, kind, reference, reason, lines, request_key):
    require_permission(user, "record_movement")
    # Serializa reintentos del mismo usuario incluso si cambia la bodega enviada.
    # NO KEY UPDATE permite las referencias FK desde confirmaciones simultáneas.
    get_user_model().objects.select_for_update(no_key=True).get(pk=user.pk)
    warehouse = Warehouse.objects.select_for_update().get(pk=warehouse_id)
    require_warehouse(user, warehouse)
    if not warehouse.active:
        raise ValidationError("La bodega está inactiva.")
    if not 1 <= len(lines) <= 50:
        raise ValidationError("Registra entre 1 y 50 líneas.")
    lines = [dict(row) for row in lines]
    for row in lines:
        row["expires_on"] = Lot._meta.get_field("expires_on").clean(row.get("expires_on"), None)
        row["quantity"] = MovementLine._meta.get_field("quantity").clean(row.get("quantity"), None)
    payload = {
        "warehouse": warehouse.pk,
        "kind": kind,
        "reference": reference.strip(),
        "reason": reason.strip(),
        "lines": [
            {
                "product_id": row["product_id"],
                "lot_code": row["lot_code"].strip(),
                "expires_on": row["expires_on"].isoformat(),
                "quantity": str(Decimal(row["quantity"]).normalize()),
                "unit_cost": str(Decimal(row.get("unit_cost") or 0).normalize()),
            }
            for row in lines
        ],
    }
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    existing = Movement.objects.filter(request_key=request_key).first()
    if existing:
        if existing.created_by_id != user.pk or existing.payload_hash != fingerprint:
            raise ValidationError(
                "La solicitud ya fue utilizada con otros datos. Abre un formulario nuevo."
            )
        return existing
    products = {
        p.pk: p
        for p in Product.objects.select_for_update()
        .filter(pk__in=[row["product_id"] for row in lines])
        .order_by("pk")
    }
    movement = save_validated(
        Movement(
            warehouse=warehouse,
            kind=kind,
            reference=reference.strip(),
            reason=reason.strip(),
            created_by=user,
            request_key=request_key,
            payload_hash=fingerprint,
        )
    )
    for row in lines:
        product = products.get(row["product_id"])
        if product is None or not product.active:
            raise ValidationError("Selecciona un producto activo.")
        code = row["lot_code"].strip()
        candidate = Lot(product=product, code=code, expires_on=row["expires_on"])
        candidate.full_clean(validate_unique=False, validate_constraints=False)
        lot = Lot.objects.filter(product=product, code=code).first()
        if lot and lot.expires_on != row["expires_on"]:
            raise ValidationError(f"El lote {code} ya tiene otro vencimiento registrado.")
        if lot is None:
            if kind == Movement.Kind.ISSUE:
                raise ValidationError(f"El lote {code} no existe para este producto.")
            lot = save_validated(candidate)
        cost = Decimal(row.get("unit_cost") or 0)
        if kind == Movement.Kind.ISSUE and cost:
            raise ValidationError("El costo de salida lo calcula el sistema; deja ese campo vacío.")
        if kind != Movement.Kind.ISSUE and row.get("unit_cost") is None:
            raise ValidationError("Indica el costo unitario del ingreso, incluso si es cero.")
        save_validated(
            MovementLine(
                movement=movement,
                lot=lot,
                quantity=row["quantity"],
                unit_cost=cost,
            )
        )
    AuditEvent.objects.create(
        actor=user,
        action="movement.created",
        warehouse=warehouse,
        movement=movement,
        detail={"request_key": str(request_key), "payload_hash": fingerprint},
    )
    return movement


@transaction.atomic
def confirm_movement(*, user, movement_id):
    require_permission(user, "record_movement")
    initial = Movement.objects.get(pk=movement_id)
    warehouse = Warehouse.objects.select_for_update().get(pk=initial.warehouse_id)
    require_warehouse(user, warehouse)
    movement = Movement.objects.select_for_update().get(pk=movement_id)
    if movement.status == Movement.Status.CONFIRMED:
        return movement
    if movement.status != Movement.Status.DRAFT:
        raise ValidationError("Este borrador fue cancelado.")
    if not warehouse.active:
        raise ValidationError("La bodega está inactiva.")
    if movement.effective_date != timezone.localdate():
        raise ValidationError(
            "Solo se confirman movimientos del día. Cancela y registra un nuevo borrador."
        )
    lines = list(movement.lines.select_related("lot__product").order_by("pk"))
    if not lines:
        raise ValidationError("El movimiento no contiene líneas.")
    products = {
        p.pk: p
        for p in Product.objects.select_for_update()
        .filter(pk__in=[line.lot.product_id for line in lines])
        .order_by("pk")
    }
    if any(not p.active for p in products.values()):
        raise ValidationError("El movimiento contiene un producto inactivo.")
    # Bloquear la bodega serializa movimientos y la creación inicial de saldos.
    balances = {
        pk: Balance.objects.get_or_create(warehouse=warehouse, product_id=pk)[0] for pk in products
    }
    if movement.kind == Movement.Kind.OPENING:
        if MovementLine.objects.filter(
            movement__warehouse=warehouse,
            movement__status=Movement.Status.CONFIRMED,
            lot__product_id__in=products,
        ).exists():
            raise ValidationError(
                "El saldo inicial solo se registra antes del primer movimiento del producto."
            )
    lots = {
        line.lot_id: LotBalance.objects.get_or_create(warehouse=warehouse, lot_id=line.lot_id)[0]
        for line in lines
    }
    audit_lines = []
    with localcontext() as context:
        context.prec = 50
        # Fijar promedio por producto al comienzo de la salida; no recalcular por cada lote.
        averages = {pk: balance.average_cost for pk, balance in balances.items()}
        for line in lines:
            balance = balances[line.lot.product_id]
            lot_balance = lots[line.lot_id]
            quantity = line.quantity
            if movement.kind == Movement.Kind.ISSUE:
                if line.lot.expires_on < timezone.localdate():
                    raise ValidationError(f"El lote {line.lot.code} está vencido.")
                if quantity > lot_balance.quantity or quantity > balance.quantity:
                    raise ValidationError(f"Stock insuficiente en el lote {line.lot.code}.")
                line.unit_cost = averages[line.lot.product_id].quantize(
                    MONEY, rounding=ROUND_HALF_UP
                )
                value = (quantity * averages[line.lot.product_id]).quantize(
                    MONEY, rounding=ROUND_HALF_UP
                )
                value = balance.value if quantity == balance.quantity else min(value, balance.value)
                balance.quantity -= quantity
                balance.value -= value
                lot_balance.quantity -= quantity
            else:
                value = (quantity * line.unit_cost).quantize(MONEY, rounding=ROUND_HALF_UP)
                balance.quantity += quantity
                balance.value += value
                lot_balance.quantity += quantity
            line.applied_value = value
            line.quantity_after = balance.quantity
            line.value_after = balance.value
            save_validated(line)
            save_validated(balance)
            save_validated(lot_balance)
            audit_lines.append(
                {
                    "line_id": line.pk,
                    "lot_id": line.lot_id,
                    "quantity": str(quantity),
                    "value": str(value),
                }
            )
    movement.status = Movement.Status.CONFIRMED
    movement.confirmed_by = user
    movement.confirmed_at = timezone.now()
    save_validated(movement)
    AuditEvent.objects.create(
        actor=user,
        action="movement.confirmed",
        warehouse=warehouse,
        movement=movement,
        detail={"lines": audit_lines},
    )
    return movement


@transaction.atomic
def cancel_draft(*, user, movement_id):
    require_permission(user, "record_movement")
    initial = Movement.objects.get(pk=movement_id)
    warehouse = Warehouse.objects.select_for_update().get(pk=initial.warehouse_id)
    require_warehouse(user, warehouse)
    movement = Movement.objects.select_for_update().get(pk=movement_id)
    if movement.status == Movement.Status.CANCELLED:
        return movement
    if movement.status != Movement.Status.DRAFT:
        raise ValidationError("Un movimiento confirmado no se puede cancelar ni modificar.")
    movement.status = Movement.Status.CANCELLED
    save_validated(movement)
    AuditEvent.objects.create(
        actor=user, action="movement.cancelled", warehouse=warehouse, movement=movement, detail={}
    )
    return movement
