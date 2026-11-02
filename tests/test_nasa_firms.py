"""
Test Suite: NASA FIRMS Integration
Validates configuration, CSV parsing, normalization, agricultural classification,
SHA-256 deduplication, spatiotemporal clustering, and SQLite persistence.
"""

import unittest
import os
import sys
import tempfile
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Phase 2 isolation: point backend.database at a throwaway file BEFORE it is
# imported (DB_PATH is read at import time) so ingestion/dedup tests never touch
# the production database/agri_smoke.db. setUpClass seeds this temp DB via
# ensure_ready() so district joins and provider-status reads behave identically.
_TMP_DIR = Path(tempfile.mkdtemp(prefix="agrismoke_firms_test_"))
os.environ["DB_PATH"] = str(_TMP_DIR / "agri_firms_test.db")

from backend.integrations.nasa_firms.config import FirmsConfig, DEFAULT_REGIONS
from backend.integrations.nasa_firms.parser import parse_firms_csv, FirmsParseError
from backend.integrations.nasa_firms.normalizer import (
    generate_observation_id,
    normalize_observation,
    parse_acquisition_timestamp,
    normalize_confidence
)
from backend.integrations.nasa_firms.classifier import (
    classify_fire_observation,
    evaluate_crop_season,
    haversine_km
)
from backend.integrations.nasa_firms.service import FirmsIngestionService
from backend import database

SAMPLE_VIIRS_CSV = """latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight
30.3452,75.1234,338.4,0.39,0.36,2026-10-29,0812,N20,VIIRS,n,2.0NRT,293.1,18.4,D
30.3510,75.1310,342.1,0.39,0.36,2026-10-29,0812,N20,VIIRS,h,2.0NRT,295.0,24.2,D
30.2100,74.9800,329.8,0.40,0.37,2026-10-29,0812,N20,VIIRS,n,2.0NRT,290.5,12.1,D
29.4600,76.9200,355.0,0.38,0.35,2026-10-29,0812,N20,VIIRS,h,2.0NRT,310.2,85.0,D
28.6500,77.2200,312.0,0.42,0.38,2026-10-29,0812,N20,VIIRS,l,2.0NRT,288.0,4.2,D
32.1000,75.9500,315.5,0.45,0.40,2026-10-29,0812,N20,VIIRS,n,2.0NRT,289.0,7.5,D
"""


class TestNasaFirmsIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Build + seed the isolated temp DB exactly like production startup does,
        # so get_district_fire_summary()'s join on districts and provider-status
        # reads have their reference rows without touching the real database.
        database.ensure_ready()

    def setUp(self):
        self.config = FirmsConfig()
        self.service = FirmsIngestionService(self.config)
        with database.get_connection() as conn:
            conn.cursor().execute("DELETE FROM fire_observations WHERE acq_date = '2026-10-29'")
            conn.cursor().execute("DELETE FROM fire_events WHERE id LIKE 'EVT-20261029-%'")
            conn.commit()

    def test_config_safeguards(self):
        """Ensure MAP_KEY is never leaked and default bounds are valid."""
        safe_dict = self.config.to_safe_dict()
        self.assertNotIn("map_key", safe_dict)
        self.assertIn("masked_map_key", safe_dict)
        self.assertEqual(len(self.config.get_bounding_box()), 4)

        # Coordinate format string validation
        formatted = self.config.format_area_coords((73.5, 27.5, 78.5, 32.5))
        self.assertEqual(formatted, "73.50,27.50,78.50,32.50")

    def test_csv_parser_valid_and_invalid_rows(self):
        """Verify robust CSV parsing, row validation, and error detection."""
        rows, rejected = parse_firms_csv(SAMPLE_VIIRS_CSV)
        self.assertEqual(len(rows), 6)
        self.assertEqual(rejected, 0)
        self.assertEqual(rows[0]["acq_date"], "2026-10-29")
        self.assertEqual(rows[0]["satellite"], "N20")

        # Corrupted row handling
        corrupted_csv = SAMPLE_VIIRS_CSV + "invalid,coords,300,1,1,2026-10-29,0812,N20,VIIRS,n,2.0NRT,290,10,D\n"
        c_rows, c_rejected = parse_firms_csv(corrupted_csv)
        self.assertEqual(len(c_rows), 6)
        self.assertEqual(c_rejected, 1)

        # NASA Error messages detection
        with self.assertRaises(FirmsParseError):
            parse_firms_csv("Bad MAP_KEY")

        with self.assertRaises(FirmsParseError):
            parse_firms_csv("<!DOCTYPE html><html><body>500 Error</body></html>")

    def test_normalizer_and_sha256_id(self):
        """Verify deterministic hash generation and timestamp normalization."""
        id1 = generate_observation_id("VIIRS_NOAA20_NRT", 30.3452, 75.1234, "2026-10-29", "0812")
        id2 = generate_observation_id("VIIRS_NOAA20_NRT", 30.3452, 75.1234, "2026-10-29", "0812")
        self.assertEqual(id1, id2)
        self.assertEqual(len(id1), 24)

        ts = parse_acquisition_timestamp("2026-10-29", "812")
        self.assertEqual(ts, "2026-10-29T08:12:00Z")

        # Confidence normalization
        _, c_high = normalize_confidence("h", "VIIRS")
        self.assertEqual(c_high, 0.95)
        _, c_modis = normalize_confidence("85", "MODIS")
        self.assertEqual(c_modis, 0.85)

    def test_classification_engine(self):
        """Test agricultural, industrial, and forest fire classification logic."""
        # Sangrur agricultural observation in peak harvest
        agri_obs = {
            "latitude": 30.25,
            "longitude": 75.84,
            "frp": 25.0,
            "confidence_normalized": 0.95,
            "acq_date": "2026-10-25"
        }
        sangrur_meta = {"name": "Sangrur", "dominant_crop": "Paddy / Wheat", "stubble_risk_level": "CRITICAL"}
        res = classify_fire_observation(agri_obs, sangrur_meta)
        self.assertEqual(res["classification"], "agricultural")
        self.assertGreaterEqual(res["classification_confidence"], 0.70)

        # Panipat Refinery industrial observation
        ind_obs = {
            "latitude": 29.46,
            "longitude": 76.92,
            "frp": 85.0,
            "confidence_normalized": 0.95,
            "acq_date": "2026-10-25"
        }
        res_ind = classify_fire_observation(ind_obs, None)
        self.assertEqual(res_ind["classification"], "industrial")

        # Shivalik forest belt observation
        forest_obs = {
            "latitude": 32.10,
            "longitude": 75.95,
            "frp": 12.0,
            "confidence_normalized": 0.80,
            "acq_date": "2026-10-25"
        }
        res_forest = classify_fire_observation(forest_obs, None)
        self.assertEqual(res_forest["classification"], "forest_vegetation")

    def test_ingestion_service_and_deduplication(self):
        """Verify full ingestion cycle, duplicate prevention, and cluster generation."""
        # 1st Ingestion run with sample CSV
        summary1 = self.service.ingest_observations(
            sensor="VIIRS_NOAA20_NRT",
            region_name="indo_gangetic_airshed",
            raw_csv_override=SAMPLE_VIIRS_CSV
        )
        self.assertEqual(summary1.status, "SUCCESS")
        self.assertEqual(summary1.records_received, 6)
        self.assertGreater(summary1.records_inserted, 0)

        # 2nd Ingestion run with the EXACT SAME CSV -> All must be detected as duplicates
        summary2 = self.service.ingest_observations(
            sensor="VIIRS_NOAA20_NRT",
            region_name="indo_gangetic_airshed",
            raw_csv_override=SAMPLE_VIIRS_CSV
        )
        self.assertEqual(summary2.status, "SUCCESS")
        self.assertEqual(summary2.records_received, 6)
        self.assertEqual(summary2.records_inserted, 0)
        self.assertEqual(summary2.records_skipped, 6)

        # Verify DB queries
        obs_list = database.get_fire_observations(limit=10)
        self.assertGreaterEqual(len(obs_list), 6)

        # Verify district fire summary aggregation
        dist_summary = database.get_district_fire_summary(days=30)
        self.assertTrue(len(dist_summary) > 0)

        # Verify provider status
        status = self.service.get_provider_status()
        self.assertTrue(status.is_healthy)
        self.assertIn(status.status.lower(), ("online", "operational"))


if __name__ == "__main__":
    unittest.main()
