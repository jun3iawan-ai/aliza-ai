import builtins
import importlib.util
import os
import runpy
import socket
import sys
import tempfile
import types
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi import APIRouter

from core import environment


ROOT = Path(__file__).resolve().parent
RUNNER = ROOT / "scripts" / "run_dashboard.py"


def _is_dotenv_path(value) -> bool:
    try:
        return Path(os.fspath(value)).name == ".env"
    except TypeError:
        return False


@contextmanager
def forbid_dotenv_file_access():
    real_open = builtins.open
    real_stat = os.stat
    real_read_text = Path.read_text

    def guarded_open(file, *args, **kwargs):
        if _is_dotenv_path(file):
            raise AssertionError("dotenv file access is forbidden")
        return real_open(file, *args, **kwargs)

    def guarded_stat(path, *args, **kwargs):
        if _is_dotenv_path(path):
            raise AssertionError("dotenv stat is forbidden")
        return real_stat(path, *args, **kwargs)

    def guarded_read_text(path, *args, **kwargs):
        if _is_dotenv_path(path):
            raise AssertionError("dotenv read_text is forbidden")
        return real_read_text(path, *args, **kwargs)

    with (
        patch("builtins.open", side_effect=guarded_open),
        patch("os.stat", side_effect=guarded_stat),
        patch.object(Path, "read_text", new=guarded_read_text),
    ):
        yield


class DotenvPolicyTests(unittest.TestCase):
    def test_disabled_policy_has_no_discovery_or_file_access(self):
        with (
            patch("dotenv.load_dotenv") as load_dotenv,
            patch("dotenv.find_dotenv") as find_dotenv,
            patch.dict(
                os.environ,
                {environment.ALIZA_DOTENV_ENABLED: "false"},
                clear=True,
            ),
            forbid_dotenv_file_access(),
        ):
            self.assertFalse(environment.load_project_dotenv())

        load_dotenv.assert_not_called()
        find_dotenv.assert_not_called()

    def test_boolean_parser_accepts_documented_values(self):
        for value in ("1", "true", "yes", "on", " TRUE "):
            with self.subTest(value=value), patch.dict(
                os.environ,
                {environment.ALIZA_DOTENV_ENABLED: value},
                clear=True,
            ):
                self.assertTrue(environment.dotenv_enabled())

        for value in ("0", "false", "no", "off", " OFF "):
            with self.subTest(value=value), patch.dict(
                os.environ,
                {environment.ALIZA_DOTENV_ENABLED: value},
                clear=True,
            ):
                self.assertFalse(environment.dotenv_enabled())

    def test_invalid_or_empty_policy_fails_before_file_access(self):
        for value in ("", "invalid", "2"):
            with (
                self.subTest(value=value),
                patch("dotenv.load_dotenv") as load_dotenv,
                patch("dotenv.find_dotenv") as find_dotenv,
                patch.dict(
                    os.environ,
                    {environment.ALIZA_DOTENV_ENABLED: value},
                    clear=True,
                ),
                forbid_dotenv_file_access(),
            ):
                with self.assertRaises(RuntimeError):
                    environment.load_project_dotenv()
                load_dotenv.assert_not_called()
                find_dotenv.assert_not_called()

    def test_enabled_policy_uses_explicit_path_and_preserves_environment(self):
        from dotenv import load_dotenv as real_load_dotenv

        with tempfile.TemporaryDirectory() as temp_dir:
            dotenv_path = Path(temp_dir) / ".env"
            dotenv_path.write_text(
                "DOTENV_EXISTING=file-value\nDOTENV_NEW=file-value\n",
                encoding="utf-8",
            )
            with (
                patch.dict(
                    os.environ,
                    {
                        environment.ALIZA_DOTENV_ENABLED: "true",
                        "DOTENV_EXISTING": "process-value",
                    },
                    clear=True,
                ),
                patch.object(
                    environment,
                    "_project_dotenv_path",
                    return_value=dotenv_path,
                ),
                patch("dotenv.load_dotenv", wraps=real_load_dotenv) as load_dotenv,
                patch("dotenv.find_dotenv") as find_dotenv,
            ):
                self.assertTrue(environment.load_project_dotenv())
                self.assertEqual(os.environ["DOTENV_EXISTING"], "process-value")
                self.assertEqual(os.environ["DOTENV_NEW"], "file-value")

            load_dotenv.assert_called_once_with(
                dotenv_path=dotenv_path,
                override=False,
            )
            find_dotenv.assert_not_called()

    def test_legacy_default_loads_only_explicit_project_path(self):
        from dotenv import load_dotenv as real_load_dotenv

        with tempfile.TemporaryDirectory() as temp_dir:
            dotenv_path = Path(temp_dir) / ".env"
            dotenv_path.write_text("LEGACY_TEMP_VALUE=loaded\n", encoding="utf-8")
            with (
                patch.dict(os.environ, {}, clear=True),
                patch.object(
                    environment,
                    "_project_dotenv_path",
                    return_value=dotenv_path,
                ),
                patch("dotenv.load_dotenv", wraps=real_load_dotenv) as load_dotenv,
                patch("dotenv.find_dotenv") as find_dotenv,
            ):
                self.assertTrue(environment.load_project_dotenv())
                self.assertEqual(os.environ["LEGACY_TEMP_VALUE"], "loaded")

            load_dotenv.assert_called_once_with(
                dotenv_path=dotenv_path,
                override=False,
            )
            find_dotenv.assert_not_called()


class DashboardRunnerTests(unittest.TestCase):
    def _load_runner(self, initial_environment):
        calls = []
        import_markers = []
        fake_uvicorn = types.ModuleType("uvicorn")

        def fake_run(*args, **kwargs):
            calls.append(
                (
                    args,
                    kwargs,
                    os.environ.get(environment.ALIZA_DOTENV_ENABLED),
                )
            )

        fake_uvicorn.run = fake_run
        real_import = builtins.__import__

        def tracking_import(name, *args, **kwargs):
            if name in {"uvicorn", "api.server"}:
                import_markers.append(
                    (name, os.environ.get(environment.ALIZA_DOTENV_ENABLED))
                )
            return real_import(name, *args, **kwargs)

        with (
            patch.dict(os.environ, initial_environment, clear=True),
            patch.dict(sys.modules, {"uvicorn": fake_uvicorn}),
            patch("builtins.__import__", side_effect=tracking_import),
        ):
            namespace = runpy.run_path(
                str(RUNNER),
                run_name="dashboard_runner_isolation_test",
            )
            marker_after_import = os.environ[environment.ALIZA_DOTENV_ENABLED]
            yield namespace, calls, import_markers, marker_after_import

    def test_runner_sets_false_before_application_can_be_imported(self):
        for namespace, calls, imports, marker in self._load_runner({}):
            self.assertEqual(marker, "false")
            self.assertIn(("uvicorn", "false"), imports)
            self.assertNotIn("api.server", [name for name, _value in imports])
            with forbid_dotenv_file_access(), patch("builtins.print"):
                namespace["main"]()

            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][0][0], "api.server:app")
            self.assertEqual(calls[0][2], "false")

    def test_runner_preserves_explicit_false(self):
        for namespace, calls, _imports, marker in self._load_runner(
            {environment.ALIZA_DOTENV_ENABLED: "false"}
        ):
            self.assertEqual(marker, "false")
            with forbid_dotenv_file_access(), patch("builtins.print"):
                namespace["main"]()
            self.assertEqual(calls[0][2], "false")

    def test_runner_preserves_invalid_value_and_fails_closed(self):
        for namespace, calls, _imports, marker in self._load_runner(
            {environment.ALIZA_DOTENV_ENABLED: "invalid"}
        ):
            self.assertEqual(marker, "invalid")
            with forbid_dotenv_file_access(), patch("builtins.print"):
                with self.assertRaises(RuntimeError):
                    namespace["main"]()
            self.assertEqual(calls, [])


class DashboardImportIsolationTests(unittest.TestCase):
    def test_dashboard_import_does_not_access_dotenv_db_or_network(self):
        fake_database = types.ModuleType("core.database")
        fake_database.conn = Mock()
        fake_database.cursor = Mock()

        fake_auth = types.ModuleType("api.auth")
        fake_auth.router = APIRouter()

        fake_dashboard_api = types.ModuleType("api.dashboard_api")
        fake_dashboard_api.router = APIRouter()

        fake_execution_limit = types.ModuleType("api.execution_limit")
        fake_execution_limit.CHAT_LLM_EXECUTION_LIMITER = Mock()
        fake_execution_limit.ExecutionTimeoutError = type(
            "ExecutionTimeoutError",
            (Exception,),
            {},
        )

        module_name = "dashboard_server_dotenv_isolation_test"
        spec = importlib.util.spec_from_file_location(
            module_name,
            ROOT / "api" / "server.py",
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)

        with (
            patch.dict(
                os.environ,
                {
                    "JWT_SECRET": "test-only-signing-secret-at-least-32-bytes",
                },
                clear=True,
            ),
            patch.dict(
                sys.modules,
                {
                    "core.database": fake_database,
                    "api.auth": fake_auth,
                    "api.dashboard_api": fake_dashboard_api,
                    "api.execution_limit": fake_execution_limit,
                },
            ),
            forbid_dotenv_file_access(),
            patch.object(
                socket.socket,
                "connect",
                side_effect=AssertionError("network access is forbidden"),
            ),
        ):
            spec.loader.exec_module(module)
            self.assertEqual(
                os.environ[environment.ALIZA_DOTENV_ENABLED],
                "false",
            )

        self.assertIsNotNone(module.app)
        fake_database.conn.assert_not_called()
        fake_database.cursor.assert_not_called()


class StaticSourcePolicyTests(unittest.TestCase):
    def test_direct_dotenv_calls_exist_only_in_central_helper_or_tests(self):
        helper = ROOT / "core" / "environment.py"
        forbidden_call = "load_" + "dotenv("
        forbidden_find = "find_" + "dotenv("

        for path in ROOT.rglob("*.py"):
            relative = path.relative_to(ROOT)
            if any(part in {".git", "venv", "docs"} for part in relative.parts):
                continue
            if path == helper or path.name.startswith("test_"):
                continue

            source = path.read_text(encoding="utf-8")
            self.assertNotIn(forbidden_call, source, str(relative))
            self.assertNotIn(forbidden_find, source, str(relative))
            self.assertNotIn("override=True", source, str(relative))

        helper_source = helper.read_text(encoding="utf-8")
        self.assertNotIn(forbidden_find, helper_source)
        self.assertIn("override=False", helper_source)

        server_source = (ROOT / "api" / "server.py").read_text(encoding="utf-8")
        self.assertLess(
            server_source.index("os.environ.setdefault"),
            server_source.index("from core.database import"),
        )

    def test_expected_legacy_callsites_use_central_helper(self):
        callsites = (
            ROOT / "main.py",
            ROOT / "core" / "database.py",
            ROOT / "interfaces" / "telegram_bot.py",
            ROOT / "interfaces" / "market_bot.py",
            ROOT / "engine" / "monitoring" / "market_monitor.py",
        )
        for path in callsites:
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertIn(
                    "load_project_dotenv()",
                    path.read_text(encoding="utf-8"),
                )


if __name__ == "__main__":
    unittest.main()
