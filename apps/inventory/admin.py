from django.contrib import admin

from .models import Warehouse, WarehouseAccess


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "active"]
    search_fields = ["code", "name"]

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(WarehouseAccess)
class WarehouseAccessAdmin(admin.ModelAdmin):
    list_display = ["user", "warehouse"]
    list_filter = ["warehouse"]
    autocomplete_fields = ["user", "warehouse"]
