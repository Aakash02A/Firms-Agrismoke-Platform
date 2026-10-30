"""
AgriSmoke AI - Database Initializer & Seeder
Creates and populates SQLite database with calibrated Indo-Gangetic airshed datasets.
"""

import sqlite3
import json
import os
from pathlib import Path

DB_DIR = Path(__file__).resolve().parent
DB_PATH = DB_DIR / "agri_smoke.db"
SCHEMA_PATH = DB_DIR / "schema.sql"

def get_db_connection():
    """Returns SQLite database connection with row factory enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_database():
    print(f"Initializing AgriSmoke AI SQLite database at: {DB_PATH}")
    
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.executescript(schema_sql)
    conn.commit()

    # 1. Seed Monitoring Stations
    stations = [
        ("del_anand_vihar", "Anand Vihar, Delhi", "Urban / Traffic Inter-State Hub", 28.6508, 77.3152, 442, "Severe", 312.0, 486.0, 39.0, "up"),
        ("del_punjabi_bagh", "Punjabi Bagh, West Delhi", "Urban Residential / Arterial", 28.6740, 77.1310, 395, "Very Poor", 248.5, 398.0, 36.0, "up"),
        ("del_mandir_marg", "Mandir Marg, Central Delhi", "Urban Institutional", 28.6364, 77.1996, 348, "Very Poor", 210.0, 340.0, 31.0, "stable"),
        ("del_rk_puram", "R.K. Puram, South Delhi", "Urban Residential", 28.5660, 77.1767, 372, "Very Poor", 228.0, 365.0, 33.0, "up"),
        ("del_igi_airport", "IGI Airport T3, Delhi", "Commercial / Transport", 28.5562, 77.1000, 335, "Very Poor", 198.0, 315.0, 30.0, "stable"),
        ("del_bawana", "Bawana, North-West Delhi", "Industrial / Upwind Inflow", 28.7762, 77.0511, 468, "Severe", 345.0, 512.0, 44.0, "up"),
        ("noida_sec62", "Sector 62, Noida (UP)", "Suburban Commercial / IT", 28.6272, 77.3725, 388, "Very Poor", 240.0, 382.0, 35.0, "up"),
        ("ggn_teri_gram", "Teri Gram, Gurugram (Haryana)", "Semi-Urban / South Inflow", 28.4289, 77.1557, 340, "Very Poor", 204.0, 332.0, 29.0, "stable"),
        ("faridabad_sec16", "Sector 16A, Faridabad (Haryana)", "Industrial / Suburban", 28.4112, 77.3178, 378, "Very Poor", 232.0, 374.0, 32.0, "up")
    ]
    cursor.executemany("""
        INSERT OR REPLACE INTO monitoring_stations 
        (id, name, type, lat, lng, aqi, category, pm25, pm10, parali_pct, trend)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, stations)

    # 2. Seed Fire Hotspots (Thermal VIIRS/MODIS anomalies)
    hotspots = [
        ("fire_sangrur_1", "Sangrur", "Punjab", 30.2458, 75.8421, 384, 42.8, "High Density Cluster", "82% Harvested", "98% (VIIRS High)", "High"),
        ("fire_firozpur_1", "Firozpur", "Punjab", 30.9237, 74.6122, 295, 38.4, "Intense Burning", "78% Harvested", "95%", "High"),
        ("fire_tarn_taran_1", "Tarn Taran", "Punjab", 31.4519, 74.9282, 218, 35.1, "Moderate-High Density", "85% Harvested", "94%", "Moderate"),
        ("fire_bathinda_1", "Bathinda", "Punjab", 30.2110, 74.9455, 186, 31.2, "Active Cluster", "74% Harvested", "92%", "Moderate"),
        ("fire_amritsar_1", "Amritsar", "Punjab", 31.6340, 74.8723, 142, 29.5, "Scattered Fires", "90% Harvested", "91%", "Moderate"),
        ("fire_ludhiana_1", "Ludhiana", "Punjab", 30.9010, 75.8573, 154, 33.7, "Active Perimeter", "80% Harvested", "93%", "Moderate"),
        ("fire_fatehabad_1", "Fatehabad", "Haryana", 29.5140, 75.4542, 112, 28.0, "Active Burning", "84% Harvested", "90%", "Moderate"),
        ("fire_kaithal_1", "Kaithal", "Haryana", 29.8015, 76.3996, 96, 26.4, "Moderate Cluster", "88% Harvested", "89%", "Moderate"),
        ("fire_karnal_1", "Karnal", "Haryana", 29.6857, 76.9905, 65, 22.3, "Localized Fires", "91% Harvested", "87%", "Low-Moderate"),
        ("fire_jind_1", "Jind", "Haryana", 29.3140, 76.3150, 52, 20.1, "Scattered Fires", "86% Harvested", "85%", "Low")
    ]
    cursor.executemany("""
        INSERT OR REPLACE INTO fire_hotspots 
        (id, district, state, lat, lng, fire_count, avg_frp, status, harvest_progress, confidence, smoke_intensity)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, hotspots)

    # 3. Seed Weekly Trends (Past 7 Days)
    weekly = [
        ("Oct 21", 242, 620, 145.0, 18.0, "Stage II"),
        ("Oct 22", 278, 840, 168.0, 22.0, "Stage II"),
        ("Oct 23", 315, 1120, 194.0, 26.0, "Stage III"),
        ("Oct 24", 342, 1390, 212.0, 30.0, "Stage III"),
        ("Oct 25", 365, 1540, 225.0, 32.0, "Stage III"),
        ("Oct 26", 378, 1610, 232.0, 33.0, "Stage III"),
        ("Oct 27 (Today)", 382, 1684, 236.4, 34.6, "Stage III")
    ]
    cursor.execute("DELETE FROM weekly_trends")
    cursor.executemany("""
        INSERT INTO weekly_trends (day_label, aqi, fires, pm25, stubble_pct, grap_stage)
        VALUES (?, ?, ?, ?, ?, ?)
    """, weekly)

    # 4. Seed District Fire Counts
    districts = [
        ("Sangrur", 384, "Punjab"),
        ("Firozpur", 295, "Punjab"),
        ("Tarn Taran", 218, "Punjab"),
        ("Bathinda", 186, "Punjab"),
        ("Ludhiana", 154, "Punjab"),
        ("Amritsar", 142, "Punjab"),
        ("Fatehabad", 112, "Haryana"),
        ("Kaithal", 96, "Haryana"),
        ("Karnal", 65, "Haryana"),
        ("Jind", 52, "Haryana")
    ]
    cursor.executemany("""
        INSERT OR REPLACE INTO district_fire_counts (district, fires, state)
        VALUES (?, ?, ?)
    """, districts)

    # 5. Seed GRAP Stages
    grap_data = [
        (
            "Stage I",
            "Poor (AQI 201 - 300)",
            "201-300",
            0,
            None,
            json.dumps([
                "Strict enforcement of dust control at construction sites > 500 sq.m",
                "Periodic mechanized road sweeping and water sprinkling",
                "Strict checks on polluting vehicles and non-destined commercial trucks",
                "Ban on open burning of municipal solid waste and biomass"
            ])
        ),
        (
            "Stage II",
            "Very Poor (AQI 301 - 400)",
            "301-400",
            1,
            None,
            json.dumps([
                "Daily water sprinkling along with dust suppressants on major transit corridors",
                "Enhanced parking fees to discourage private transport usage",
                "Augment CNG/electric bus and metro services with higher frequency",
                "Uninterrupted power supply to prevent diesel generator (DG) usage"
            ])
        ),
        (
            "Stage III",
            "Severe (AQI 401 - 450)",
            "401-450",
            0,
            "Forecasted threshold entry expected between 18:00 - 22:00 IST today",
            json.dumps([
                "Strict ban on non-essential construction and demolition activities",
                "Prohibition on plying of BS-III petrol and BS-IV diesel 4-wheelers in Delhi-NCR",
                "Closure of stone crushers and mining activities across NCR",
                "States may discontinue physical classes for children up to Class V"
            ])
        ),
        (
            "Stage IV",
            "Severe+ / Emergency (AQI > 450)",
            ">450",
            0,
            None,
            json.dumps([
                "Ban on entry of non-electric / non-CNG trucks into Delhi (except essential commodities)",
                "Prohibition on running of commercial diesel light goods vehicles registered outside Delhi",
                "Closure of all construction and public project development",
                "Online mode for educational institutions (Classes VI - IX and XI)",
                "Work from home for 50% staff in public and private offices"
            ])
        )
    ]
    cursor.executemany("""
        INSERT OR REPLACE INTO grap_stages (stage, title, aqi_range, is_active, upcoming_notice, actions_json)
        VALUES (?, ?, ?, ?, ?, ?)
    """, grap_data)

    # 6. Seed Early Warning Alerts
    alerts = [
        (
            "alt_01",
            "CRITICAL",
            "Severe Smog Influx",
            "10:15 IST",
            "North-Westerly Wind Vector Transporting Dense Stubble Plume to NCR",
            "Thermal satellite telemetry shows 1,684 active fires across Punjab & Haryana. North-westerly winds (11.5 km/h) combined with lowering nocturnal boundary layer (<250m) are projected to push Delhi AQI past 440 by midnight.",
            "Enforce GRAP Stage III preemptive bans on polluting vehicles; advise vulnerable populations to remain indoors."
        ),
        (
            "alt_02",
            "WARNING",
            "Boundary Layer Trapping",
            "09:40 IST",
            "Severe Temperature Inversion & Calm Surface Winds Expected Tonight",
            "Mixing height expected to compress to 175m at 04:00 IST. Pollutants from agricultural burning and vehicular emissions will remain trapped near ground level.",
            "Deploy mechanized mist sprayers and anti-smog guns across 13 identified NCR hotspots."
        ),
        (
            "alt_03",
            "ADVISORY",
            "Public Health Warning",
            "08:00 IST",
            "High Particulate PM2.5 Exposure Advisory for High-Risk Demographics",
            "Ambient PM2.5 levels exceed 230 µg/m³ (approx 15 times the WHO safe guideline). Asthma patients and elderly citizens must avoid outdoor exercise.",
            "Wear certified N95 masks if outdoors; operate indoor HEPA purifiers in closed rooms."
        )
    ]
    cursor.executemany("""
        INSERT OR REPLACE INTO early_warning_alerts (id, level, alert_type, timestamp_str, title, detail, action_required)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, alerts)

    # 7. Seed Default Threshold Settings
    cursor.execute("""
        INSERT OR REPLACE INTO custom_thresholds (id, aqi_threshold, fires_threshold)
        VALUES (1, 400, 2000)
    """)

    # 8. Seed Geographic Districts with authentic coordinates for spatial filtering
    districts_geo = [
        ("PB_SANGRUR", "Sangrur", "Punjab", 30.2458, 75.8421, 29.85, 30.65, 75.50, 76.20, 3610.0, "agricultural"),
        ("PB_FIROZPUR", "Firozpur", "Punjab", 30.9237, 74.6122, 30.50, 31.35, 74.20, 75.10, 2190.0, "agricultural"),
        ("PB_TARN_TARAN", "Tarn Taran", "Punjab", 31.4519, 74.9282, 31.15, 31.75, 74.60, 75.25, 2414.0, "agricultural"),
        ("PB_BATHINDA", "Bathinda", "Punjab", 30.2110, 74.9455, 29.80, 30.60, 74.60, 75.35, 3385.0, "agricultural"),
        ("PB_AMRITSAR", "Amritsar", "Punjab", 31.6340, 74.8723, 31.40, 32.05, 74.50, 75.30, 2683.0, "agricultural"),
        ("PB_LUDHIANA", "Ludhiana", "Punjab", 30.9010, 75.8573, 30.60, 31.15, 75.40, 76.30, 3765.0, "agricultural"),
        ("PB_PATIALA", "Patiala", "Punjab", 30.3398, 76.3869, 30.00, 30.65, 76.05, 76.80, 3218.0, "agricultural"),
        ("PB_MANSA", "Mansa", "Punjab", 29.9880, 75.3900, 29.70, 30.25, 75.15, 75.75, 2171.0, "agricultural"),
        ("PB_MOGA", "Moga", "Punjab", 30.8165, 75.1715, 30.55, 31.05, 74.90, 75.45, 2216.0, "agricultural"),
        ("HR_FATEHABAD", "Fatehabad", "Haryana", 29.5140, 75.4542, 29.30, 29.85, 75.20, 75.90, 2538.0, "agricultural"),
        ("HR_KAITHAL", "Kaithal", "Haryana", 29.8015, 76.3996, 29.55, 30.10, 76.15, 76.75, 2317.0, "agricultural"),
        ("HR_KARNAL", "Karnal", "Haryana", 29.6857, 76.9905, 29.45, 29.98, 76.70, 77.25, 2520.0, "agricultural"),
        ("HR_JIND", "Jind", "Haryana", 29.3140, 76.3150, 29.05, 29.65, 75.90, 76.70, 2702.0, "agricultural"),
        ("HR_SIRSA", "Sirsa", "Haryana", 29.5349, 75.0298, 29.20, 29.95, 74.50, 75.45, 4277.0, "agricultural"),
        ("HR_KURUKSHETRA", "Kurukshetra", "Haryana", 29.9695, 76.8783, 29.80, 30.20, 76.60, 77.15, 1530.0, "agricultural"),
        ("DL_NORTH_WEST", "North West Delhi", "Delhi", 28.7762, 77.0511, 28.68, 28.88, 76.95, 77.18, 442.0, "urban"),
        ("DL_EAST", "East Delhi", "Delhi", 28.6508, 77.3152, 28.58, 28.72, 77.25, 77.36, 64.0, "urban"),
        ("DL_CENTRAL", "Central Delhi", "Delhi", 28.6364, 77.1996, 28.60, 28.68, 77.17, 77.24, 25.0, "urban"),
        ("UP_NOIDA", "Gautam Buddha Nagar", "Uttar Pradesh", 28.5355, 77.3910, 28.25, 28.70, 77.30, 77.70, 1442.0, "urban"),
        ("UP_GHAZIABAD", "Ghaziabad", "Uttar Pradesh", 28.6692, 77.4538, 28.55, 28.85, 77.28, 77.65, 1179.0, "urban")
    ]
    cursor.executemany("""
        INSERT OR REPLACE INTO districts
        (id, name, state, centroid_lat, centroid_lng, min_lat, max_lat, min_lng, max_lng, area_sq_km, primary_land_use)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, districts_geo)

    # 9. Seed Data Provider Status
    providers = [
        ("NASA_FIRMS", "NASA Fire Information for Resource Management System", "unconfigured", "VIIRS_NOAA20_NRT", None, None, 0, 0, 0, None, None, 0),
        ("CPCB", "Central Pollution Control Board (CAAQMS)", "operational", "DELHI_NCR_STATIONS", None, None, 1, 1, 0, None, 30, 9),
        ("OPEN_METEO", "Open-Meteo High-Resolution Atmospheric Wind & PBL", "operational", "GLOBAL_MET", None, None, 1, 1, 0, None, 60, 24)
    ]
    cursor.executemany("""
        INSERT OR REPLACE INTO data_provider_status
        (provider_id, name, status, selected_dataset, last_attempt, last_success, total_syncs, successful_syncs, failed_syncs, last_error, freshness_minutes, records_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, providers)

    conn.commit()
    conn.close()
    print("Database initialization complete with sample calibrated records.")

if __name__ == "__main__":
    init_database()

