from unittest.mock import patch

from django.db import OperationalError
from django.test import TestCase
from django.urls import reverse


class EnvironmentTests(TestCase):
    def test_home_is_available(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, "SICFE")

    def test_health_checks_real_database(self):
        self.assertEqual(self.client.get(reverse("health")).json(), {"status": "ok"})

    def test_health_hides_database_error(self):
        with patch("apps.core.views.connection.cursor", side_effect=OperationalError("secret")):
            response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "unavailable"})
        self.assertNotContains(response, "secret", status_code=503)

    def test_admin_requires_authentication(self):
        response = self.client.get(reverse("admin:index"))
        self.assertRedirects(response, "/admin/login/?next=/admin/")
