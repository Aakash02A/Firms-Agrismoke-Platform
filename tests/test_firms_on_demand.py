"""
Test Suite: On-Demand NASA FIRMS Live Snapshot (stateless public deployment)

Proves the Phase-5 stateless read path introduced for the Render Free tier:
  * FIRMS_ON_DEMAND defaults OFF (existing scheduler behavior untouched).
  * When enabled, live hotspots / district counts are aggregated from a real
    FIRMS CSV (reusing the tested client/parser/normalizer) WITHOUT writing to
    the database - the defining statelessness guarantee.
  * The fetch is cached by TTL and single-flighted, so visitor traffic does NOT
    translate into proportional NASA API calls (free-tier outbound safety).
  * Unconfigured MAP_KEY or a provider failure is fail-soft (empty result, no
    raise) so callers fall back to seeded reference data.

Isolation mirrors the Phase 4 suite: a throwaway SQLite file in a temp dir, and
the on_demand module's process-global cache is reset before/after each test. No
real network call is ever attempted - the client fetch is always patched.
"""

import os
import sys
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend import database as db                                   # noqa: E402
from backend.app_config import AppConfig                            # noqa: E402
from backend.integrations.nasa_firms import on_demand              # noqa: E402
from backend.integrations.nasa_firms.client import NasaFirmsClient  # noqa: E402

FAKE_KEY = "ABCD1234EFGH5678IJKL"          # >=10 chars -> FirmsConfig.is_configured True

# A tiny but realistic VIIRS CSV: two detections near Sangrur, one near Firozpur.
SAMPLE_CSV = (
    "latitude,longitude,acq_date,acq_time,confidence,frp,satellite,instrument\n"
    "30.2458,75.8421,2026-01-01,0815,n,10.0,NOAA-20,VIIRS\n"
    "30.2500,75.8500,2026-01-01,0830,n,20.0,NOAA-20,VIIRS\n"
    "30.9237,74.6122,2026-01-01,0900,h,5.0,NOAA-20,VIIRS\n"
)


class OnDemandTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="agrismoke_ondemand_"))
        self.db_path = self.tmp / "agri_smoke_test.db"

        self._saved = {}
        for key in ("NASA_FIRMS_MAP_KEY", "FIRMS_ON_DEMAND", "FIRMS_ON_DEMAND_TTL_SECONDS"):
            self._saved[key] = os.environ.get(key)
        os.environ["DB_PATH"] = str(self.db_path)
        os.environ.pop("NASA_FIRMS_MAP_KEY", None)

        db.DB_PATH = self.db_path
        db._wal_active = None
        self._reset_cache()

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._reset_cache()
        db._wal_active = None
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _reset_cache(self):
        on_demand._data = None
        on_demand._expires_at = 0.0

    def boot_db(self):
        db.ensure_ready()

    def obs_count(self):
        with db.get_connection() as conn:
            return conn.execute("SELECT COUNT(*) FROM fire_observations").fetchone()[0]


class TestConfigDefault(OnDemandTestCase):
    def test_on_demand_defaults_to_disabled(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            cfg = AppConfig()
        self.assertFalse(cfg.firms_on_demand)
        self.assertEqual(cfg.firms_on_demand_ttl, 900)

    def test_on_demand_env_enables_it(self):
        with mock.patch.dict(os.environ, {"FIRMS_ON_DEMAND": "true"}):
            cfg = AppConfig()
        self.assertTrue(cfg.firms_on_demand)


class TestUnconfiguredAndFailSoft(OnDemandTestCase):
    def test_unconfigured_returns_empty_without_network(self):
        # No MAP_KEY -> is_configured False -> empty snapshot, client never called.
        self.boot_db()
        with mock.patch.object(NasaFirmsClient, "get_area_observations_csv",
                               side_effect=AssertionError("network must not be used")):
            self.assertEqual(on_demand.get_live_hotspots(), [])
            self.assertEqual(on_demand.get_live_district_counts(), [])

    def test_provider_error_is_fail_soft(self):
        os.environ["NASA_FIRMS_MAP_KEY"] = FAKE_KEY
        self.boot_db()
        with mock.patch.object(NasaFirmsClient, "get_area_observations_csv",
                               side_effect=RuntimeError("boom")):
            # No prior cache -> empty, and it must NOT raise into the handler.
            self.assertEqual(on_demand.get_live_hotspots(), [])


class TestAggregation(OnDemandTestCase):
    def test_snapshot_aggregates_without_touching_the_database(self):
        os.environ["NASA_FIRMS_MAP_KEY"] = FAKE_KEY
        self.boot_db()
        self.assertEqual(self.obs_count(), 0)

        with mock.patch.object(NasaFirmsClient, "get_area_observations_csv",
                               return_value=SAMPLE_CSV):
            hotspots = on_demand.get_live_hotspots()
            counts = on_demand.get_live_district_counts()

        self.assertTrue(hotspots, "expected at least one aggregated district")
        # Shapes mirror db.get_live_fire_hotspots() so the frontend needs no changes.
        top = hotspots[0]
        for field in ("id", "district", "state", "lat", "lng", "fire_count",
                      "avg_frp", "smoke_intensity", "fireCount", "avgFRP", "live"):
            self.assertIn(field, top)
        self.assertTrue(top["live"])
        self.assertEqual(top["source"], "NASA_FIRMS_ON_DEMAND")
        # Sorted newest-count first.
        self.assertGreaterEqual(hotspots[0]["fire_count"], hotspots[-1]["fire_count"])
        # Total detections across districts == rows in the CSV (3).
        self.assertEqual(sum(c["fires"] for c in counts), 3)

        # The statelessness guarantee: the live read path wrote NOTHING to the DB.
        self.assertEqual(self.obs_count(), 0)

    def test_point_level_observations_for_the_map(self):
        # The map reads /api/v1/firms/observations; on a stateless deploy the DB is
        # empty, so on_demand must supply point-level, DB-shaped LIVE rows.
        os.environ["NASA_FIRMS_MAP_KEY"] = FAKE_KEY
        self.boot_db()
        self.assertEqual(self.obs_count(), 0)

        with mock.patch.object(NasaFirmsClient, "get_area_observations_csv",
                               return_value=SAMPLE_CSV):
            obs = on_demand.get_live_observations(limit=1000)

        self.assertEqual(len(obs), 3, "one row per CSV detection")
        for field in ("id", "latitude", "longitude", "frp", "classification",
                      "confidence_normalized", "acquisition_timestamp"):
            self.assertIn(field, obs[0])
        self.assertTrue(obs[0]["live"])
        self.assertEqual(obs[0]["source"], "NASA_FIRMS_ON_DEMAND")
        # Still stateless: point-level path wrote nothing to fire_observations.
        self.assertEqual(self.obs_count(), 0)

    def test_unconfigured_observations_empty(self):
        self.boot_db()
        with mock.patch.object(NasaFirmsClient, "get_area_observations_csv",
                               side_effect=AssertionError("network must not be used")):
            self.assertEqual(on_demand.get_live_observations(), [])


class TestTTLCacheIsTrafficIndependent(OnDemandTestCase):
    def test_many_requests_trigger_at_most_one_fetch_per_ttl(self):
        os.environ["NASA_FIRMS_MAP_KEY"] = FAKE_KEY
        os.environ["FIRMS_ON_DEMAND_TTL_SECONDS"] = "900"
        self.boot_db()

        calls = {"n": 0}

        def fake_fetch(*args, **kwargs):
            calls["n"] += 1
            return SAMPLE_CSV

        with mock.patch.object(NasaFirmsClient, "get_area_observations_csv", side_effect=fake_fetch):
            for _ in range(20):                     # simulate heavy visitor traffic
                on_demand.get_live_hotspots()

        self.assertEqual(calls["n"], 1, "NASA must be called at most once within the TTL window")

    def test_expired_cache_refetches(self):
        os.environ["NASA_FIRMS_MAP_KEY"] = FAKE_KEY
        self.boot_db()
        calls = {"n": 0}

        def fake_fetch(*args, **kwargs):
            calls["n"] += 1
            return SAMPLE_CSV

        with mock.patch.object(NasaFirmsClient, "get_area_observations_csv", side_effect=fake_fetch):
            on_demand.get_live_hotspots()
            on_demand._expires_at = 0.0             # force TTL expiry
            on_demand.get_live_hotspots()

        self.assertEqual(calls["n"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
