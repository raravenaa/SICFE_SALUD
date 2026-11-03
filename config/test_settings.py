"""Cuenta local separada para crear y destruir la base de pruebas de Django."""

from config.settings import *  # noqa: F403
from config.settings import DATABASES, required

MIRROR = []
DATABASES["default"]["USER"] = "sicfe_admin"
DATABASES["default"]["PASSWORD"] = required("POSTGRES_ADMIN_PASSWORD")
DATABASES["default"]["TEST"] = {"NAME": "test_sicfe_dev"}
