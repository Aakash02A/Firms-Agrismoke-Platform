"""
AgriSmoke AI - Master Test Suite Runner
Executes comprehensive end-to-end tests across:
1. Frontend DOM references & syntax
2. SQLite schema & database CRUD
3. Machine Learning inference & boundary physics
4. Backend API endpoints & static asset delivery
"""

import sys
import subprocess
from pathlib import Path

# Configure UTF-8 safe stdout for Windows console
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

TESTS_DIR = Path(__file__).resolve().parent

TEST_SCRIPTS = [
    ("Frontend DOM Element Verification", "test_dom_elements.py"),
    ("PWA & Static Asset Serving", "test_pwa_assets.py"),
    ("SQLite Database Layer", "test_database.py"),
    ("SQLite Production Readiness (WAL/backup/retention)", "test_sqlite_production.py"),
    ("Scheduler Ingestion & Backup Automation", "test_scheduler_maintenance.py"),
    ("NASA FIRMS Ingestion & Intelligence Layer", "test_nasa_firms.py"),
    ("On-Demand NASA FIRMS (Stateless Public Deployment)", "test_firms_on_demand.py"),
    ("Machine Learning & Physical Dispersion", "test_ml_model.py"),
    ("FastAPI Backend & API Endpoints", "test_backend_api.py"),
    ("Secret Leakage & Redaction Hardening", "test_security_scrubbing.py")
]

def run_all():
    print("=" * 70)
    print(">> AgriSmoke AI - Automated End-to-End Test Suite")
    print("=" * 70)

    total = len(TEST_SCRIPTS)
    passed = 0

    for name, script in TEST_SCRIPTS:
        script_path = TESTS_DIR / script
        print(f"\n[RUNNING] {name} ({script})...")
        res = subprocess.run([sys.executable, str(script_path)], capture_output=True, text=True, encoding="utf-8", errors="replace")
        
        if res.returncode == 0:
            print(f"[SUCCESS] {name} PASSED.")
            passed += 1
            for line in res.stdout.splitlines():
                if line.startswith("[PASS]") or line.startswith("==="):
                    print("   " + line)
        else:
            print(f"[FAILED] {name} FAILED with return code {res.returncode}")
            print("STDOUT:\n" + res.stdout)
            print("STDERR:\n" + res.stderr)

    print("\n" + "=" * 70)
    print(f"Test Suite Summary: {passed}/{total} Test Suites Passed ({round((passed/total)*100)}%)")
    print("=" * 70)

    if passed == total:
        print(">> ALL SYSTEMS OPERATIONAL AND VALIDATED!")
        return 0
    else:
        print(">> SOME TESTS FAILED. Please review the errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(run_all())
