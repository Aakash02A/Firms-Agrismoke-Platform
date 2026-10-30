-- ==============================================================================
-- AgriSmoke AI - Enterprise PostgreSQL + PostGIS Schema Migration
-- Designed for cloud-native scale, high-frequency satellite telemetry ingestion,
-- and high-performance geospatial spatial boundary intersections.
-- ==============================================================================

-- 1. Enable PostGIS Spatial Extensions
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ------------------------------------------------------------------------------
-- 2. Monitoring Stations (Ground Sensors)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS monitoring_stations (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    type VARCHAR(64) NOT NULL,
    lat DOUBLE PRECISION NOT NULL,
    lng DOUBLE PRECISION NOT NULL,
    geom GEOMETRY(Point, 4326),
    aqi INTEGER NOT NULL,
    category VARCHAR(64) NOT NULL,
    pm25 DOUBLE PRECISION NOT NULL,
    pm10 DOUBLE PRECISION NOT NULL,
    parali_pct DOUBLE PRECISION NOT NULL,
    trend VARCHAR(32) DEFAULT 'stable',
    last_updated TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_stations_geom ON monitoring_stations USING GIST(geom);

-- ------------------------------------------------------------------------------
-- 3. Geographic Districts Master Table (Polygons & Airshed Regions)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS districts (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    state VARCHAR(64) NOT NULL,
    centroid_lat DOUBLE PRECISION NOT NULL,
    centroid_lng DOUBLE PRECISION NOT NULL,
    centroid_geom GEOMETRY(Point, 4326),
    boundary_geom GEOMETRY(Polygon, 4326),
    min_lat DOUBLE PRECISION NOT NULL,
    max_lat DOUBLE PRECISION NOT NULL,
    min_lng DOUBLE PRECISION NOT NULL,
    max_lng DOUBLE PRECISION NOT NULL,
    area_sq_km DOUBLE PRECISION,
    primary_land_use VARCHAR(64) DEFAULT 'agricultural'
);

CREATE INDEX IF NOT EXISTS idx_districts_centroid ON districts USING GIST(centroid_geom);
CREATE INDEX IF NOT EXISTS idx_districts_boundary ON districts USING GIST(boundary_geom);

-- ------------------------------------------------------------------------------
-- 4. Satellite Fire Observations (Pixel-level NASA VIIRS/MODIS Telemetry)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fire_observations (
    id VARCHAR(64) PRIMARY KEY,
    source_provider VARCHAR(64) DEFAULT 'NASA_FIRMS',
    source_dataset VARCHAR(64) NOT NULL,
    satellite VARCHAR(64) NOT NULL,
    instrument VARCHAR(32) NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    geom GEOMETRY(Point, 4326),
    brightness DOUBLE PRECISION,
    bright_t31 DOUBLE PRECISION,
    scan DOUBLE PRECISION,
    track DOUBLE PRECISION,
    acq_date DATE NOT NULL,
    acq_time VARCHAR(8) NOT NULL,
    acquisition_timestamp TIMESTAMPTZ NOT NULL,
    confidence VARCHAR(32) NOT NULL,
    confidence_score DOUBLE PRECISION NOT NULL,
    version VARCHAR(32),
    frp DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    daynight VARCHAR(4) NOT NULL,
    state VARCHAR(64),
    district VARCHAR(128),
    classification VARCHAR(64) DEFAULT 'unclassified',
    classification_confidence DOUBLE PRECISION DEFAULT 0.5,
    classification_method VARCHAR(64) DEFAULT 'rule_based_v1',
    classification_evidence JSONB,
    event_id VARCHAR(64),
    ingestion_timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    raw_payload JSONB
);

CREATE INDEX IF NOT EXISTS idx_fire_obs_geom ON fire_observations USING GIST(geom);
CREATE INDEX IF NOT EXISTS idx_fire_obs_time ON fire_observations(acquisition_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_fire_obs_district ON fire_observations(district, state);
CREATE INDEX IF NOT EXISTS idx_fire_obs_class ON fire_observations(classification);

-- Auto-populate Geometry Column on Insert/Update
CREATE OR REPLACE FUNCTION update_fire_geom() RETURNS TRIGGER AS $$
BEGIN
    NEW.geom := ST_SetSRID(ST_MakePoint(NEW.longitude, NEW.latitude), 4326);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_fire_obs_geom ON fire_observations;
CREATE TRIGGER trg_fire_obs_geom
    BEFORE INSERT OR UPDATE ON fire_observations
    FOR EACH ROW EXECUTE FUNCTION update_fire_geom();

-- ------------------------------------------------------------------------------
-- 5. Clustered Fire Events (Spatiotemporally aggregated events)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fire_events (
    id VARCHAR(64) PRIMARY KEY,
    centroid_lat DOUBLE PRECISION NOT NULL,
    centroid_lng DOUBLE PRECISION NOT NULL,
    centroid_geom GEOMETRY(Point, 4326),
    state VARCHAR(64) NOT NULL,
    district VARCHAR(128) NOT NULL,
    observation_count INTEGER NOT NULL,
    total_frp DOUBLE PRECISION NOT NULL,
    max_frp DOUBLE PRECISION NOT NULL,
    mean_frp DOUBLE PRECISION NOT NULL,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    classification VARCHAR(64) NOT NULL,
    classification_confidence DOUBLE PRECISION NOT NULL,
    radius_km DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_fire_events_geom ON fire_events USING GIST(centroid_geom);
CREATE INDEX IF NOT EXISTS idx_fire_events_frp ON fire_events(total_frp DESC);

-- ------------------------------------------------------------------------------
-- 6. Regulatory & Operational Alert Records (Lifecycle Managed)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS alert_records (
    id VARCHAR(64) PRIMARY KEY,
    category VARCHAR(64) NOT NULL,
    severity VARCHAR(32) NOT NULL,
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    state VARCHAR(64),
    district VARCHAR(128),
    trigger_condition TEXT,
    status VARCHAR(32) DEFAULT 'NEW',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    acknowledged_at TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ,
    resolution_notes TEXT,
    evidence_json JSONB
);

CREATE INDEX IF NOT EXISTS idx_alerts_status ON alert_records(status, created_at DESC);

-- ------------------------------------------------------------------------------
-- 7. Simulation History (Scenario Analytics Run Log)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS simulation_history (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    fire_count INTEGER NOT NULL,
    wind_speed DOUBLE PRECISION NOT NULL,
    wind_dir INTEGER NOT NULL,
    pbl_height INTEGER NOT NULL,
    baseline_aqi INTEGER NOT NULL,
    bio_dec_pct INTEGER NOT NULL,
    happy_seeder_pct INTEGER NOT NULL,
    predicted_aqi INTEGER NOT NULL,
    predicted_pm25 DOUBLE PRECISION NOT NULL,
    predicted_pm10 DOUBLE PRECISION NOT NULL,
    parali_pct DOUBLE PRECISION NOT NULL,
    grap_stage VARCHAR(32) NOT NULL,
    mitigation_drop INTEGER NOT NULL,
    uncertainty_margin INTEGER,
    aod_estimated DOUBLE PRECISION
);

-- ------------------------------------------------------------------------------
-- 8. Data Synchronization & Provider Health Telemetry
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS data_sync_jobs (
    id BIGSERIAL PRIMARY KEY,
    job_type VARCHAR(64) DEFAULT 'NASA_FIRMS',
    source_dataset VARCHAR(64) NOT NULL,
    area_coordinates VARCHAR(128) NOT NULL,
    day_range INTEGER NOT NULL,
    status VARCHAR(32) NOT NULL,
    started_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    duration_seconds DOUBLE PRECISION,
    records_fetched INTEGER DEFAULT 0,
    records_inserted INTEGER DEFAULT 0,
    duplicates_skipped INTEGER DEFAULT 0,
    error_message TEXT,
    http_status INTEGER
);

CREATE TABLE IF NOT EXISTS data_provider_status (
    provider_id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    status VARCHAR(32) DEFAULT 'unconfigured',
    selected_dataset VARCHAR(64),
    last_attempt TIMESTAMPTZ,
    last_success TIMESTAMPTZ,
    total_syncs INTEGER DEFAULT 0,
    successful_syncs INTEGER DEFAULT 0,
    failed_syncs INTEGER DEFAULT 0,
    last_error TEXT,
    freshness_minutes INTEGER,
    records_count INTEGER DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
