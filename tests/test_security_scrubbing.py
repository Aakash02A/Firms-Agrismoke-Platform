"""
Test Suite: Secret Leakage & Redaction (Phase 1 hardening)
Regression tests for every identified credential-leak path:
  1. NASA FIRMS key leaking via requests exception messages (client).
  2. NASA FIRMS key leaking via persisted / logged ingestion errors (service).
  3. Redis credentials leaking via cache connection logs (mask_url).
  4. Raw error message exposure on the public provider-status response (read scrub).
  5. Scheduler last_error leaking MAP_KEY / Redis password into logs and the
     public GET /api/v1/scheduler/status response.
  6. Global unhandled-exception handler echoing raw exception text / request
     URL (with credentials) back to clients.

These tests DO NOT touch the real database: every DB writer is mocked and
backend.main is imported with DB_PATH pointed at an isolated temp SQLite file,
so the production/local SQLite file is never mutated.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Isolate any DB access triggered by importing the FastAPI app: point DB_PATH
# at a throwaway temp file BEFORE backend.main is imported.
_TMP_DB = Path(tempfile.gettempdir()) / f"agri_smoke_sec_test_{os.getpid()}.db"
os.environ["DB_PATH"] = str(_TMP_DB)

import requests  # noqa: E402

from backend.security import redact_secrets, mask_url, safe_error, known_env_secrets
from backend.integrations.nasa_firms.config import FirmsConfig
from backend.integrations.nasa_firms.client import NasaFirmsClient
from backend.integrations.nasa_firms.service import FirmsIngestionService
from backend.integrations.nasa_firms.exceptions import FirmsNetworkError, FirmsError

FAKE_KEY = "ABCD1234EFGH5678IJKL"  # 20 chars, >= 10 so is_configured is True
FAKE_REDIS_URL = "redis://default:Sup3rS3cretPw@redis-host:6379/0"
URL_WITH_KEY = (
    f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{FAKE_KEY}/"
    "VIIRS_NOAA20_NRT/73.5,27.5,78.5,32.5/3"
)


def _config_with_key():
    cfg = FirmsConfig()
    cfg.map_key = FAKE_KEY  # simulate a configured key without reading env
    return cfg


class TestRedactionPrimitives(unittest.TestCase):
    def test_redacts_firms_key_literal_and_path(self):
        out = redact_secrets(URL_WITH_KEY, [FAKE_KEY])
        self.assertNotIn(FAKE_KEY, out)
        self.assertIn("/csv/***/", out)
        self.assertIn("firms.modaps.eosdis.nasa.gov", out)  # host preserved

    def test_masks_url_userinfo_credentials(self):
        out = mask_url("redis://user:s3cr3tpw@redis-host:6379/0")
        self.assertNotIn("s3cr3tpw", out)
        self.assertIn("redis://***@redis-host:6379/0", out)

    def test_mask_url_no_credentials_unchanged(self):
        url = "https://api.open-meteo.com/v1/forecast?latitude=28.6&longitude=77.2"
        self.assertEqual(mask_url(url), url)

    def test_safe_error_keeps_class_name_without_secret(self):
        err = requests.exceptions.ConnectionError(f"bad url {URL_WITH_KEY}")
        msg = safe_error(err, [FAKE_KEY])
        self.assertTrue(msg.startswith("ConnectionError"))
        self.assertNotIn(FAKE_KEY, msg)

    def test_none_passthrough(self):
        self.assertIsNone(redact_secrets(None))


class TestClientLeakPaths(unittest.TestCase):
    def test_connection_error_message_excludes_key(self):
        client = NasaFirmsClient(_config_with_key())
        with mock.patch.object(client.session, "get", side_effect=requests.exceptions.ConnectionError(URL_WITH_KEY)), \
             mock.patch("backend.integrations.nasa_firms.client.time.sleep"):
            with self.assertRaises(FirmsNetworkError) as ctx:
                client.get_area_observations_csv()
        self.assertNotIn(FAKE_KEY, str(ctx.exception))
        self.assertIn("ConnectionError", str(ctx.exception))  # diagnostic type kept

    def test_timeout_message_excludes_key(self):
        client = NasaFirmsClient(_config_with_key())
        with mock.patch.object(client.session, "get", side_effect=requests.exceptions.Timeout(URL_WITH_KEY)), \
             mock.patch("backend.integrations.nasa_firms.client.time.sleep"):
            with self.assertRaises(FirmsNetworkError) as ctx:
                client.get_area_observations_csv()
        self.assertNotIn(FAKE_KEY, str(ctx.exception))

    def test_unexpected_http_body_excludes_key(self):
        class FakeResp:
            status_code = 418
            text = f"Server error. Your MAP_KEY {FAKE_KEY} was rejected."

        client = NasaFirmsClient(_config_with_key())
        with mock.patch.object(client.session, "get", return_value=FakeResp()):
            with self.assertRaises(FirmsError) as ctx:
                client.get_area_observations_csv()
        self.assertNotIn(FAKE_KEY, str(ctx.exception))


class TestServiceIngestionLeak(unittest.TestCase):
    def test_failure_logs_persists_and_returns_scrubbed_message(self):
        cfg = _config_with_key()
        service = FirmsIngestionService(cfg)

        with mock.patch.object(
            service.client, "get_area_observations_csv",
            side_effect=requests.exceptions.ConnectionError(URL_WITH_KEY),
        ), mock.patch("backend.database.record_sync_job", return_value=1) as mock_sync, \
             mock.patch("backend.database.update_data_provider_status") as mock_status:

            with self.assertLogs("agri_smoke.firms.service", level="ERROR") as captured:
                summary = service.ingest_observations()

        # 1. Returned SyncSummary.message (exposed via POST /api/v1/firms/sync)
        self.assertNotIn(FAKE_KEY, summary.message)

        # 2. Persisted error messages
        for call in mock_sync.call_args_list:
            self.assertNotIn(FAKE_KEY, str(call.kwargs.get("error_message", "")))
        for call in mock_status.call_args_list:
            self.assertNotIn(FAKE_KEY, str(call.kwargs.get("error_message", "")))

        # 3. Logged traceback
        self.assertNotIn(FAKE_KEY, "\n".join(captured.output))


class TestProviderStatusReadScrub(unittest.TestCase):
    def test_last_error_message_scrubbed_on_read(self):
        service = FirmsIngestionService(_config_with_key())
        raw = {
            "status": "degraded",
            "is_healthy": 0,
            "last_sync_timestamp": None,
            "latest_data_timestamp": None,
            "total_records_ingested": 0,
            "consecutive_failures": 2,
            "last_error_message": f"Fetch failed for {URL_WITH_KEY}",
            "details": None,
        }
        with mock.patch("backend.database.get_data_provider_status", return_value=raw):
            resp = service.get_provider_status()
        self.assertNotIn(FAKE_KEY, resp.last_error_message or "")


class TestSchedulerErrorScrub(unittest.TestCase):
    """Regression: scheduler stored raw str(e) in last_error, which is logged
    and returned verbatim by the public GET /api/v1/scheduler/status endpoint.
    A requests exception echoing the FIRMS URL (path contains MAP_KEY) or the
    Redis URL (contains password) must be scrubbed before storage."""

    def _drive_one_pass(self, refresh_side_effect):
        """Run exactly one scheduler loop pass synchronously.

        The loop's inter-pass sleep is patched to stop the scheduler, so
        _run_loop() returns after a single deterministic iteration.
        """
        from backend.scheduler import IngestionScheduler
        sched = IngestionScheduler(firms_interval_seconds=10800, weather_interval_seconds=0)

        def _stop_after_pass(*_a, **_k):
            sched._running = False

        env = {"NASA_FIRMS_MAP_KEY": FAKE_KEY, "REDIS_URL": FAKE_REDIS_URL}
        with mock.patch.dict(os.environ, env, clear=False), \
             mock.patch("backend.integrations.weather.service.weather_service.refresh_cache",
                        side_effect=refresh_side_effect), \
             mock.patch("backend.integrations.nasa_firms.FirmsConfig") as firmcfg, \
             mock.patch("backend.scheduler.time.sleep", side_effect=_stop_after_pass):
            firmcfg.return_value.is_configured = False  # skip FIRMS branch, isolate weather branch
            sched._running = True
            sched._run_loop()
        return sched

    def test_weather_error_scrubbed_before_log_and_status(self):
        boom = requests.exceptions.ConnectionError(
            f"Redis cache flush failed against {FAKE_REDIS_URL} while syncing {URL_WITH_KEY}"
        )
        with self.assertLogs("agri_smoke.scheduler", level="WARNING") as captured:
            sched = self._drive_one_pass(boom)

        self.assertTrue(sched.last_error, "scheduler never recorded an error")
        # 1. Stored message -> returned verbatim by GET /api/v1/scheduler/status
        self.assertNotIn(FAKE_KEY, sched.last_error)
        self.assertNotIn("Sup3rS3cretPw", sched.last_error)
        # 2. Full status payload
        status = sched.get_status()
        self.assertNotIn(FAKE_KEY, str(status))
        self.assertNotIn("Sup3rS3cretPw", str(status))
        # 3. Logged line
        joined = "\n".join(captured.output)
        self.assertNotIn(FAKE_KEY, joined)
        self.assertNotIn("Sup3rS3cretPw", joined)
        # Diagnostic value preserved
        self.assertIn("Weather update error", sched.last_error)
        self.assertIn("ConnectionError", sched.last_error)

    def test_firms_sync_error_scrubbed_in_status(self):
        # Same leak path in the FIRMS branch of the scheduler loop.
        boom = requests.exceptions.ConnectionError(f"could not fetch {URL_WITH_KEY}")
        from backend.scheduler import IngestionScheduler
        sched = IngestionScheduler(firms_interval_seconds=0, weather_interval_seconds=999999)

        def _stop_after_pass(*_a, **_k):
            sched._running = False

        cfg_mock = mock.MagicMock()
        cfg_mock.is_configured = True
        env = {"NASA_FIRMS_MAP_KEY": FAKE_KEY, "REDIS_URL": FAKE_REDIS_URL}
        with mock.patch.dict(os.environ, env, clear=False), \
             mock.patch("backend.integrations.weather.service.weather_service.refresh_cache", return_value=mock.MagicMock()), \
             mock.patch("backend.integrations.nasa_firms.FirmsConfig", return_value=cfg_mock), \
             mock.patch("backend.integrations.nasa_firms.FirmsIngestionService") as svc, \
             mock.patch("backend.scheduler.time.sleep", side_effect=_stop_after_pass):
            svc.return_value.ingest_observations.side_effect = boom
            sched._running = True
            sched._run_loop()

        self.assertTrue(sched.last_error)
        self.assertIn("FIRMS sync error", sched.last_error)
        self.assertNotIn(FAKE_KEY, sched.last_error)
        self.assertNotIn(FAKE_KEY, str(sched.get_status()))


class TestUnhandledExceptionHandlerScrub(unittest.TestCase):
    """Regression: the global handler used logger.exception (rendering the raw
    traceback, whose final line is ``ExcType: <message>`` and can echo a
    credential-bearing URL) and, outside production, returned
    f"{type(exc).__name__}: {exc}" to the client.
    Both the response body and the logged traceback must be scrubbed."""

    def _build_request(self, url: str):
        from starlette.requests import Request
        import urllib.parse as up
        parsed = up.urlsplit(url)
        scope = {
            "type": "http",
            "method": "GET",
            "path": parsed.path or "/",
            "query_string": (parsed.query or "").encode(),
            "headers": [],
            "client": ("127.0.0.1", 55555),
            "server": ("testserver", 80),
            "scheme": parsed.scheme or "https",
            "root_path": "",
            "http_version": "1.1",
            "app": None,
        }
        return Request(scope)

    def _raise_and_handle(self, exc, is_production, url="https://app.example.com/api/boom"):
        """Invoke the handler with a *real* raised exception so it carries a
        traceback, exactly as FastAPI does in production."""
        import asyncio
        from backend.main import unhandled_exception_handler

        def _boom():
            raise exc

        with mock.patch("backend.main.config.is_production", is_production), \
             mock.patch.dict(os.environ, {"NASA_FIRMS_MAP_KEY": FAKE_KEY, "REDIS_URL": FAKE_REDIS_URL}, clear=False):
            req = self._build_request(url)
            try:
                _boom()
            except Exception as caught:
                return asyncio.run(unhandled_exception_handler(req, caught))
        self.fail("exception was not raised")  # pragma: no cover

    def test_response_body_never_contains_firms_key_in_dev(self):
        resp = self._raise_and_handle(
            requests.exceptions.ConnectionError(f"GET {URL_WITH_KEY} failed"), is_production=False)
        body = resp.body.decode()
        self.assertNotIn(FAKE_KEY, body)
        self.assertNotIn("Sup3rS3cretPw", body)
        self.assertIn("ConnectionError", body)  # class name kept for dev diagnostics

    def test_response_body_generic_in_production(self):
        resp = self._raise_and_handle(ValueError(f"bad config {FAKE_REDIS_URL}"), is_production=True)
        body = resp.body.decode()
        self.assertNotIn("Sup3rS3cretPw", body)
        self.assertNotIn(FAKE_REDIS_URL, body)
        self.assertIn("Internal server error", body)

    def test_logged_traceback_scrubs_firms_key_and_redis_password(self):
        """The rendered traceback ends with the raw exception message; it must be
        redacted before reaching the log."""
        with self.assertLogs("agri_smoke.api", level="ERROR") as captured:
            self._raise_and_handle(
                requests.exceptions.ConnectionError(f"GET {URL_WITH_KEY} failed"), is_production=False)
        joined = "\n".join(captured.output)
        self.assertNotIn(FAKE_KEY, joined)
        # Traceability preserved: still tells you what/where it failed
        self.assertIn("ConnectionError", joined)
        self.assertIn("firms.modaps.eosdis.nasa.gov", joined)

    def test_logged_traceback_scrubs_redis_password(self):
        with self.assertLogs("agri_smoke.api", level="ERROR") as captured:
            self._raise_and_handle(RuntimeError(f"connection lost to {FAKE_REDIS_URL}"), is_production=False)
        joined = "\n".join(captured.output)
        self.assertNotIn("Sup3rS3cretPw", joined)
        # REDIS_URL is a known env secret, so the whole connection string (incl.
        # host) is replaced; the exception type and frames stay for diagnosis.
        self.assertNotIn(FAKE_REDIS_URL, joined)
        self.assertIn("RuntimeError: connection lost to ***", joined)
        self.assertIn("Traceback (most recent call last)", joined)

    def test_logged_request_url_with_credentials_is_masked(self):
        leaky = f"https://app.example.com/api/boom?key={FAKE_KEY}"
        with self.assertLogs("agri_smoke.api", level="ERROR") as captured:
            self._raise_and_handle(ValueError("boom"), is_production=False, url=leaky)
        joined = "\n".join(captured.output)
        self.assertNotIn(FAKE_KEY, joined)


class TestKnownEnvSecrets(unittest.TestCase):
    def test_collects_configured_secret_env_values(self):
        env = {"NASA_FIRMS_MAP_KEY": FAKE_KEY, "REDIS_URL": FAKE_REDIS_URL, "DATABASE_URL": ""}
        with mock.patch.dict(os.environ, env, clear=False):
            secrets = known_env_secrets()
        self.assertIn(FAKE_KEY, secrets)
        self.assertIn(FAKE_REDIS_URL, secrets)

    def test_redact_with_env_literals_masks_password_and_key(self):
        raw = f"sync failed: {URL_WITH_KEY} cached via {FAKE_REDIS_URL}"
        env = {"NASA_FIRMS_MAP_KEY": FAKE_KEY, "REDIS_URL": FAKE_REDIS_URL}
        with mock.patch.dict(os.environ, env, clear=False):
            out = redact_secrets(raw, known_env_secrets())
        self.assertNotIn(FAKE_KEY, out)
        self.assertNotIn("Sup3rS3cretPw", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
