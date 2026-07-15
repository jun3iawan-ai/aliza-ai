import os
import unittest
from unittest.mock import patch

from scripts import run_dashboard


class DashboardBindingTests(unittest.TestCase):
    def test_default_host_is_ipv4_loopback(self):
        with patch.dict(os.environ, {}, clear=True):
            host, _ = run_dashboard.get_dashboard_config()

        self.assertEqual(host, "127.0.0.1")

    def test_default_port_is_8001(self):
        with patch.dict(os.environ, {}, clear=True):
            _, port = run_dashboard.get_dashboard_config()

        self.assertEqual(port, 8001)

    def test_valid_port_override_is_used(self):
        with patch.dict(os.environ, {"ALIZA_DASHBOARD_PORT": "18001"}, clear=True):
            _, port = run_dashboard.get_dashboard_config()

        self.assertEqual(port, 18001)

    def test_loopback_hosts_are_accepted(self):
        for expected in ("127.0.0.1", "localhost", "::1"):
            with self.subTest(host=expected):
                with patch.dict(
                    os.environ,
                    {"ALIZA_DASHBOARD_HOST": expected},
                    clear=True,
                ):
                    host, _ = run_dashboard.get_dashboard_config()

                self.assertEqual(host, expected)

    def test_ipv4_wildcard_is_rejected(self):
        with patch.dict(
            os.environ,
            {"ALIZA_DASHBOARD_HOST": "0.0.0.0"},
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "loopback-only"):
                run_dashboard.get_dashboard_config()

    def test_ipv6_wildcard_is_rejected(self):
        with patch.dict(
            os.environ,
            {"ALIZA_DASHBOARD_HOST": "::"},
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "loopback-only"):
                run_dashboard.get_dashboard_config()

    def test_empty_host_falls_back_to_ipv4_loopback(self):
        with patch.dict(
            os.environ,
            {"ALIZA_DASHBOARD_HOST": "   "},
            clear=True,
        ):
            host, _ = run_dashboard.get_dashboard_config()

        self.assertEqual(host, "127.0.0.1")

    def test_main_passes_safe_config_and_reload_false_to_uvicorn(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(run_dashboard.uvicorn, "run") as uvicorn_run,
            patch("builtins.print") as print_mock,
        ):
            run_dashboard.main()

        uvicorn_run.assert_called_once_with(
            "api.server:app",
            host="127.0.0.1",
            port=8001,
            reload=False,
        )
        startup_output = " ".join(
            " ".join(str(arg) for arg in call.args)
            for call in print_mock.call_args_list
        )
        self.assertNotIn("0.0.0.0", startup_output)


if __name__ == "__main__":
    unittest.main()
