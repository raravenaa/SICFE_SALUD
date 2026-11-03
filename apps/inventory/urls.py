from django.urls import path

from . import views

app_name = "inventory"
urlpatterns = [
    path("", views.stock, name="stock"),
    path("productos/", views.products, name="products"),
    path("productos/nuevo/", views.product_edit, name="product_create"),
    path("productos/<int:pk>/", views.product_edit, name="product_edit"),
    path("movimientos/", views.movements, name="movements"),
    path("movimientos/nuevo/", views.movement_create, name="movement_create"),
    path("movimientos/<int:pk>/", views.movement_detail, name="movement_detail"),
    path(
        "movimientos/<int:pk>/confirmar/",
        views.movement_action,
        {"action": "confirm"},
        name="movement_confirm",
    ),
    path(
        "movimientos/<int:pk>/cancelar/",
        views.movement_action,
        {"action": "cancel"},
        name="movement_cancel",
    ),
    path("kardex/", views.ledger, name="ledger"),
    path("auditoria/", views.audit, name="audit"),
]
