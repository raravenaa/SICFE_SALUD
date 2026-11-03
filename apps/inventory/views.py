from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .access import require_permission, warehouses_for
from .forms import MovementForm, MovementLineFormSet, ProductForm
from .models import AuditEvent, Balance, LotBalance, Movement, MovementLine, Product
from .services import cancel_draft, confirm_movement, create_draft, save_product


def page(request, rows):
    return Paginator(rows, 50).get_page(request.GET.get("page"))


def filtered(request, rows, warehouse_field="warehouse_id"):
    warehouse_id = request.GET.get("warehouse", "")
    if warehouse_id.isdecimal():
        rows = rows.filter(**{warehouse_field: int(warehouse_id)})
    return rows


@login_required
@permission_required("inventory.view_stock", raise_exception=True)
@require_GET
def stock(request):
    warehouses = warehouses_for(request.user)
    rows = (
        LotBalance.objects.filter(warehouse__in=warehouses)
        .select_related("warehouse", "lot__product")
        .order_by("lot__expires_on", "lot__product__name", "pk")
    )
    rows = filtered(request, rows)
    query = request.GET.get("q", "").strip()
    if query:
        rows = rows.filter(
            Q(lot__product__name__icontains=query)
            | Q(lot__product__code__icontains=query)
            | Q(lot__code__icontains=query)
        )
    status = request.GET.get("status", "")
    today = timezone.localdate()
    if status == "expired":
        rows = rows.filter(lot__expires_on__lt=today, quantity__gt=0)
    elif status == "soon":
        rows = rows.filter(
            lot__expires_on__range=(today, today + timedelta(days=90)), quantity__gt=0
        )
    costs = None
    if request.user.has_perm("inventory.view_costs"):
        costs = filtered(request, Balance.objects.filter(warehouse__in=warehouses))
        if query:
            costs = costs.filter(
                Q(product__name__icontains=query) | Q(product__code__icontains=query)
            )
        costs = page(
            request, costs.select_related("product", "warehouse").order_by("product__name", "pk")
        )
    return render(
        request,
        "inventory/stock.html",
        {
            "page": page(request, rows),
            "warehouses": warehouses,
            "costs": costs,
            "query": query,
            "selected_warehouse": request.GET.get("warehouse", ""),
            "status": status,
        },
    )


@login_required
@permission_required("inventory.view_product", raise_exception=True)
@require_GET
def products(request):
    rows = Product.objects.all()
    query = request.GET.get("q", "").strip()
    if query:
        rows = rows.filter(Q(name__icontains=query) | Q(code__icontains=query))
    return render(request, "inventory/products.html", {"page": page(request, rows), "query": query})


@login_required
def product_edit(request, pk=None):
    require_permission(request.user, "change_product" if pk else "add_product")
    instance = get_object_or_404(Product, pk=pk) if pk else None
    form = ProductForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        try:
            save_product(user=request.user, data=form.cleaned_data, product_id=pk)
        except ValidationError as exc:
            form.add_error(None, exc.messages)
        else:
            messages.success(request, "Producto guardado.")
            return redirect("inventory:products")
    return render(request, "inventory/product_form.html", {"form": form, "editing": pk is not None})


@login_required
@permission_required("inventory.view_movement", raise_exception=True)
@require_GET
def movements(request):
    warehouses = warehouses_for(request.user)
    rows = Movement.objects.filter(warehouse__in=warehouses).select_related(
        "warehouse", "created_by"
    )
    rows = filtered(request, rows)
    return render(
        request, "inventory/movements.html", {"page": page(request, rows), "warehouses": warehouses}
    )


@login_required
@permission_required("inventory.record_movement", raise_exception=True)
def movement_create(request):
    form = MovementForm(request.POST or None, user=request.user)
    formset = MovementLineFormSet(request.POST or None, prefix="lines")
    if request.method == "POST":
        valid_header, valid_lines = form.is_valid(), formset.is_valid()
        if valid_header and valid_lines:
            lines = []
            for row in formset.cleaned_data:
                if row and not row.get("DELETE"):
                    lines.append(
                        {
                            "product_id": row["product"].pk,
                            "lot_code": row["lot_code"],
                            "expires_on": row["expires_on"],
                            "quantity": row["quantity"],
                            "unit_cost": row["unit_cost"],
                        }
                    )
            try:
                movement = create_draft(
                    user=request.user,
                    warehouse_id=form.cleaned_data["warehouse"].pk,
                    kind=form.cleaned_data["kind"],
                    reference=form.cleaned_data["reference"],
                    reason=form.cleaned_data["reason"],
                    request_key=form.cleaned_data["request_key"],
                    lines=lines,
                )
            except ValidationError as exc:
                form.add_error(None, exc.messages)
            else:
                messages.success(
                    request, "Borrador guardado. Revisa sus líneas antes de confirmar."
                )
                return redirect("inventory:movement_detail", pk=movement.pk)
    return render(request, "inventory/movement_form.html", {"form": form, "formset": formset})


def accessible_movement(request, pk):
    return get_object_or_404(
        Movement.objects.filter(warehouse__in=warehouses_for(request.user)).select_related(
            "warehouse", "created_by", "confirmed_by"
        ),
        pk=pk,
    )


@login_required
@permission_required("inventory.view_movement", raise_exception=True)
@require_GET
def movement_detail(request, pk):
    movement = accessible_movement(request, pk)
    return render(
        request,
        "inventory/movement_detail.html",
        {
            "movement": movement,
            "lines": movement.lines.select_related("lot__product"),
            "show_costs": request.user.has_perm("inventory.view_costs")
            or (
                movement.created_by_id == request.user.pk
                and movement.status == Movement.Status.DRAFT
                and movement.kind != Movement.Kind.ISSUE
            ),
        },
    )


@login_required
@permission_required("inventory.record_movement", raise_exception=True)
@require_POST
def movement_action(request, pk, action):
    movement = accessible_movement(request, pk)
    operation = confirm_movement if action == "confirm" else cancel_draft
    try:
        operation(user=request.user, movement_id=movement.pk)
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(
            request, "Movimiento confirmado." if action == "confirm" else "Borrador cancelado."
        )
    return redirect("inventory:movement_detail", pk=pk)


@login_required
@permission_required("inventory.view_movement", raise_exception=True)
@require_GET
def ledger(request):
    rows = MovementLine.objects.filter(
        movement__warehouse__in=warehouses_for(request.user),
        movement__status=Movement.Status.CONFIRMED,
    )
    rows = filtered(request, rows, "movement__warehouse_id")
    product_id = request.GET.get("product", "")
    if product_id.isdecimal():
        rows = rows.filter(lot__product_id=int(product_id))
    query = request.GET.get("lot", "").strip()
    if query:
        rows = rows.filter(lot__code__icontains=query)
    rows = rows.select_related("movement__warehouse", "movement__confirmed_by", "lot__product")
    return render(
        request,
        "inventory/ledger.html",
        {
            "page": page(request, rows.order_by("-movement__confirmed_at", "-pk")),
            "warehouses": warehouses_for(request.user),
            "products": Product.objects.all(),
            "selected_product": product_id,
            "query": query,
        },
    )


@login_required
@permission_required("inventory.view_audit", raise_exception=True)
@require_GET
def audit(request):
    rows = AuditEvent.objects.filter(
        Q(warehouse__in=warehouses_for(request.user)) | Q(warehouse__isnull=True)
    ).select_related("actor", "warehouse")
    # No enviar el JSON con valores a perfiles sin permiso de costos.
    return render(request, "inventory/audit.html", {"page": page(request, rows)})
