"""
AgriSmoke AI - Backend Server Runner
Usage:
    python backend/run.py
Starts FastAPI server on http://127.0.0.1:8000
"""

import sys
from pathlib import Path
import uvicorn

# Configure UTF-8 safe stdout for Windows console
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure backend directory is in path
ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
AI_ML_DIR = ROOT_DIR / "ai-ml"

for p in [str(ROOT_DIR), str(BACKEND_DIR), str(AI_ML_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Import app object directly
from main import app
from app_config import config

if __name__ == "__main__":
    print("=" * 65)
    print(">> Starting AgriSmoke AI Python Backend Server")
    print(">> Environment: " + config.environment)
    print(f">> Binding {config.host}:{config.port} "
          f"(docs={'on' if config.docs_enabled else 'off'}, "
          f"read-only={'yes' if config.read_only else 'no'})")
    print("=" * 65)
    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        log_level="info",
        reload=False,
        proxy_headers=config.proxy_headers,
        forwarded_allow_ips=config.forwarded_allow_ips,
    )
