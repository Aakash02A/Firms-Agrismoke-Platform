# 📚 AgriSmoke AI &bull; Data Dictionary & Database Specification

This document provides the definitive data models, types, constraints, and index definitions for the **AgriSmoke AI** SQLite relational store (`database/agri_smoke.db`).

---

## 1. Core Tables

### 1.1 `fire_observations` (Normalized NASA FIRMS Telemetry)
Stores pixel-level thermal anomalies detected by satellite instruments (VIIRS and MODIS).

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | TEXT | PRIMARY KEY | Deterministic SHA-256 hash of `(source_dataset, latitude, longitude, acq_date, acq_time)` preventing duplicate entries. |
| `source_provider` | TEXT | NOT NULL DEFAULT 'NASA_FIRMS' | Originating data provider. |
| `source_dataset` | TEXT | NOT NULL | NASA product code (e.g., `VIIRS_NOAA20_NRT`, `VIIRS_SNPP_NRT`, `MODIS_NRT`). |
| `satellite` | TEXT | NOT NULL | Satellite platform (`NOAA-20`, `Suomi-NPP`, `Terra`, `Aqua`). |
| `instrument` | TEXT | NOT NULL | Sensor instrument (`VIIRS`, `MODIS`). |
| `latitude` | REAL | NOT NULL | WGS-84 decimal latitude (-90.0 to 90.0). |
| `longitude` | REAL | NOT NULL | WGS-84 decimal longitude (-180.0 to 180.0). |
| `brightness` | REAL | NULL | Brightness temperature (Kelvin) for I-4 channel (VIIRS) or 21/31 channel (MODIS). |
| `bright_t31` | REAL | NULL | Channel 31/I-5 brightness temperature (Kelvin). |
| `scan` | REAL | NULL | Scan pixel resolution (km). |
| `track` | REAL | NULL | Track pixel resolution (km). |
| `acq_date` | TEXT | NOT NULL | UTC Acquisition Date formatted as `YYYY-MM-DD`. |
| `acq_time` | TEXT | NOT NULL | UTC Acquisition Time formatted as `HHMM`. |
| `acquisition_timestamp` | TIMESTAMP | NOT NULL | ISO-8601 UTC timestamp (`YYYY-MM-DDTHH:MM:SSZ`). |
| `confidence` | TEXT | NOT NULL | Native confidence level (`low`, `nominal`, `high` or percentage `0-100`). |
| `confidence_score` | REAL | NOT NULL | Standardized normalized confidence score ($0.0$ to $1.0$). |
| `version` | TEXT | NULL | NRT or Standard processing algorithm version. |
| `frp` | REAL | NOT NULL DEFAULT 0.0 | Fire Radiative Power in Megawatts (MW). |
| `daynight` | TEXT | NOT NULL | Overpass solar regime: `'D'` (Daytime) or `'N'` (Nighttime). |
| `state` | TEXT | NULL | Identified Indian State (Punjab, Haryana, Delhi, Rajasthan, UP). |
| `district` | TEXT | NULL | Identified district name (e.g., Sangrur, Firozpur). |
| `classification` | TEXT | NOT NULL DEFAULT 'unclassified' | `agricultural`, `vegetation`, `forest`, `industrial`, `unclassified`. |
| `classification_confidence`| REAL | DEFAULT 0.5 | Probability score of classification ($0.0$ to $1.0$). |
| `classification_method`| TEXT | DEFAULT 'rule_based_v1' | Algorithm or version used for classification. |
| `classification_evidence` | TEXT | NULL | JSON string detailing contextual signals, land use, and seasonal factors. |
| `event_id` | TEXT | NULL | Foreign key referencing spatiotemporally grouped `fire_events`. |
| `ingestion_timestamp` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | UTC timestamp when the record was persisted. |
| `raw_payload` | TEXT | NULL | JSON representation of the raw CSV row from NASA FIRMS. |

**Indexes:**
- `idx_fire_obs_coords` on `(latitude, longitude)`
- `idx_fire_obs_time` on `(acquisition_timestamp)`
- `idx_fire_obs_district` on `(district, state)`
- `idx_fire_obs_dataset` on `(source_dataset)`
- `idx_fire_obs_class` on `(classification)`

---

### 1.2 `fire_events` (Spatiotemporal Clusters)
Represents discrete, clustered fire incidents constructed by grouping adjacent pixel detections within spatial ($\le 3.5\text{km}$) and temporal ($\le 12\text{h}$) thresholds.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | TEXT | PRIMARY KEY | Unique event identifier (e.g., `EVT_20261029_001`). |
| `centroid_lat` | REAL | NOT NULL | Geographic center latitude of the cluster. |
| `centroid_lng` | REAL | NOT NULL | Geographic center longitude of the cluster. |
| `state` | TEXT | NOT NULL | State name. |
| `district` | TEXT | NOT NULL | District name. |
| `observation_count`| INTEGER | NOT NULL | Number of satellite pixels grouped into this event. |
| `total_frp` | REAL | NOT NULL | Cumulative Fire Radiative Power (MW). |
| `max_frp` | REAL | NOT NULL | Peak pixel Fire Radiative Power (MW). |
| `mean_frp` | REAL | NOT NULL | Average Fire Radiative Power (MW). |
| `start_time` | TIMESTAMP | NOT NULL | Earliest observation timestamp in the cluster. |
| `end_time` | TIMESTAMP | NOT NULL | Latest observation timestamp in the cluster. |
| `classification`| TEXT | NOT NULL | Aggregated event classification. |
| `classification_confidence` | REAL | NOT NULL | Confidence score ($0.0$ to $1.0$). |
| `radius_km` | REAL | NOT NULL | Spatial spread radius of the cluster. |
| `created_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Record creation timestamp. |

---

### 1.3 `districts` (Geographic Administration Boundaries)
Contains spatial bounding boxes and centroids for upwind agricultural and downwind receptor districts across Punjab, Haryana, Delhi-NCR, Rajasthan, and Western Uttar Pradesh.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | TEXT | PRIMARY KEY | District code (e.g., `PB_SANGRUR`, `HR_FATEHABAD`). |
| `name` | TEXT | NOT NULL | District name. |
| `state` | TEXT | NOT NULL | State name (`Punjab`, `Haryana`, `Delhi`, etc.). |
| `centroid_lat` | REAL | NOT NULL | District centroid latitude. |
| `centroid_lng` | REAL | NOT NULL | District centroid longitude. |
| `min_lat` / `max_lat` | REAL | NOT NULL | Latitude bounding box extents. |
| `min_lng` / `max_lng` | REAL | NOT NULL | Longitude bounding box extents. |
| `area_sq_km` | REAL | NULL | Approximate total land area ($\text{km}^2$). |
| `primary_land_use`| TEXT | DEFAULT 'agricultural' | `agricultural`, `urban`, `forest`. |

---

### 1.4 `data_sync_jobs` (Telemetry Ingestion Audit)
Records telemetry synchronization events, payload statistics, and audit diagnostics.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Sequential job ID. |
| `job_type` | TEXT | DEFAULT 'NASA_FIRMS' | Provider type (`NASA_FIRMS`, `CPCB`, etc.). |
| `source_dataset` | TEXT | NOT NULL | Satellite dataset requested. |
| `area_coordinates` | TEXT | NOT NULL | Bounding box requested (`west,south,east,north`). |
| `day_range` | INTEGER | NOT NULL | Day range requested (1 to 5). |
| `status` | TEXT | NOT NULL | `RUNNING`, `SUCCESS`, `FAILED`, `PARTIAL`. |
| `started_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Job trigger timestamp. |
| `completed_at` | TIMESTAMP | NULL | Job completion timestamp. |
| `duration_seconds`| REAL | NULL | Total execution duration. |
| `records_fetched` | INTEGER | DEFAULT 0 | Raw rows received from provider API. |
| `records_inserted`| INTEGER | DEFAULT 0 | New unique rows persisted. |
| `duplicates_skipped` | INTEGER | DEFAULT 0 | Existing rows identified and deduplicated. |
| `error_message` | TEXT | NULL | Detailed diagnostic error message upon failure. |
| `http_status` | INTEGER | NULL | HTTP response code from provider. |

---

### 1.5 `data_provider_status` (Health & Telemetry Metadata)
Maintains real-time service health, data freshness, and API operational status.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `provider_id` | TEXT | PRIMARY KEY | `NASA_FIRMS`, `CPCB`, `OPEN_METEO`. |
| `name` | TEXT | NOT NULL | Full provider title. |
| `status` | TEXT | NOT NULL | `operational`, `degraded`, `offline`, `unconfigured`. |
| `selected_dataset`| TEXT | NULL | Active dataset selected for analysis. |
| `last_attempt` | TIMESTAMP | NULL | Timestamp of most recent sync attempt. |
| `last_success` | TIMESTAMP | NULL | Timestamp of most recent successful ingestion. |
| `total_syncs` | INTEGER | DEFAULT 0 | Cumulative sync executions. |
| `successful_syncs`| INTEGER | DEFAULT 0 | Total successful syncs. |
| `failed_syncs` | INTEGER | DEFAULT 0 | Total failed syncs. |
| `last_error` | TEXT | NULL | Most recent error message. |
| `freshness_minutes` | INTEGER | NULL | Elapsed minutes since newest persisted observation. |
| `records_count` | INTEGER | DEFAULT 0 | Total active records in database. |
| `updated_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Health record update time. |

---

### 1.6 `alert_records` (Real-World Environmental Incident Lifecycle)
Manages persistent alerts, threshold triggers, and administrative disposition.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | TEXT | PRIMARY KEY | Unique alert identifier (e.g., `ALT_20261030_001`). |
| `category` | TEXT | NOT NULL | `high_fire_activity`, `extreme_frp`, `grap_threshold`, `inversion_trapping`. |
| `severity` | TEXT | NOT NULL | `INFO`, `WARNING`, `CRITICAL`, `EMERGENCY`. |
| `title` | TEXT | NOT NULL | Clear alert headline. |
| `message` | TEXT | NOT NULL | Detailed narrative description. |
| `state` / `district` | TEXT | NULL | Geographic focus area. |
| `trigger_condition` | TEXT | NULL | Quantitative threshold that triggered the alert. |
| `status` | TEXT | DEFAULT 'NEW' | `NEW`, `ACKNOWLEDGED`, `INVESTIGATING`, `RESOLVED`, `DISMISSED`. |
| `created_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Alert trigger timestamp. |
| `acknowledged_at`| TIMESTAMP | NULL | Timestamp when operator acknowledged alert. |
| `resolved_at` | TIMESTAMP | NULL | Timestamp when alert was marked resolved. |
| `resolution_notes`| TEXT | NULL | Notes recorded upon closure. |
| `evidence_json` | TEXT | NULL | JSON payload with triggering observation IDs and values. |
