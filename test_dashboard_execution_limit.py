import importlib
import os
import sys
import threading
import types
import unittest
from unittest.mock import MagicMock, Mock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.execution_limit import (
    CHAT_LLM_MAX_CONCURRENCY_ENV_VAR,
    CHAT_LLM_TIMEOUT_ENV_VAR,
    ExecutionLimiter,
    ExecutionTimeoutError,
    get_chat_execution_config,
)
from api.security import JWT_SECRET_ENV_VAR, create_access_token


TEST_SECRET = "execution-limit-test-secret-at-least-32-chars"


class ExecutionLimiterTests(unittest.TestCase):
    def _limiter(self, *, timeout=1.0, concurrency=1):
        limiter = ExecutionLimiter(
            timeout_seconds=timeout,
            max_concurrency=concurrency,
        )
        self.addCleanup(limiter.shutdown)
        return limiter

    def test_success_returns_result_and_releases_slot(self):
        limiter = self._limiter()

        self.assertEqual(limiter.run(lambda: "first"), "first")
        self.assertEqual(limiter.run(lambda: "second"), "second")

    def test_exception_releases_slot(self):
        limiter = self._limiter()

        def fail():
            raise ValueError("test failure")

        with self.assertRaises(ValueError):
            limiter.run(fail)

        self.assertEqual(limiter.run(lambda: "recovered"), "recovered")

    def test_full_concurrency_rejects_before_function_runs(self):
        limiter = self._limiter()
        started = threading.Event()
        release = threading.Event()
        result = []

        def blocking_call():
            started.set()
            release.wait(1)
            return "finished"

        worker = threading.Thread(
            target=lambda: result.append(limiter.run(blocking_call)),
        )
        worker.start()
        self.assertTrue(started.wait(1))
        rejected_function = Mock(return_value="must-not-run")

        try:
            with self.assertRaises(HTTPException) as caught:
                limiter.run(rejected_function)
        finally:
            release.set()
            worker.join(1)

        self.assertEqual(caught.exception.status_code, 503)
        self.assertEqual(caught.exception.detail, "Chat service is busy")
        rejected_function.assert_not_called()
        self.assertFalse(worker.is_alive())
        self.assertEqual(result, ["finished"])

    def test_timeout_is_generic_and_task_keeps_slot_until_done(self):
        limiter = self._limiter(timeout=0.01)
        release = threading.Event()
        finished = threading.Event()

        def blocking_call():
            release.wait(1)
            finished.set()

        try:
            with self.assertRaises(ExecutionTimeoutError) as caught:
                limiter.run(blocking_call)

            self.assertEqual(str(caught.exception), "Chat execution timed out.")
            with self.assertRaises(HTTPException):
                limiter.run(lambda: "must-not-run")
        finally:
            release.set()
            self.assertTrue(finished.wait(1))

    def test_executor_is_reused_across_requests(self):
        limiter = self._limiter()
        executor = limiter._executor

        limiter.run(lambda: "first")
        limiter.run(lambda: "second")

        self.assertIs(limiter._executor, executor)

    def test_default_config(self):
        with patch.dict(os.environ, {}, clear=True):
            timeout, concurrency = get_chat_execution_config()

        self.assertEqual(timeout, 45.0)
        self.assertEqual(concurrency, 2)

    def test_invalid_timeout_config_is_rejected(self):
        for value in ("", "0", "-1", "121", "nan", "invalid"):
            with self.subTest(value=value):
                with patch.dict(
                    os.environ,
                    {CHAT_LLM_TIMEOUT_ENV_VAR: value},
                    clear=True,
                ):
                    with self.assertRaises(RuntimeError):
                        get_chat_execution_config()

    def test_invalid_concurrency_config_is_rejected(self):
        for value in ("", "0", "-1", "9", "1.5", "invalid"):
            with self.subTest(value=value):
                with patch.dict(
                    os.environ,
                    {CHAT_LLM_MAX_CONCURRENCY_ENV_VAR: value},
                    clear=True,
                ):
                    with self.assertRaises(RuntimeError):
                        get_chat_execution_config()


class ChatExecutionEndpointTests(unittest.TestCase):
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
        cls.client_context = TestClient(cls.server.app)
        cls.client = cls.client_context.__enter__()
        cls.user_token = create_access_token(
            user_id=7,
            username="alice",
            role="user",
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
        self.ask_aliza.reset_mock()
        self.server.CHAT_RATE_LIMITER.clear()

    def test_success_returns_llm_result_and_persists(self):
        response = self._chat()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["answer"], "test answer")
        self.ask_aliza.assert_called_once_with("hello")
        self.assertEqual(self.cursor.execute.call_count, 2)
        self.conn.commit.assert_called_once_with()

    def test_timeout_returns_fallback_without_database_write(self):
        with patch.object(
            self.server.CHAT_LLM_EXECUTION_LIMITER,
            "run",
            side_effect=ExecutionTimeoutError("internal timeout detail"),
        ):
            response = self._chat()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["answer"], self.server._FALLBACK_REPLY)
        self.assertEqual(response.json()["tokens"], 0)
        self.assertNotIn("internal timeout detail", response.text)
        self.cursor.execute.assert_not_called()
        self.conn.commit.assert_not_called()

    def test_llm_exception_returns_fallback_without_database_write(self):
        with patch.object(
            self.server.CHAT_LLM_EXECUTION_LIMITER,
            "run",
            side_effect=RuntimeError("internal exception detail"),
        ):
            response = self._chat()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["answer"], self.server._FALLBACK_REPLY)
        self.assertNotIn("internal exception detail", response.text)
        self.cursor.execute.assert_not_called()
        self.conn.commit.assert_not_called()

    def test_busy_request_is_rejected_before_ask_aliza(self):
        with patch.object(
            self.server.CHAT_LLM_EXECUTION_LIMITER,
            "run",
            side_effect=HTTPException(
                status_code=503,
                detail="Chat service is busy",
            ),
        ):
            response = self._chat()

        self.assertEqual(response.status_code, 503)
        self.ask_aliza.assert_not_called()
        self.cursor.execute.assert_not_called()

    def test_unauthorized_request_does_not_use_execution_slot(self):
        with patch.object(
            self.server.CHAT_LLM_EXECUTION_LIMITER,
            "run",
        ) as execute:
            response = self.client.post("/api/chat", json={"message": "hello"})

        self.assertEqual(response.status_code, 401)
        execute.assert_not_called()

    def test_rate_limited_request_does_not_use_execution_slot(self):
        with (
            patch.object(
                self.server.CHAT_RATE_LIMITER,
                "check",
                side_effect=HTTPException(
                    status_code=429,
                    detail="Too many requests",
                ),
            ),
            patch.object(
                self.server.CHAT_LLM_EXECUTION_LIMITER,
                "run",
            ) as execute,
        ):
            response = self._chat()

        self.assertEqual(response.status_code, 429)
        execute.assert_not_called()
        self.ask_aliza.assert_not_called()
        self.cursor.execute.assert_not_called()

    def _chat(self):
        return self.client.post(
            "/api/chat",
            json={"message": "hello", "user_id": 99999},
            headers={"Authorization": f"Bearer {self.user_token}"},
        )


if __name__ == "__main__":
    unittest.main()
