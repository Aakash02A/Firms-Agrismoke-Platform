-- AgriSmoke AI - SQLite Database Schema
-- Indo-Gangetic Airshed Crop-Burning & Urban Air Quality Prediction System

PRAGMA foreign_keys = ON;

-- 1. Monitoring Stations Table
CREATE TABLE IF NOT EXISTS monitoring_stations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    lat REAL NOT NULL,
    lng REAL NOT NULL,
    aqi INTEGER NOT NULL,
    category TEXT NOT NULL,
    pm25 REAL NOT NULL,
    pm10 REAL NOT NULL,
    parali_pct REAL NOT NULL,
    trend TEXT DEFAULT 'stable',
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Active Fire Hotspots (Thermal Anomalies from Satellite Sensors)
CREATE TABLE IF NOT EXISTS fire_hotspots (
    id TEXT PRIMARY KEY,
    district TEXT NOT NULL,
    state TEXT NOT NULL,
    lat REAL NOT NULL,
    lng REAL NOT NULL,
    fire_count INTEGER NOT NULL,
    avg_frp REAL NOT NULL,
    status TEXT NOT NULL,
    harvest_progress TEXT NOT NULL,
    confidence TEXT NOT NULL,
    smoke_intensity TEXT NOT NULL,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Hourly Forecasts (Diurnal Cycle Projections)
CREATE TABLE IF NOT EXISTS hourly_forecasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hour_str TEXT NOT NULL,
    hour_num INTEGER NOT NULL,
    aqi INTEGER NOT NULL,
    pm25 REAL NOT NULL,
    stubble_pct REAL NOT NULL,
    wind_speed REAL NOT NULL,
    pbl_height INTEGER NOT NULL,
    category TEXT NOT NULL,
    color TEXT NOT NULL,
    forecast_date DATE DEFAULT (DATE('now'))
);

-- 4. 7-Day Air Quality & Stubble Trend History
CREATE TABLE IF NOT EXISTS weekly_trends (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day_label TEXT NOT NULL,
    aqi INTEGER NOT NULL,
    fires INTEGER NOT NULL,
    pm25 REAL NOT NULL,
    stubble_pct REAL NOT NULL,
    grap_stage TEXT NOT NULL,
    log_date DATE DEFAULT (DATE('now'))
);

-- 5. District-wise Stubble Burning Breakdown
CREATE TABLE IF NOT EXISTS district_fire_counts (
    district TEXT PRIMARY KEY,
    fires INTEGER NOT NULL,
    state TEXT NOT NULL,
    last_surveyed DATE DEFAULT (DATE('now'))
);

-- 6. Graded Response Action Plan (GRAP) Guidelines
CREATE TABLE IF NOT EXISTS grap_stages (
    stage TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    aqi_range TEXT NOT NULL,
    is_active BOOLEAN DEFAULT 0,
    upcoming_notice TEXT,
    actions_json TEXT NOT NULL
);

-- 7. Early Warning Alert Feed
CREATE TABLE IF NOT EXISTS early_warning_alerts (
    id TEXT PRIMARY KEY,
    level TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    timestamp_str TEXT NOT NULL,
    title TEXT NOT NULL,
    detail TEXT NOT NULL,
    action_required TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 8. Simulation Run History (Stores scenarios run by users/engine)
CREATE TABLE IF NOT EXISTS simulation_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fire_count INTEGER NOT NULL,
    wind_speed REAL NOT NULL,
    wind_dir INTEGER NOT NULL,
    pbl_height INTEGER NOT NULL,
    baseline_aqi INTEGER NOT NULL,
    bio_dec_pct INTEGER NOT NULL,
    happy_seeder_pct INTEGER NOT NULL,
    predicted_aqi INTEGER NOT NULL,
    predicted_pm25 REAL NOT NULL,
    predicted_pm10 REAL NOT NULL,
    parali_pct REAL NOT NULL,
    grap_stage TEXT NOT NULL,
    mitigation_drop INTEGER NOT NULL
);

-- 9. Custom Safety Threshold Settings
CREATE TABLE IF NOT EXISTS custom_thresholds (
    id INTEGER PRIMARY KEY,
    aqi_threshold INTEGER NOT NULL DEFAULT 400,
    fires_threshold INTEGER NOT NULL DEFAULT 2000,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 10. Satellite Fire Observations (Normalized NASA FIRMS records)
CREATE TABLE IF NOT EXISTS fire_observations (
    id TEXT PRIMARY KEY,                       -- Deterministic SHA-256 hash
    source_provider TEXT NOT NULL DEFAULT 'NASA_FIRMS',
    source_dataset TEXT NOT NULL,              -- VIIRS_NOAA20_NRT, VIIRS_SNPP_NRT, MODIS_NRT, etc.
    satellite TEXT NOT NULL,                   -- NOAA-20, Suomi-NPP, Terra, Aqua, NOAA-21
    instrument TEXT NOT NULL,                  -- VIIRS / MODIS
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    brightness REAL,                           -- Brightness temperature (Kelvin)
    bright_t31 REAL,                           -- Brightness temperature Channel 31/I-5
    scan REAL,                                 -- Scan pixel resolution
    track REAL,                                -- Track pixel resolution
    acq_date TEXT NOT NULL,                    -- YYYY-MM-DD
    acq_time TEXT NOT NULL,                    -- HHMM (UTC)
    acquisition_timestamp TIMESTAMP NOT NULL,  -- ISO-8601 UTC timestamp
    confidence TEXT NOT NULL,                  -- nominal, low, high, or 0-100 percentage
    confidence_score REAL NOT NULL,            -- Normalized 0.0 - 1.0
    version TEXT,
    frp REAL NOT NULL DEFAULT 0.0,             -- Fire Radiative Power (MW)
    daynight TEXT NOT NULL,                    -- 'D' (Day) or 'N' (Night)
    state TEXT,                                -- Punjab, Haryana, Delhi, Rajasthan, Uttar Pradesh
    district TEXT,                             -- Sangrur, Firozpur, Bathinda, etc.
    classification TEXT NOT NULL DEFAULT 'unclassified', -- agricultural, vegetation, forest, industrial, unclassified
    classification_confidence REAL DEFAULT 0.5,
    classification_method TEXT DEFAULT 'rule_based_v1',
    classification_evidence TEXT,              -- JSON details explaining classification signals
    event_id TEXT,                             -- Clustered event link
    ingestion_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    raw_payload TEXT                           -- Original raw record JSON
);

CREATE INDEX IF NOT EXISTS idx_fire_obs_coords ON fire_observations(latitude, longitude);
CREATE INDEX IF NOT EXISTS idx_fire_obs_time ON fire_observations(acquisition_timestamp);
CREATE INDEX IF NOT EXISTS idx_fire_obs_district ON fire_observations(district, state);
CREATE INDEX IF NOT EXISTS idx_fire_obs_dataset ON fire_observations(source_dataset);
CREATE INDEX IF NOT EXISTS idx_fire_obs_class ON fire_observations(classification);

-- 11. Clustered Fire Events (Spatiotemporally aggregated fire clusters)
CREATE TABLE IF NOT EXISTS fire_events (
    id TEXT PRIMARY KEY,
    centroid_lat REAL NOT NULL,
    centroid_lng REAL NOT NULL,
    state TEXT NOT NULL,
    district TEXT NOT NULL,
    observation_count INTEGER NOT NULL,
    total_frp REAL NOT NULL,
    max_frp REAL NOT NULL,
    mean_frp REAL NOT NULL,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    classification TEXT NOT NULL,
    classification_confidence REAL NOT NULL,
    radius_km REAL NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 12. Geographic Districts Master Table
CREATE TABLE IF NOT EXISTS districts (
    id TEXT PRIMARY KEY,                       -- e.g. PB_SANGRUR, HR_FATEHABAD
    name TEXT NOT NULL,
    state TEXT NOT NULL,
    centroid_lat REAL NOT NULL,
    centroid_lng REAL NOT NULL,
    min_lat REAL NOT NULL,
    max_lat REAL NOT NULL,
    min_lng REAL NOT NULL,
    max_lng REAL NOT NULL,
    area_sq_km REAL,
    primary_land_use TEXT DEFAULT 'agricultural' -- agricultural, urban, forested
);

-- 13. Data Synchronization Jobs
CREATE TABLE IF NOT EXISTS data_sync_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_type TEXT NOT NULL DEFAULT 'NASA_FIRMS',
    source_dataset TEXT NOT NULL,
    area_coordinates TEXT NOT NULL,
    day_range INTEGER NOT NULL,
    status TEXT NOT NULL,                      -- RUNNING, SUCCESS, FAILED, PARTIAL
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    duration_seconds REAL,
    records_fetched INTEGER DEFAULT 0,
    records_inserted INTEGER DEFAULT 0,
    duplicates_skipped INTEGER DEFAULT 0,
    error_message TEXT,
    http_status INTEGER
);

-- 14. Data Provider Status
CREATE TABLE IF NOT EXISTS data_provider_status (
    provider_id TEXT PRIMARY KEY,              -- 'NASA_FIRMS', 'CPCB', 'OPEN_METEO'
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'unconfigured', -- 'operational', 'degraded', 'offline', 'unconfigured'
    selected_dataset TEXT,
    last_attempt TIMESTAMP,
    last_success TIMESTAMP,
    total_syncs INTEGER DEFAULT 0,
    successful_syncs INTEGER DEFAULT 0,
    failed_syncs INTEGER DEFAULT 0,
    last_error TEXT,
    freshness_minutes INTEGER,
    records_count INTEGER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 15. Real-World Alert Records (Formal Lifecycle: NEW, ACKNOWLEDGED, RESOLVED, DISMISSED)
CREATE TABLE IF NOT EXISTS alert_records (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,                    -- high_fire_activity, extreme_frp, grap_threshold, etc.
    severity TEXT NOT NULL,                    -- INFO, WARNING, CRITICAL, EMERGENCY
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    state TEXT,
    district TEXT,
    trigger_condition TEXT,
    status TEXT NOT NULL DEFAULT 'NEW',        -- NEW, ACKNOWLEDGED, INVESTIGATING, RESOLVED, DISMISSED
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    acknowledged_at TIMESTAMP,
    resolved_at TIMESTAMP,
    resolution_notes TEXT,
    evidence_json TEXT
);

