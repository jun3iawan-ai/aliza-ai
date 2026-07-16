import importlib
import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


DOCS_ENV_VAR = "ALIZA_DASHBOARD_DOCS_ENABLED"
TEST_JWT_SECRET = "dashboard-docs-test-secret-value-32-chars"
MISSING = object()


class DashboardDocsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fake_database = types.ModuleType("core.database")
        fake_database.cursor = MagicMock()
        fake_database.conn = MagicMock()
        cls.modules_patcher = patch.dict(
            sys.modules,
            {"core.database": fake_database},
        )
        cls.modules_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._remove_dashboard_modules()
        cls.modules_patcher.stop()

    def setUp(self):
        self._remove_dashboard_modules()

    def tearDown(self):
        self._remove_dashboard_modules()

    @staticmethod
    def _remove_dashboard_modules():
        for module_name in ("api.auth", "api.dashboard_api", "api.server"):
            sys.modules.pop(module_name, None)

    def _import_server(self, docs_value=MISSING):
        environment = {"JWT_SECRET": TEST_JWT_SECRET}
        if docs_value is not MISSING:
            environment[DOCS_ENV_VAR] = docs_value

        self._remove_dashboard_modules()
        with patch.dict(os.environ, environment, clear=True):
            return importlib.import_module("api.server")

    def test_docs_are_disabled_by_default(self):
        app = self._import_server().app

        self.assertIsNone(app.docs_url)
        self.assertIsNone(app.redoc_url)
        self.assertIsNone(app.openapi_url)

    def test_empty_and_false_disable_docs(self):
        for value in ("", "false"):
            with self.subTest(value=value):
                app = self._import_server(value).app
                self.assertIsNone(app.docs_url)
                self.assertIsNone(app.redoc_url)
                self.assertIsNone(app.openapi_url)

    def test_true_enables_standard_docs_routes(self):
        app = self._import_server("true").app

        self.assertEqual(app.docs_url, "/docs")
        self.assertEqual(app.redoc_url, "/redoc")
        self.assertEqual(app.openapi_url, "/openapi.json")

    def test_true_is_case_insensitive_and_ignores_whitespace(self):
        app = self._import_server(" TRUE ").app

        self.assertEqual(app.docs_url, "/docs")
        self.assertEqual(app.redoc_url, "/redoc")
        self.assertEqual(app.openapi_url, "/openapi.json")

    def test_invalid_values_are_rejected(self):
        for value in ("yes", "1", "enabled"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "ALIZA_DASHBOARD_DOCS_ENABLED",
                ):
                    self._import_server(value)

    def test_default_mode_does_not_register_docs_routes(self):
        app = self._import_server().app
        registered_paths = {route.path for route in app.routes}
        docs_paths = {
            "/docs",
            "/docs/oauth2-redirect",
            "/redoc",
            "/openapi.json",
        }

        self.assertTrue(docs_paths.isdisjoint(registered_paths))
        with patch.dict(os.environ, {"JWT_SECRET": TEST_JWT_SECRET}, clear=True):
            with TestClient(app) as client:
                for path in docs_paths:
                    with self.subTest(path=path):
                        self.assertEqual(client.get(path).status_code, 404)

    def test_default_mode_keeps_public_routes_available(self):
        app = self._import_server().app

        with patch.dict(os.environ, {"JWT_SECRET": TEST_JWT_SECRET}, clear=True):
            with TestClient(app) as client:
                health_response = client.get("/health")
                root_response = client.get("/")

        self.assertEqual(health_response.status_code, 200)
        self.assertEqual(health_response.json(), {"status": "ok"})
        self.assertEqual(root_response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
