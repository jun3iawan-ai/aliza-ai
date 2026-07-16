"""
Jalankan Aliza Dashboard (FastAPI + Uvicorn).

Host dan port dikonfigurasi via environment variable:
  ALIZA_DASHBOARD_HOST  (default: 127.0.0.1; loopback only)
  ALIZA_DASHBOARD_PORT  (default: 8001)

Contoh:
  python scripts/run_dashboard.py

  export ALIZA_DASHBOARD_PORT=8080
  python scripts/run_dashboard.py
"""
import os
import sys

os.environ.setdefault("ALIZA_DOTENV_ENABLED", "false")

# Fix Python path agar api/, engine/, interfaces/ dapat diakses dari mana pun CWD
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

import uvicorn
from core.environment import load_project_dotenv

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8001
ALLOWED_HOSTS = {DEFAULT_HOST, "localhost", "::1"}


def get_dashboard_config():
    host = (os.getenv("ALIZA_DASHBOARD_HOST") or "").strip() or DEFAULT_HOST
    if host not in ALLOWED_HOSTS:
        raise ValueError(
            "ALIZA_DASHBOARD_HOST must be loopback-only "
            "(127.0.0.1, localhost, or ::1)."
        )

    port = int(os.getenv("ALIZA_DASHBOARD_PORT", str(DEFAULT_PORT)))
    return host, port


def main():
    load_project_dotenv()
    host, port = get_dashboard_config()
    print(f"Aliza Dashboard listening on loopback host {host}, port {port}")
    uvicorn.run(
        "api.server:app",
        host=host,
        port=port,
        reload=False,
    )


if __name__ == "__main__":
    main()
