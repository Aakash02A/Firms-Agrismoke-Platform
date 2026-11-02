"""
Test Suite: Secret Leakage & Redaction (Phase 1 hardening)
Regression tests for every identified credential-leak path:
  1. NASA FIRMS key leaking via requests exception messages (client).
  2. NASA FIRMS key leaking via persisted / logged ingestion errors (service).
  3. Redis credentials leaking via cache connection logs (mask_url).
  4. Raw error message exposure on the public provider-status response (read scrub).

These tests DO NOT touch the real database: every DB writer is mocked, so the
production/local SQLite file is never mutated.
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

from backend.security import redact_secrets, mask_url, safe_error
from backend.integrations.nasa_firms.config import FirmsConfig
from backend.integrations.nasa_firms.client import NasaFirmsClient
from backend.integrations.nasa_firms.service import FirmsIngestionService
from backend.integrations.nasa_firms.exceptions import FirmsNetworkError, FirmsError

FAKE_KEY = "ABCD1234EFGH5678IJKL"  # 20 chars, >= 10 so is_configured is True
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
