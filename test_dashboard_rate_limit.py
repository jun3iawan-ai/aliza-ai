import importlib
import os
import sys
import types
import unittest
from unittest.mock import MagicMock, Mock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.rate_limit import RateLimiter
from api.security import JWT_SECRET_ENV_VAR, create_access_token


TEST_SECRET = "rate-limit-test-secret-value-at-least-32-chars"


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class RateLimiterTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()

    def test_requests_below_limit_are_accepted(self):
        limiter = RateLimiter(limit=2, window_seconds=60, clock=self.clock)

        limiter.check("client")
        limiter.check("client")

    def test_request_over_limit_has_positive_retry_after(self):
        limiter = RateLimiter(limit=1, window_seconds=60, clock=self.clock)
        limiter.check("client")

        with self.assertRaises(HTTPException) as caught:
            limiter.check("client")

        self.assertEqual(caught.exception.status_code, 429)
        self.assertGreater(int(caught.exception.headers["Retry-After"]), 0)

    def test_window_expiry_allows_requests_again(self):
        limiter = RateLimiter(limit=1, window_seconds=10, clock=self.clock)
        limiter.check("client")
        self.clock.advance(10)

        limiter.check("client")

    def test_separate_keys_do_not_block_each_other(self):
        limiter = RateLimiter(limit=1, window_seconds=60, clock=self.clock)

        limiter.check("first")
        limiter.check("second")

    def test_keys_are_cleaned_and_bounded(self):
        limiter = RateLimiter(
            limit=1,
            window_seconds=10,
            max_keys=2,
            clock=self.clock,
        )
        limiter.check("first")
        limiter.check("second")
        limiter.check("third")
        self.assertEqual(limiter.key_count, 2)

        self.clock.advance(10)
        limiter.check("new")
        self.assertEqual(limiter.key_count, 1)

    def test_error_detail_does_not_disclose_key(self):
        limiter = RateLimiter(limit=1, window_seconds=60, clock=self.clock)
        limiter.check("sensitive-username")

        with self.assertRaises(HTTPException) as caught:
            limiter.check("sensitive-username")

        self.assertEqual(caught.exception.detail, "Too many requests")
        self.assertNotIn("sensitive-username", caught.exception.detail)


class DashboardRateLimitInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cursor = MagicMock()
        cls.conn = MagicMock()
        cls.ask_aliza = Mock(return_value="test answer")

        fake_database = types.ModuleType("core.database")
        fake_database.cursor = cls.cursor
        fake_database.conn = cls.conn

        fake_aliza = types.ModuleType("engine.brain.aliza_engine")
        fake_aliza.ask_aliza = cls.ask_aliza

        cls.modules_patcher = patch.dict(
            sys.modules,
            {
                "core.database": fake_database,
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
        cls.auth = sys.modules["api.auth"]
        cls.client_context = TestClient(cls.server.app)
        cls.client = cls.client_context.__enter__()
        cls.user_token = create_access_token(
            user_id=7,
            username="alice",
            role="user",
        )
        cls.other_user_token = create_access_token(
            user_id=8,
            username="bob",
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
        self.cursor.fetchone.return_value = None
        self.conn.reset_mock()
        self.conn.commit.side_effect = None
        self.ask_aliza.reset_mock()
        self.auth.LOGIN_IP_RATE_LIMITER.clear()
        self.auth.LOGIN_USERNAME_RATE_LIMITER.clear()
        self.auth.REGISTER_RATE_LIMITER.clear()
        self.server.CHAT_RATE_LIMITER.clear()

    def test_login_limit_per_ip_and_username_blocks_before_database(self):
        with patch.object(self.auth, "verify_password", return_value=False):
            for _ in range(5):
                response = self._login(" Alice ")
                self.assertEqual(response.status_code, 401)

            blocked = self._login("alice")

        self.assertEqual(blocked.status_code, 429)
        self.assertGreater(int(blocked.headers["retry-after"]), 0)
        self.assertEqual(self.cursor.execute.call_count, 5)

    def test_login_ip_limit_applies_across_different_usernames(self):
        with patch.object(self.auth, "verify_password", return_value=False):
            for number in range(20):
                response = self._login(f"user-{number}")
                self.assertEqual(response.status_code, 401)

            blocked = self._login("another-user")

        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(self.cursor.execute.call_count, 20)

    def test_login_input_limits_return_422_before_database(self):
        too_long_password = self._login("alice", "x" * 129)
        too_long_username = self._login("x" * 65, "password")

        self.assertEqual(too_long_password.status_code, 422)
        self.assertEqual(too_long_username.status_code, 422)
        self.cursor.execute.assert_not_called()

    def test_unknown_user_uses_dummy_argon2_and_stays_generic(self):
        with (
            patch.object(
                self.auth,
                "verify_password",
                wraps=self.auth.verify_password,
            ) as verify,
            patch.object(self.auth, "create_access_token") as create_token,
        ):
            response = self._login("missing-user", "candidate-password")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Invalid username or password")
        verify.assert_called_once()
        self.assertIs(verify.call_args.args[1], self.auth._DUMMY_PASSWORD_HASH)
        self.conn.commit.assert_not_called()
        create_token.assert_not_called()

    def test_register_password_limits_return_422(self):
        short_response = self.client.post(
            "/api/auth/auth/register",
            json={"username": "new-user", "password": "short"},
            headers=self._admin_headers(),
        )
        long_response = self.client.post(
            "/api/auth/auth/register",
            json={"username": "new-user", "password": "x" * 129},
            headers=self._admin_headers(),
        )

        self.assertEqual(short_response.status_code, 422)
        self.assertEqual(long_response.status_code, 422)
        self.cursor.execute.assert_not_called()

    def test_blocked_register_skips_database_hash_and_commit(self):
        with patch.object(
            self.auth,
            "hash_password",
            return_value="$argon2id$test-hash",
        ) as hash_password:
            for number in range(10):
                response = self.client.post(
                    "/api/auth/auth/register",
                    json={
                        "username": f"new-user-{number}",
                        "password": "valid-password",
                    },
                    headers=self._admin_headers(),
                )
                self.assertEqual(response.status_code, 200)

            blocked = self.client.post(
                "/api/auth/auth/register",
                json={
                    "username": "blocked-user",
                    "password": "valid-password",
                },
                headers=self._admin_headers(),
            )

        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(self.cursor.execute.call_count, 20)
        self.assertEqual(hash_password.call_count, 10)
        self.assertEqual(self.conn.commit.call_count, 10)

    def test_chat_limit_uses_jwt_user_and_blocks_before_side_effects(self):
        for body_user_id in range(10):
            response = self.client.post(
                "/api/chat",
                json={"message": "hello", "user_id": body_user_id},
                headers=self._user_headers(),
            )
            self.assertEqual(response.status_code, 200)

        blocked = self.client.post(
            "/api/chat",
            json={"message": "hello", "user_id": 99999},
            headers=self._user_headers(),
        )

        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(self.ask_aliza.call_count, 10)
        self.assertEqual(self.cursor.execute.call_count, 20)
        self.assertEqual(self.conn.commit.call_count, 10)

    def test_chat_users_have_separate_buckets(self):
        for _ in range(10):
            response = self.client.post(
                "/api/chat",
                json={"message": "hello"},
                headers=self._user_headers(),
            )
            self.assertEqual(response.status_code, 200)

        other_user_response = self.client.post(
            "/api/chat",
            json={"message": "hello"},
            headers=self._other_user_headers(),
        )

        self.assertEqual(other_user_response.status_code, 200)
        self.assertEqual(self.ask_aliza.call_count, 11)

    def test_chat_input_limits_and_whitespace_return_422(self):
        requests = [
            {"message": "x" * 4001},
            {"prompt": "x" * 4001},
            {"message": "hello", "channel": "x" * 33},
            {"message": "   ", "prompt": " 	 "},
        ]

        for body in requests:
            with self.subTest(body_fields=tuple(body)):
                response = self.client.post(
                    "/api/chat",
                    json=body,
                    headers=self._user_headers(),
                )
                self.assertEqual(response.status_code, 422)

        self.ask_aliza.assert_not_called()
        self.cursor.execute.assert_not_called()

    def test_chat_prefers_message_when_message_and_prompt_are_both_set(self):
        response = self.client.post(
            "/api/chat",
            json={"message": "first", "prompt": "second"},
            headers=self._user_headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.ask_aliza.assert_called_once_with("first")

    def _login(self, username, password="wrong-password"):
        return self.client.post(
            "/api/auth/auth/login",
            json={"username": username, "password": password},
        )

    def _user_headers(self):
        return {"Authorization": f"Bearer {self.user_token}"}

    def _other_user_headers(self):
        return {"Authorization": f"Bearer {self.other_user_token}"}

    def _admin_headers(self):
        return {"Authorization": f"Bearer {self.admin_token}"}


if __name__ == "__main__":
    unittest.main()
