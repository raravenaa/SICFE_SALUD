from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from apps.core.views import health, home

admin.site.site_header = "Administración SICFE"
admin.site.site_title = "SICFE"
admin.site.index_title = "Administración del entorno"

urlpatterns = [
    path("", home, name="home"),
    path("health/", health, name="health"),
    path("admin/", admin.site.urls),
    path(
        "ingresar/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path("salir/", auth_views.LogoutView.as_view(), name="logout"),
    path("existencias/", include("apps.inventory.urls")),
]
