"""
Diagnostic Test: Database Layer Verification
Tests SQLite connection, schema integrity, seeded records, and CRUD functions.
"""

import sys
import sqlite3
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "backend"))
import database as db

def test_database_layer():
    print("=== Test 2: Database Layer Verification ===")
    
    # 1. Connect to SQLite
    conn = db.get_connection()
    cursor = conn.cursor()
    
    # Verify tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}
    expected_tables = {
        "monitoring_stations", "fire_hotspots", "hourly_forecasts",
        "weekly_trends", "district_fire_counts", "grap_stages",
        "early_warning_alerts", "simulation_history", "custom_thresholds"
    }
    missing_tables = expected_tables - tables
    assert not missing_tables, f"Missing tables in SQLite: {missing_tables}"
    print(f"[PASS] All {len(expected_tables)} schema tables exist.")

    # 2. Verify monitoring stations
    stations = db.get_monitoring_stations()
    assert len(stations) == 9, f"Expected 9 stations, got {len(stations)}"
    for st in stations:
        assert "name" in st and "aqi" in st and "paraliPct" in st
        assert 0 <= st["aqi"] <= 999
        assert 0.0 <= st["paraliPct"] <= 100.0
    print(f"[PASS] Monitoring stations verified ({len(stations)} stations, camelCase mapped).")

    # 3. Verify fire hotspots
    hotspots = db.get_fire_hotspots()
    assert len(hotspots) == 10, f"Expected 10 hotspots, got {len(hotspots)}"
    for h in hotspots:
        assert "district" in h and "fireCount" in h and "avgFRP" in h
        assert h["fireCount"] > 0
    print(f"[PASS] Fire hotspots verified ({len(hotspots)} hotspots, camelCase mapped).")

    # 4. Verify weekly trends
    weekly = db.get_weekly_trends()
    assert len(weekly) == 7, f"Expected 7 weekly trend entries, got {len(weekly)}"
    print(f"[PASS] Weekly trends verified ({len(weekly)} records).")

    # 5. Verify district fire counts
    districts = db.get_district_fire_counts()
    assert len(districts) == 10, f"Expected 10 districts, got {len(districts)}"
    print(f"[PASS] District fire counts verified ({len(districts)} districts).")

    # 6. Verify GRAP stages
    grap = db.get_grap_stages()
    assert len(grap) == 4, f"Expected 4 GRAP stages, got {len(grap)}"
    print(f"[PASS] GRAP stages verified ({len(grap)} stages).")

    # 7. Verify Alerts
    alerts = db.get_early_warning_alerts()
    assert len(alerts) >= 3, f"Expected at least 3 alerts, got {len(alerts)}"
    print(f"[PASS] Early warning alerts verified ({len(alerts)} alerts).")

    # 8. Test simulation run recording
    test_params = {
        "fireCount": 2200, "windSpeed": 14.5, "windDirectionDeg": 310,
        "pblHeight": 350, "urbanBaselineAqi": 180,
        "bioDecomposerAdoption": 30, "happySeederAdoption": 35
    }
    test_pred = {
        "predictedAqi": 395, "totalPm25": 248.5, "totalPm10": 418.0,
        "paraliPct": 42.0, "grapStage": "Stage II",
        "mitigationSavings": {"aqiDrop": 50}
    }
    db.save_simulation_run(test_params, test_pred)
    cursor.execute("SELECT * FROM simulation_history ORDER BY id DESC LIMIT 1")
    last_run = cursor.fetchone()
    assert last_run["fire_count"] == 2200
    assert last_run["predicted_aqi"] == 395
    print("[PASS] Simulation record successfully persisted and retrieved.")

    # 9. Test custom thresholds
    updated_th = db.update_custom_thresholds(420, 2500)
    current_th = db.get_custom_thresholds()
    assert current_th["aqi"] == 420 and current_th["fires"] == 2500
    # Reset back to default
    db.update_custom_thresholds(400, 2000)
    print("[PASS] Custom thresholds update and retrieval verified.")

    conn.close()
    print("=== Database Layer: ALL TESTS PASSED! ===")

if __name__ == "__main__":
    test_database_layer()

