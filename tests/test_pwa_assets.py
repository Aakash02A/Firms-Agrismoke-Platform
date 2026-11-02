"""
Test Suite: PWA & Static Asset Serving (Phase 3)

Exercises the real HTTP surface of the FastAPI app with a TestClient to prove the
frontend is deploy-ready:
  * /, /index.html, /manifest.json, /service-worker.js all return HTTP 200
    (they previously 404'd because only '/', '/css' and '/js' were routed, which
    broke service-worker install and the manifest link).
  * Every asset the service worker precaches actually resolves, so cache.addAll
    cannot fail and strand the PWA in a non-installed state.
  * Every root-relative href/src referenced by index.html resolves (no broken
    relative paths in production).
  * The service worker and HTML entry points are served no-cache so a deploy
    propagates to clients, and the cache version is well-formed.
  * Production routing does NOT expose unintended files (README, .env, VCS).

The app is imported with DB_PATH pointed at an isolated temp file and the
startup/shutdown events are never triggered (the TestClient is not used as a
context manager), so neither the database nor the background scheduler is touched.
"""

import os
import re
import sys
import json
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

# Isolate before importing backend.main (which imports backend.database).
_TMP = Path(tempfile.mkdtemp(prefix="agrismoke_pwa_test_"))
os.environ["DB_PATH"] = str(_TMP / "agri_pwa_test.db")

sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "backend"))
sys.path.insert(0, str(ROOT_DIR / "ai-ml"))

from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402
from backend.main import app  # noqa: E402

FRONTEND_DIR = ROOT_DIR / "frontend"


class TestPwaStaticAssets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Not entering the context manager means the ASGI lifespan (startup /
        # shutdown) does NOT run, so scheduler.start()/ensure_ready() are skipped.
        cls.client = TestClient(app)

    def _get(self, path):
        return self.client.get(path)

    # ----------------------------------------------------------------- routes
    def test_core_frontend_routes_return_200(self):
        for path in ["/", "/index.html", "/manifest.json", "/service-worker.js",
                     "/css/styles.css", "/js/app.js", "/favicon.ico"]:
            r = self._get(path)
            self.assertEqual(r.status_code, 200, f"{path} -> {r.status_code}")

    def test_content_types(self):
        self.assertIn("text/html", self._get("/").headers["content-type"])
        self.assertIn("text/html", self._get("/index.html").headers["content-type"])
        self.assertIn("manifest", self._get("/manifest.json").headers["content-type"])
        self.assertIn("javascript", self._get("/service-worker.js").headers["content-type"])

    def test_manifest_is_valid_json_with_icons(self):
        r = self._get("/manifest.json")
        data = json.loads(r.text)
        self.assertIn("start_url", data)
        self.assertIn("icons", data)
        self.assertTrue(len(data["icons"]) >= 1, "manifest must declare at least one icon")

    def test_entry_points_are_no_cache(self):
        # The SW and HTML shell must not be served from a stale cache, or a
        # deployment update would not reach the client.
        for path in ["/", "/index.html", "/service-worker.js", "/manifest.json"]:
            cc = self._get(path).headers.get("cache-control", "")
            self.assertIn("no-cache", cc, f"{path} missing no-cache: {cc!r}")

    # ------------------------------------------------------------- service worker
    def _sw_precache_list(self):
        sw_src = (FRONTEND_DIR / "service-worker.js").read_text(encoding="utf-8")
        block = re.search(r"STATIC_ASSETS\s*=\s*\[(.*?)\]", sw_src, re.S)
        self.assertIsNotNone(block, "service-worker.js must declare a STATIC_ASSETS precache list")
        return re.findall(r"['\"]([^'\"]+)['\"]", block.group(1))

    def test_service_worker_precache_entries_all_resolve(self):
        # cache.addAll() aborts the whole install if ANY entry 404s.
        for asset in self._sw_precache_list():
            r = self._get("/" + asset.lstrip("/"))
            self.assertLess(r.status_code, 400, f"SW precache entry /{asset} -> {r.status_code}")

    def test_cache_version_is_bem_formatted(self):
        sw_src = (FRONTEND_DIR / "service-worker.js").read_text(encoding="utf-8")
        m = re.search(r"CACHE_NAME\s*=\s*['\"]([^'\"]+)['\"]", sw_src)
        self.assertIsNotNone(m, "CACHE_NAME not found")
        self.assertRegex(m.group(1), r"^agrismoke-v\d+\.\d+$",
                         "cache version must be 'agrismoke-vMAJOR.MINOR' for clean bump-on-deploy")

    # ------------------------------------------------------------- index.html refs
    def _local_refs_in_index(self):
        html = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
        refs = set()
        for m in re.finditer(r'(?:href|src)\s*=\s*["\']([^"\']+)["\']', html):
            url = m.group(1)
            if url.startswith(("http://", "https://", "data:", "#", "mailto:")):
                continue
            refs.add(url)
        return refs

    def test_no_broken_relative_references_in_index(self):
        refs = self._local_refs_in_index()
        self.assertTrue(refs, "expected the index to reference local css/js/manifest")
        for ref in refs:
            path = "/" + ref.lstrip("/")
            r = self._get(path)
            self.assertLess(r.status_code, 400, f"index.html reference '{ref}' -> {r.status_code}")

    # ------------------------------------------------------------- path safety
    def test_unintended_files_not_exposed(self):
        for path in ["/README.md", "/.env", "/../.env", "/.gitignore",
                     "/service-worker.js.map", "/css/../.env"]:
            r = self.client.get(path, follow_redirects=False)
            self.assertNotEqual(r.status_code, 200, f"{path} must not be served")
            self.assertNotIn("MAP_KEY", r.text)
            self.assertNotIn("SECRET", r.text.upper() if r.text else "")

    def test_api_health_still_reachable_alongside_static(self):
        r = self._get("/api/health")
        self.assertEqual(r.status_code, 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
