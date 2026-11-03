from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = "Crea cinco perfiles iniciales conservando los grupos existentes. No asigna usuarios."

    @transaction.atomic
    def handle(self, *args, **options):
        shared = ["view_product", "view_stock", "view_movement"]
        roles = {
            "Administrador": [
                *shared,
                "add_product",
                "change_product",
                "view_warehouse",
                "add_warehouse",
                "change_warehouse",
                "view_warehouseaccess",
                "add_warehouseaccess",
                "change_warehouseaccess",
                "delete_warehouseaccess",
                "view_audit",
            ],
            "Operador": [*shared, "record_movement"],
            "Contabilidad": [*shared, "view_costs"],
            "Auditor": [*shared, "view_costs", "view_audit"],
            "Dirección": ["view_stock", "view_costs"],
        }
        for name, codes in roles.items():
            group, created = Group.objects.get_or_create(name=name)
            if created:
                permissions = Permission.objects.filter(
                    content_type__app_label="inventory", codename__in=codes
                )
                if permissions.count() != len(codes):
                    raise RuntimeError("Faltan permisos. Ejecuta migrate antes de bootstrap_roles.")
                group.permissions.set(permissions)
            self.stdout.write(f"{name}: {'creado' if created else 'existente, conservado'}")
