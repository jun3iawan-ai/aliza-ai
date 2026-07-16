import importlib
import os
import sys
import types
import unittest
from unittest.mock import MagicMock, Mock, patch

from fastapi.testclient import TestClient
from api.passwords import hash_password

from api.security import JWT_SECRET_ENV_VAR, create_access_token


TEST_SECRET = "endpoint-auth-test-secret-value-32-chars"


class DashboardEndpointAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cursor = MagicMock()
        cls.conn = MagicMock()
        cls.get_market_data = Mock(return_value={"price": 100})
        cls.btc_signal = Mock(return_value={"signal": "hold"})
        cls.scan_opportunities = Mock(return_value=[])
        cls.get_active_trades = Mock(return_value=[])
        cls.calculate_market_score = Mock(return_value={"score": 50})
        cls.calculate_market_predictions = Mock(return_value={"bullish": 50})
        cls.ask_aliza = Mock(return_value="test answer")

        fake_database = types.ModuleType("core.database")
        fake_database.cursor = cls.cursor
        fake_database.conn = cls.conn

        fake_market_cache = types.ModuleType("engine.utils.market_cache")
        fake_market_cache.get_market_data = cls.get_market_data

        fake_scanner = types.ModuleType("engine.trading.opportunity_scanner")
        fake_scanner.scan_opportunities = cls.scan_opportunities

        fake_trade_manager = types.ModuleType("engine.trading.trade_manager")
        fake_trade_manager.get_active_trades = cls.get_active_trades

        fake_market_analyzer = types.ModuleType("engine.market.market_analyzer")
        fake_market_analyzer.btc_signal = cls.btc_signal

        fake_quant = types.ModuleType("engine.intelligence.quant_market_model")
        fake_quant.calculate_market_score = cls.calculate_market_score

        fake_predict = types.ModuleType("engine.intelligence.predictive_market_ai")
        fake_predict.calculate_market_predictions = cls.calculate_market_predictions

        fake_aliza = types.ModuleType("engine.brain.aliza_engine")
        fake_aliza.ask_aliza = cls.ask_aliza

        cls.modules_patcher = patch.dict(
            sys.modules,
            {
                "core.database": fake_database,
                "engine.utils.market_cache": fake_market_cache,
                "engine.trading.opportunity_scanner": fake_scanner,
                "engine.trading.trade_manager": fake_trade_manager,
                "engine.market.market_analyzer": fake_market_analyzer,
                "engine.intelligence.quant_market_model": fake_quant,
                "engine.intelligence.predictive_market_ai": fake_predict,
                "engine.brain.aliza_engine": fake_aliza,
            },
        )
        cls.modules_patcher.start()

        for module_name in ("api.auth", "api.dashboard_api", "api.server"):
            sys.modules.pop(module_name, None)

        cls.env_patcher = patch.dict(
            os.environ,
            {JWT_SECRET_ENV_VAR: TEST_SECRET},
            clear=False,
        )
        cls.env_patcher.start()

        cls.server = importlib.import_module("api.server")
        cls.client_context = TestClient(cls.server.app)
        cls.client = cls.client_context.__enter__()
        cls.user_token = create_access_token(
            user_id=7,
            username="alice",
            role="user",
        )
        cls.admin_token = create_access_token(
            user_id=1,
            username="admin",
            role="admin",
        )

    @classmethod
    def tearDownClass(cls):
        cls.client_context.__exit__(None, None, None)
        cls.env_patcher.stop()
        cls.modules_patcher.stop()
        for module_name in ("api.auth", "api.dashboard_api", "api.server"):
            sys.modules.pop(module_name, None)

    def setUp(self):
        self.cursor.reset_mock()
        self.conn.reset_mock()
        for business_mock in self._business_mocks():
            business_mock.reset_mock()

    def test_sensitive_routes_require_bearer_token(self):
        requests = [
            ("GET", "/market", None),
            ("GET", "/api/market/btc", None),
            ("POST", "/api/chat", {"message": "hello"}),
            ("GET", "/api/dashboard/market", None),
            ("GET", "/api/dashboard/quant", None),
            ("GET", "/api/dashboard/predict", None),
            ("GET", "/api/dashboard/signals", None),
            ("GET", "/api/dashboard/portfolio", None),
            ("GET", "/admin/users", None),
            ("GET", "/admin/stats", None),
            (
                "POST",
                "/api/auth/auth/register",
                {"username": "new-user", "password": "password"},
            ),
        ]

        for method, path, body in requests:
            with self.subTest(method=method, path=path):
                response = self.client.request(method, path, json=body)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.headers.get("www-authenticate"), "Bearer")

    def test_invalid_token_returns_401_with_bearer_challenge(self):
        response = self.client.get(
            "/market",
            headers={"Authorization": "Bearer invalid-token"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers.get("www-authenticate"), "Bearer")

    def test_user_token_reaches_non_admin_route(self):
        response = self.client.get("/market", headers=self._user_headers())

        self.assertEqual(response.status_code, 200)
        self.get_market_data.assert_called_once_with("BTC")

    def test_user_token_is_forbidden_from_admin_routes_and_register(self):
        requests = [
            ("GET", "/admin/users", None),
            ("GET", "/admin/stats", None),
            (
                "POST",
                "/api/auth/auth/register",
                {"username": "new-user", "password": "password"},
            ),
        ]

        for method, path, body in requests:
            with self.subTest(method=method, path=path):
                response = self.client.request(
                    method,
                    path,
                    json=body,
                    headers=self._user_headers(),
                )
                self.assertEqual(response.status_code, 403)

        self.cursor.execute.assert_not_called()
        self.conn.commit.assert_not_called()

    def test_admin_token_can_reach_register_handler(self):
        self.cursor.fetchone.return_value = None

        response = self.client.post(
            "/api/auth/auth/register",
            json={"username": "new-user", "password": "password"},
            headers=self._admin_headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(self.cursor.execute.call_count, 2)
        self.conn.commit.assert_called_once_with()

    def test_admin_token_can_reach_admin_route(self):
        self.cursor.fetchall.return_value = []

        response = self.client.get(
            "/admin/users",
            headers=self._admin_headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.cursor.execute.assert_called_once_with(
            "SELECT id, username, role FROM users"
        )

    def test_chat_ignores_body_user_id_and_uses_token_identity(self):
        response = self.client.post(
            "/api/chat",
            json={"message": "hello", "user_id": 99999},
            headers=self._user_headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.ask_aliza.assert_called_once_with("hello")
        execute_calls = self.cursor.execute.call_args_list
        self.assertEqual(execute_calls[0].args[1][0], 7)
        self.assertEqual(execute_calls[1].args[1][0], 7)

    def test_unauthorized_chat_has_no_side_effects(self):
        response = self.client.post("/api/chat", json={"message": "hello"})

        self.assertEqual(response.status_code, 401)
        self.ask_aliza.assert_not_called()
        self.cursor.execute.assert_not_called()
        self.conn.commit.assert_not_called()

    def test_unauthorized_market_and_dashboard_routes_skip_business_functions(self):
        paths = [
            "/market",
            "/api/market/btc",
            "/api/dashboard/market",
            "/api/dashboard/quant",
            "/api/dashboard/predict",
            "/api/dashboard/signals",
            "/api/dashboard/portfolio",
        ]

        for path in paths:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 401)

        for business_mock in self._market_business_mocks():
            business_mock.assert_not_called()

    def test_valid_token_reaches_market_and_dashboard_handlers(self):
        paths = [
            "/market",
            "/api/market/btc",
            "/api/dashboard/market",
            "/api/dashboard/quant",
            "/api/dashboard/predict",
            "/api/dashboard/signals",
            "/api/dashboard/portfolio",
        ]

        for path in paths:
            with self.subTest(path=path):
                response = self.client.get(path, headers=self._user_headers())
                self.assertEqual(response.status_code, 200)

        for business_mock in self._market_business_mocks():
            business_mock.assert_called()

    def test_public_health_is_minimal(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_root_remains_public(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)

    def test_login_remains_public(self):
        self.cursor.fetchone.return_value = {
            "id": 7,
            "username": "alice",
            "role": "user",
            "password": hash_password("password"),
        }

        response = self.client.post(
            "/api/auth/auth/login",
            json={"username": "alice", "password": "password"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("token", response.json())
        self.assertFalse(
            any(
                call.args[0].startswith("UPDATE users SET password")
                for call in self.cursor.execute.call_args_list
            )
        )
        self.conn.commit.assert_not_called()


    def _user_headers(self):
        return {"Authorization": f"Bearer {self.user_token}"}

    def _admin_headers(self):
        return {"Authorization": f"Bearer {self.admin_token}"}

    def _business_mocks(self):
        return self._market_business_mocks() + (self.ask_aliza,)

    def _market_business_mocks(self):
        return (
            self.get_market_data,
            self.btc_signal,
            self.scan_opportunities,
            self.get_active_trades,
            self.calculate_market_score,
            self.calculate_market_predictions,
        )


if __name__ == "__main__":
    unittest.main()
