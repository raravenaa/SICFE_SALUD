from django.core.exceptions import PermissionDenied

from .models import Warehouse


def require_permission(user, codename):
    if (
        not user.is_authenticated
        or not user.is_active
        or not user.has_perm(f"inventory.{codename}")
    ):
        raise PermissionDenied("Tu perfil no permite esta operación.")


def warehouses_for(user):
    if not user.is_authenticated or not user.is_active:
        return Warehouse.objects.none()
    if user.is_superuser:
        return Warehouse.objects.all()
    return Warehouse.objects.filter(warehouseaccess__user=user)


def require_warehouse(user, warehouse):
    if not warehouses_for(user).filter(pk=warehouse.pk).exists():
        raise PermissionDenied("No tienes acceso a esta bodega.")
