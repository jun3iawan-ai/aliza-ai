"""
Jalankan Aliza Dashboard (FastAPI + Uvicorn).

Port dikonfigurasi via environment variable:
  ALIZA_DASHBOARD_PORT  (default: 8001)

Contoh:
  python scripts/run_dashboard.py

  export ALIZA_DASHBOARD_PORT=8080
  python scripts/run_dashboard.py
"""
import os
import sys

# Fix Python path agar api/, engine/, interfaces/ dapat diakses dari mana pun CWD
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

import uvicorn

PORT = int(os.getenv("ALIZA_DASHBOARD_PORT", "8001"))

if __name__ == "__main__":
    print(f"Aliza Dashboard running on port {PORT}")
    print(f"Dashboard: http://0.0.0.0:{PORT}")
    print(f"Health:    http://0.0.0.0:{PORT}/health")
    uvicorn.run(
        "api.server:app",
        host="0.0.0.0",
        port=PORT,
        reload=False
    )
