"""
AgriSmoke AI - Database Access Layer
Provides clean CRUD helpers and queries for the SQLite database.

Production characteristics of the connection layer:
  * one short-lived connection per operation, ALWAYS closed (no fd/lock leaks);
  * WAL journal mode so API readers never block behind a FIRMS ingestion write;
  * a real busy_timeout so transient write locks retry instead of 500-ing;
  * foreign-key enforcement enabled per connection (SQLite defaults it OFF);
  * idempotent schema/index/pragma validation at startup (ensure_ready).
"""

import os
import sqlite3
import json
import shutil
import logging
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("agri_smoke.database")

# Default to the repo-local SQLite file, but allow an env override (DB_PATH) so
# PaaS/container deployments can point the database at a mounted, persistent
# volume instead of the ephemeral app directory.
_default_db = Path(__file__).resolve().parent.parent / "database" / "agri_smoke.db"
_env_db = os.getenv("DB_PATH", "").strip()
DB_PATH = Path(_env_db).expanduser() if _env_db else _default_db


def _get_int(key: str, default: int) -> int:
    try:
        return int(str(os.getenv(key, default)).strip())
    except (TypeError, ValueError):
        return default


def _get_bool(key: str, default: bool) -> bool:
    val = os.getenv(key)
    if val is None or not val.strip():
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


# --- Tunables. Env-overridable so an operator can react to lock contention or
# disk layout on a running deployment without shipping code.
BUSY_TIMEOUT_MS: int = max(0, _get_int("SQLITE_BUSY_TIMEOUT_MS", 10000))
WAL_ENABLED: bool = _get_bool("SQLITE_WAL", True)
CACHE_SIZE_KB: int = _get_int("SQLITE_CACHE_SIZE_KB", -8000)   # negative => KiB/connection
WAL_JOURNAL_SIZE_LIMIT: int = _get_int("SQLITE_WAL_JOURNAL_SIZE_LIMIT", 64 * 1024 * 1024)

# Tables the API cannot function without. Verified (not created blindly) at startup.
REQUIRED_TABLES = (
    "monitoring_stations", "fire_hotspots", "weekly_trends", "district_fire_counts",
    "grap_stages", "early_warning_alerts", "custom_thresholds", "fire_observations",
    "fire_events", "districts", "data_sync_jobs", "data_provider_status", "alert_records",
)

# Performance indexes for the read paths that hit the DB on every dashboard poll.
# Applied idempotently at startup so already-deployed DB files get them too.
INDEX_DDL = (
    # get_fire_observation_stats / get_live_fire_hotspots / get_live_district_fire_counts
    # and the district join all filter on acq_date; without this they full-scan.
    "CREATE INDEX IF NOT EXISTS idx_fire_obs_acq_date ON fire_observations(acq_date)",
    # GET /api/v1/alerts?status=... ORDER BY created_at DESC
    "CREATE INDEX IF NOT EXISTS idx_alert_records_status_created ON alert_records(status, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_alert_records_created ON alert_records(created_at)",
    # GET /api/v1/geospatial/events ORDER BY total_frp DESC
    "CREATE INDEX IF NOT EXISTS idx_fire_events_total_frp ON fire_events(total_frp)",
    # provider telemetry reads, newest first
    "CREATE INDEX IF NOT EXISTS idx_data_sync_jobs_started ON data_sync_jobs(started_at)",
    # supports simulation_history reads and retention pruning
    "CREATE INDEX IF NOT EXISTS idx_simulation_history_created ON simulation_history(created_at)",
)

# Resolved once per process: whether THIS database file is running in WAL.
_wal_active: Optional[bool] = None
_wal_lock = threading.Lock()


def _open_raw() -> sqlite3.Connection:
    """Create a configured SQLite connection. Prefer get_connection() instead.

    Isolation is left at the sqlite3 default (deferred, implicit BEGIN before the
    first DML) on purpose: the FIRMS ingestion helpers insert thousands of rows
    in one loop and rely on that single implicit transaction for both atomicity
    and speed. Switching to autocommit would make every row its own commit.
    """
    conn = sqlite3.connect(
        DB_PATH,
        # sqlite3's own busy timeout, so even PRAGMA setup waits out a lock.
        timeout=BUSY_TIMEOUT_MS / 1000.0,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    # synchronous=NORMAL is crash-safe under WAL and markedly faster than FULL;
    # if WAL is unavailable we stay at the default (FULL) for durability.
    conn.execute("PRAGMA temp_store = MEMORY")
    conn.execute(f"PRAGMA cache_size = {CACHE_SIZE_KB}")
    if _wal_active:
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute(f"PRAGMA journal_size_limit = {WAL_JOURNAL_SIZE_LIMIT}")
    return conn


def _try_enable_wal() -> bool:
    """Flip the database file to WAL once per process and remember the result.

    journal_mode is persistent in the DB header, so this is a one-time setup
    cost rather than a per-connection pragma. A concurrent reader/writer can
    make the switch return busy, which is why the outcome is only cached after a
    confirmed change and otherwise re-checked on the next call.
    """
    global _wal_active
    if not WAL_ENABLED:
        _wal_active = False
        return False
    with _wal_lock:
        if _wal_active is True:
            return True
        try:
            conn = sqlite3.connect(DB_PATH, timeout=BUSY_TIMEOUT_MS / 1000.0)
            try:
                mode = conn.execute("PRAGMA journal_mode = WAL").fetchone()[0]
                conn.execute(f"PRAGMA synchronous = {'NORMAL' if str(mode).lower() == 'wal' else 'FULL'}")
                conn.execute(f"PRAGMA journal_size_limit = {WAL_JOURNAL_SIZE_LIMIT}")
                conn.commit()
            finally:
                conn.close()
            got_wal = str(mode).lower() == "wal"
            if got_wal:
                _wal_active = True
                logger.info("SQLite journal_mode=WAL active on %s (concurrent readers no longer blocked by writers)", DB_PATH)
            else:
                logger.warning(
                    "SQLite could not switch to WAL (journal_mode=%s) on %s; falling back to rollback journal. "
                    "WAL needs a local filesystem that supports shared memory - not NFS/FUSE mounts.",
                    mode, DB_PATH,
                )
            return got_wal
        except sqlite3.Error as exc:
            logger.warning("WAL setup skipped (%s); continuing with default journal mode", exc)
            return False


@contextmanager
def get_connection():
    """Context manager yielding a configured connection that is always closed.

    ``with get_connection() as conn:`` commits on a clean exit and rolls back on
    an exception - the same transaction semantics sqlite3.Connection provides -
    but additionally releases the file handle. Without that release a failed
    statement keeps the connection (and its locks) alive via the traceback
    frames of the in-flight exception, which is how a single "database is
    locked" error cascades into a stalled API.
    """
    _try_enable_wal()
    conn = _open_raw()
    try:
        yield conn
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except sqlite3.Error:  # pragma: no cover - already-failed handle
            pass
        raise
    finally:
        conn.close()

def get_monitoring_stations() -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM monitoring_stations ORDER BY aqi DESC")
        rows = cursor.fetchall()
        results = []
        for row in rows:
            d = dict(row)
            d["paraliPct"] = row["parali_pct"]
            results.append(d)
        return results

def get_fire_hotspots() -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM fire_hotspots ORDER BY fire_count DESC")
        rows = cursor.fetchall()
        results = []
        for row in rows:
            d = dict(row)
            d["fireCount"] = row["fire_count"]
            d["avgFRP"] = row["avg_frp"]
            d["harvestProgress"] = row["harvest_progress"]
            d["smokeIntensity"] = row["smoke_intensity"]
            results.append(d)
        return results

def get_weekly_trends() -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM weekly_trends ORDER BY id ASC")
        rows = cursor.fetchall()
        return [
            {
                "day": row["day_label"],
                "aqi": row["aqi"],
                "fires": row["fires"],
                "pm25": row["pm25"],
                "stubblePct": row["stubble_pct"],
                "grapStage": row["grap_stage"]
            }
            for row in rows
        ]

def get_district_fire_counts() -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM district_fire_counts ORDER BY fires DESC")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def get_grap_stages() -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM grap_stages ORDER BY stage ASC")
        rows = cursor.fetchall()
        results = []
        for row in rows:
            results.append({
                "stage": row["stage"],
                "title": row["title"],
                "aqiRange": row["aqi_range"],
                "active": bool(row["is_active"]),
                "upcomingNotice": row["upcoming_notice"],
                "actions": json.loads(row["actions_json"]) if row["actions_json"] else []
            })
        return results

def get_early_warning_alerts() -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM early_warning_alerts ORDER BY created_at DESC")
        rows = cursor.fetchall()
        return [
            {
                "id": row["id"],
                "level": row["level"],
                "type": row["alert_type"],
                "timestamp": row["timestamp_str"],
                "title": row["title"],
                "detail": row["detail"],
                "actionRequired": row["action_required"]
            }
            for row in rows
        ]

def get_custom_thresholds() -> Dict[str, int]:
    # Read-only lookup with safe defaults: a missing table or DB error must not
    # crash /api/status (previously raised "no such table: custom_thresholds"
    # when the DB file existed but was never initialized).
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT aqi_threshold, fires_threshold FROM custom_thresholds WHERE id = 1")
            row = cursor.fetchone()
            if row:
                return {"aqi": row["aqi_threshold"], "fires": row["fires_threshold"]}
    except sqlite3.Error as exc:
        logger.warning("Custom thresholds lookup failed (%s); using defaults", exc)
    return {"aqi": 400, "fires": 2000}

def update_custom_thresholds(aqi: int, fires: int) -> Dict[str, int]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO custom_thresholds (id, aqi_threshold, fires_threshold, updated_at)
            VALUES (1, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                aqi_threshold = excluded.aqi_threshold,
                fires_threshold = excluded.fires_threshold,
                updated_at = CURRENT_TIMESTAMP
        """, (aqi, fires))
        conn.commit()
    return {"aqi": aqi, "fires": fires}

def save_simulation_run(params: dict, pred: dict):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO simulation_history (
                fire_count, wind_speed, wind_dir, pbl_height,
                baseline_aqi, bio_dec_pct, happy_seeder_pct,
                predicted_aqi, predicted_pm25, predicted_pm10,
                parali_pct, grap_stage, mitigation_drop
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            int(params.get("fireCount", 0)),
            float(params.get("windSpeed", 0.0)),
            int(params.get("windDirectionDeg", 0)),
            int(params.get("pblHeight", 0)),
            int(params.get("urbanBaselineAqi", 0)),
            int(params.get("bioDecomposerAdoption", 0)),
            int(params.get("happySeederAdoption", 0)),
            pred.get("predictedAqi", 0),
            pred.get("totalPm25", 0.0),
            pred.get("totalPm10", 0.0),
            pred.get("paraliPct", 0.0),
            pred.get("grapStage", "None"),
            pred.get("mitigationSavings", {}).get("aqiDrop", 0)
        ))
        conn.commit()


# ============================================================================
# NASA FIRMS & GEOSPATIAL INTELLIGENCE ACCESS LAYER
# ============================================================================

def insert_fire_observations(observations: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Insert normalized fire observations into the fire_observations table with SHA-256 deduplication.
    Uses INSERT OR IGNORE to safely handle duplicates without error.
    Returns counts of inserted, skipped (duplicate), and total processed.
    """
    if not observations:
        return {"total": 0, "inserted": 0, "skipped": 0, "errors": 0}

    inserted = 0
    errors = 0

    sql = """
        INSERT OR IGNORE INTO fire_observations (
            id, source_provider, source_dataset, satellite, instrument,
            latitude, longitude, brightness, bright_t31, scan, track,
            acq_date, acq_time, acquisition_timestamp, confidence,
            confidence_score, version, frp, daynight, state, district,
            classification, classification_confidence, classification_method,
            classification_evidence, event_id, raw_payload, ingestion_timestamp
        ) VALUES (
            :id, :source_provider, :source_dataset, :satellite, :instrument,
            :latitude, :longitude, :brightness, :bright_t31, :scan, :track,
            :acq_date, :acq_time, :acquisition_timestamp, :confidence,
            :confidence_score, :version, :frp, :daynight, :state, :district,
            :classification, :classification_confidence, :classification_method,
            :classification_evidence, :event_id, :raw_payload, CURRENT_TIMESTAMP
        )
    """

    with get_connection() as conn:
        cursor = conn.cursor()
        for obs in observations:
            try:
                # Prepare payload ensuring schema keys match
                record = {
                    "id": obs["id"],
                    "source_provider": obs.get("source_provider", "NASA_FIRMS"),
                    "source_dataset": obs.get("source_dataset", "VIIRS_NOAA20_NRT"),
                    "satellite": obs.get("satellite", "NOAA-20"),
                    "instrument": obs.get("instrument", "VIIRS"),
                    "latitude": obs["latitude"],
                    "longitude": obs["longitude"],
                    "brightness": obs.get("brightness") or obs.get("brightness_temperature"),
                    "bright_t31": obs.get("bright_t31") or obs.get("bright_ti5"),
                    "scan": obs.get("scan"),
                    "track": obs.get("track"),
                    "acq_date": obs["acq_date"],
                    "acq_time": obs["acq_time"],
                    "acquisition_timestamp": obs["acquisition_timestamp"],
                    "confidence": obs.get("confidence") or obs.get("confidence_raw") or "nominal",
                    "confidence_score": obs.get("confidence_score") if obs.get("confidence_score") is not None else obs.get("confidence_normalized", 0.65),
                    "version": obs.get("version") or obs.get("source_version"),
                    "frp": obs.get("frp", 0.0),
                    "daynight": obs.get("daynight") or obs.get("day_night", "D"),
                    "state": obs.get("state"),
                    "district": obs.get("district") or obs.get("district_id"),
                    "classification": obs.get("classification", "unclassified"),
                    "classification_confidence": obs.get("classification_confidence", 0.5),
                    "classification_method": obs.get("classification_method", "rule_based_v2"),
                    "classification_evidence": obs.get("classification_evidence"),
                    "event_id": obs.get("event_id"),
                    "raw_payload": obs.get("raw_payload")
                }
                cursor.execute(sql, record)
                inserted += cursor.rowcount
            except Exception:
                errors += 1
        conn.commit()

    total = len(observations)
    skipped = total - inserted - errors
    return {"total": total, "inserted": inserted, "skipped": skipped, "errors": errors}


def get_fire_observations(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    satellite: Optional[str] = None,
    min_confidence: Optional[float] = None,
    min_frp: Optional[float] = None,
    state: Optional[str] = None,
    district_id: Optional[str] = None,
    classification: Optional[str] = None,
    limit: int = 500,
    offset: int = 0
) -> List[Dict[str, Any]]:
    """Query normalized fire observations with flexible spatiotemporal & quality filters."""
    conditions = ["1=1"]
    params = []

    if start_date:
        conditions.append("acq_date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("acq_date <= ?")
        params.append(end_date)
    if satellite:
        conditions.append("satellite = ?")
        params.append(satellite)
    if min_confidence is not None:
        conditions.append("confidence_score >= ?")
        params.append(min_confidence)
    if min_frp is not None:
        conditions.append("frp >= ?")
        params.append(min_frp)
    if state:
        conditions.append("state = ?")
        params.append(state)
    if district_id:
        conditions.append("(district = ? OR district LIKE ?)")
        params.append(district_id)
        params.append(f"%{district_id}%")
    if classification:
        conditions.append("classification = ?")
        params.append(classification)

    where_clause = " AND ".join(conditions)
    sql = f"""
        SELECT * FROM fire_observations
        WHERE {where_clause}
        ORDER BY acquisition_timestamp DESC
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        results = []
        for row in rows:
            d = dict(row)
            # Maintain backward & forward alias compatibility
            d["confidence_normalized"] = d.get("confidence_score", 0.5)
            d["district_id"] = d.get("district")
            results.append(d)
        return results


def get_fire_observation_stats(days: int = 3) -> Dict[str, Any]:
    """Retrieve aggregate statistics for recent fire observations."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                COUNT(*) as total_observations,
                COALESCE(SUM(CASE WHEN classification = 'agricultural' THEN 1 ELSE 0 END), 0) as agricultural_count,
                COALESCE(SUM(CASE WHEN confidence_score >= 0.7 THEN 1 ELSE 0 END), 0) as high_confidence_count,
                COALESCE(AVG(frp), 0.0) as avg_frp,
                COALESCE(MAX(frp), 0.0) as max_frp,
                COALESCE(SUM(frp), 0.0) as total_frp,
                MAX(acquisition_timestamp) as latest_acquisition,
                MIN(acquisition_timestamp) as earliest_acquisition,
                COUNT(DISTINCT district) as active_districts_count
            FROM fire_observations
            WHERE acq_date >= date('now', '-' || ? || ' days')
        """, (days,))
        row = cursor.fetchone()
        stats = dict(row) if row else {}
        stats["avg_frp"] = round(stats.get("avg_frp", 0.0), 2)
        stats["total_frp"] = round(stats.get("total_frp", 0.0), 2)
        stats["max_frp"] = round(stats.get("max_frp", 0.0), 2)
        return stats


def get_districts() -> List[Dict[str, Any]]:
    """Retrieve reference metadata for all configured districts."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM districts ORDER BY state, name")
        rows = cursor.fetchall()
        results = []
        for row in rows:
            d = dict(row)
            d["center_lat"] = d.get("centroid_lat")
            d["center_lon"] = d.get("centroid_lng")
            d["stubble_risk_level"] = "CRITICAL" if d.get("state") == "Punjab" else ("HIGH" if d.get("state") == "Haryana" else "MODERATE")
            d["dominant_crop"] = "Paddy / Wheat" if d.get("primary_land_use") == "agricultural" else "Urban / Mixed"
            results.append(d)
        return results


def get_district_fire_summary(days: int = 3) -> List[Dict[str, Any]]:
    """
    Compute live dynamic district-level fire summaries from actual NASA observations,
    fallback-joining with district reference metadata.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                d.id as district_id,
                d.name as district_name,
                d.state,
                d.centroid_lat as center_lat,
                d.centroid_lng as center_lon,
                d.primary_land_use,
                COUNT(f.id) as total_fires,
                SUM(CASE WHEN f.classification = 'agricultural' THEN 1 ELSE 0 END) as agricultural_fires,
                COALESCE(AVG(f.frp), 0.0) as avg_frp,
                COALESCE(MAX(f.frp), 0.0) as max_frp,
                COALESCE(SUM(f.frp), 0.0) as total_frp,
                MAX(f.acquisition_timestamp) as latest_fire_time
            FROM districts d
            LEFT JOIN fire_observations f ON (d.name = f.district OR d.id = f.district)
                AND f.acq_date >= date('now', '-' || ? || ' days')
            GROUP BY d.id
            ORDER BY total_fires DESC, d.name ASC
        """, (days,))
        rows = cursor.fetchall()
        results = []
        for row in rows:
            d = dict(row)
            d["avg_frp"] = round(d["avg_frp"], 2)
            d["total_frp"] = round(d["total_frp"], 2)
            d["max_frp"] = round(d["max_frp"], 2)
            d["stubble_risk_level"] = "CRITICAL" if d.get("state") == "Punjab" else ("HIGH" if d.get("state") == "Haryana" else "MODERATE")
            d["dominant_crop"] = "Paddy / Wheat" if d.get("primary_land_use") == "agricultural" else "Urban / Mixed"
            results.append(d)
        return results


def _smoke_intensity_from_count(count: int) -> str:
    if count >= 300:
        return "Very High"
    if count >= 150:
        return "High"
    if count >= 60:
        return "Moderate"
    return "Low"


def get_live_fire_hotspots(days: int = 3) -> List[Dict[str, Any]]:
    """
    Derive active fire hotspots by aggregating REAL NASA FIRMS observations
    (last `days` days) by district. Returns [] when no live observations exist,
    allowing the caller to fall back to the seeded placeholder hotspots.
    Output shape mirrors get_fire_hotspots() so the frontend needs no changes.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                district,
                state,
                COUNT(*)                AS fire_count,
                COALESCE(AVG(frp), 0.0) AS avg_frp,
                AVG(latitude)           AS lat,
                AVG(longitude)          AS lng,
                COALESCE(AVG(confidence_score), 0.6) AS avg_conf,
                MAX(acquisition_timestamp)           AS latest_acq
            FROM fire_observations
            WHERE acq_date >= date('now', '-' || ? || ' days')
              AND district IS NOT NULL
            GROUP BY district, state
            ORDER BY fire_count DESC
        """, (days,))
        rows = cursor.fetchall()
        results = []
        for row in rows:
            d = dict(row)
            count = int(d["fire_count"])
            results.append({
                "id": f"live_{(d['district'] or 'region').lower().replace(' ', '_')}",
                "district": d["district"],
                "state": d["state"],
                "lat": round(d["lat"], 4),
                "lng": round(d["lng"], 4),
                "fire_count": count,
                "avg_frp": round(d["avg_frp"], 1),
                "status": "Live satellite detection",
                "harvest_progress": "Live (FIRMS)",
                "confidence": f"{round(d['avg_conf'] * 100)}% (VIIRS)",
                "smoke_intensity": _smoke_intensity_from_count(count),
                "fireCount": count,
                "avgFRP": round(d["avg_frp"], 1),
                "harvestProgress": "Live (FIRMS)",
                "smokeIntensity": _smoke_intensity_from_count(count),
                "live": True,
                "latestAcquisition": d["latest_acq"],
            })
        return results


def get_live_district_fire_counts(days: int = 3) -> List[Dict[str, Any]]:
    """
    District-wise live fire counts derived from REAL NASA FIRMS observations.
    Returns [] when no live data exists, so the caller can fall back to seed data.
    Output shape mirrors get_district_fire_counts() ({district, fires, state}).
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT district AS district, state, COUNT(*) AS fires
            FROM fire_observations
            WHERE acq_date >= date('now', '-' || ? || ' days')
              AND district IS NOT NULL
            GROUP BY district, state
            ORDER BY fires DESC
        """, (days,))
        return [dict(row) for row in cursor.fetchall()]


def record_sync_job(
    provider_id: str,
    status: str,
    records_received: int,
    records_inserted: int,
    records_skipped: int,
    records_rejected: int,
    execution_duration_ms: int,
    request_params: Optional[str] = None,
    error_message: Optional[str] = None
) -> int:
    """Record an execution run of data ingestion."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO data_sync_jobs (
                job_type, source_dataset, area_coordinates, day_range,
                status, duration_seconds, records_fetched, records_inserted,
                duplicates_skipped, error_message, http_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            provider_id,
            "VIIRS_NOAA20_NRT",
            request_params or "73.5,27.5,78.5,32.5",
            3,
            status,
            round(execution_duration_ms / 1000.0, 3),
            records_received,
            records_inserted,
            records_skipped,
            error_message,
            200 if status == "SUCCESS" else 500
        ))
        conn.commit()
        return cursor.lastrowid


def get_recent_sync_jobs(limit: int = 10) -> List[Dict[str, Any]]:
    """Retrieve recent data synchronization runs."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM data_sync_jobs ORDER BY started_at DESC LIMIT ?", (limit,))
        return [dict(row) for row in cursor.fetchall()]


def get_data_provider_status(provider_id: str = "NASA_FIRMS") -> Dict[str, Any]:
    """Retrieve operational status and freshness of a data provider."""
    # Normalize ID matching
    pid = "NASA_FIRMS" if "firms" in provider_id.lower() else provider_id
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM data_provider_status WHERE provider_id = ?", (pid,))
        row = cursor.fetchone()
        if row:
            d = dict(row)
            d["is_healthy"] = 1 if d.get("status") in ("operational", "ONLINE") else 0
            d["last_sync_timestamp"] = d.get("last_success") or d.get("last_attempt")
            d["total_records_ingested"] = d.get("records_count", 0)
            return d
        return {"provider_id": provider_id, "status": "unconfigured", "is_healthy": 0}


def update_data_provider_status(
    provider_id: str,
    status: str,
    is_healthy: bool,
    records_ingested_delta: int = 0,
    latest_data_timestamp: Optional[str] = None,
    error_message: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None
):
    """Update health, metrics, and freshness for a data provider."""
    pid = "NASA_FIRMS" if "firms" in provider_id.lower() else provider_id
    operational_status = "operational" if is_healthy else ("unconfigured" if "UNCONFIGURED" in status else "degraded")

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO data_provider_status (
                provider_id, name, status, selected_dataset,
                last_attempt, last_success, total_syncs,
                successful_syncs, failed_syncs, last_error, records_count, updated_at
            ) VALUES (
                ?, 'NASA FIRMS Fire Data', ?, 'VIIRS_NOAA20_NRT',
                CURRENT_TIMESTAMP, CASE WHEN ? THEN CURRENT_TIMESTAMP ELSE NULL END,
                1, CASE WHEN ? THEN 1 ELSE 0 END, CASE WHEN ? THEN 0 ELSE 1 END,
                ?, ?, CURRENT_TIMESTAMP
            )
            ON CONFLICT(provider_id) DO UPDATE SET
                status = excluded.status,
                last_attempt = CURRENT_TIMESTAMP,
                last_success = CASE WHEN ? THEN CURRENT_TIMESTAMP ELSE data_provider_status.last_success END,
                total_syncs = data_provider_status.total_syncs + 1,
                successful_syncs = data_provider_status.successful_syncs + (CASE WHEN ? THEN 1 ELSE 0 END),
                failed_syncs = data_provider_status.failed_syncs + (CASE WHEN ? THEN 0 ELSE 1 END),
                last_error = excluded.last_error,
                records_count = data_provider_status.records_count + ?,
                updated_at = CURRENT_TIMESTAMP
        """, (
            pid, operational_status,
            1 if is_healthy else 0,
            1 if is_healthy else 0,
            1 if is_healthy else 0,
            error_message, records_ingested_delta,
            1 if is_healthy else 0,
            1 if is_healthy else 0,
            1 if is_healthy else 0,
            records_ingested_delta
        ))
        conn.commit()


def save_fire_events(events: List[Dict[str, Any]]) -> int:
    """Store clustered fire events."""
    if not events:
        return 0
    saved = 0
    sql = """
        INSERT OR REPLACE INTO fire_events (
            id, centroid_lat, centroid_lng, state, district,
            observation_count, total_frp, max_frp, mean_frp,
            start_time, end_time, classification, classification_confidence,
            radius_km, created_at
        ) VALUES (
            :id, :centroid_lat, :centroid_lng, :state, :district,
            :observation_count, :total_frp, :max_frp, :mean_frp,
            :start_time, :end_time, :classification, :classification_confidence,
            :radius_km, CURRENT_TIMESTAMP
        )
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        for ev in events:
            try:
                record = {
                    "id": ev["id"],
                    "centroid_lat": ev.get("centroid_lat"),
                    "centroid_lng": ev.get("centroid_lon") or ev.get("centroid_lng"),
                    "state": ev.get("state") or "Punjab",
                    "district": ev.get("district") or ev.get("district_id") or "Unknown",
                    "observation_count": ev.get("observation_count", 1),
                    "total_frp": ev.get("total_frp", 0.0),
                    "max_frp": ev.get("max_frp", 0.0),
                    "mean_frp": round(ev.get("total_frp", 0.0) / max(1, ev.get("observation_count", 1)), 2),
                    "start_time": ev.get("first_seen") or ev.get("start_time"),
                    "end_time": ev.get("last_seen") or ev.get("end_time"),
                    "classification": ev.get("classification", "agricultural"),
                    "classification_confidence": ev.get("classification_confidence", 0.8),
                    "radius_km": ev.get("radius_km", 3.5)
                }
                cursor.execute(sql, record)
                saved += cursor.rowcount
            except Exception:
                pass
        conn.commit()
    return saved


def get_fire_events(limit: int = 100) -> List[Dict[str, Any]]:
    """Retrieve clustered fire events."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM fire_events ORDER BY total_frp DESC LIMIT ?", (limit,))
        return [dict(row) for row in cursor.fetchall()]


def get_alert_records(status: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieve lifecycle-managed alert records."""
    sql = "SELECT * FROM alert_records"
    params = []
    if status:
        sql += " WHERE status = ?"
        params.append(status)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]


def insert_alert_record(alert: Dict[str, Any]) -> bool:
    """Insert a new alert record if not already existing."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO alert_records (
                id, category, severity, title, message,
                state, district, trigger_condition, status, created_at
            ) VALUES (
                :id, :category, :severity, :title, :message,
                :state, :district, :trigger_condition, 'NEW', CURRENT_TIMESTAMP
            )
        """, alert)
        conn.commit()
        return cursor.rowcount > 0


def update_alert_record_status(alert_id: str, new_status: str, notes: Optional[str] = None) -> bool:
    """Update lifecycle status of an alert record."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE alert_records 
            SET status = ?, 
                acknowledged_at = CASE WHEN ? = 'ACKNOWLEDGED' AND acknowledged_at IS NULL THEN CURRENT_TIMESTAMP ELSE acknowledged_at END,
                resolved_at = CASE WHEN ? = 'RESOLVED' THEN CURRENT_TIMESTAMP ELSE resolved_at END,
                resolution_notes = COALESCE(?, resolution_notes)
            WHERE id = ?
        """, (new_status, new_status, new_status, notes, alert_id))
        conn.commit()
        return cursor.rowcount > 0


# ============================================================================
# PRODUCTION LIFECYCLE: BOOTSTRAP, VALIDATION, BACKUP, RETENTION
# ============================================================================
#
# The repo layout keeps schema.sql / init_db.py next to the DEFAULT database
# file, while a deployment points DB_PATH at a mounted volume (e.g.
# /var/data/agri_smoke.db). Resolve the DDL/seed sources from the CODE location,
# never from DB_PATH's parent, or a volume-mounted production DB would look for
# schema.sql inside the data directory and fail to start.

_DB_ASSETS_DIR = Path(__file__).resolve().parent.parent / "database"
SCHEMA_PATH = _DB_ASSETS_DIR / "schema.sql"
INIT_SCRIPT_PATH = _DB_ASSETS_DIR / "init_db.py"


def _backup_dir() -> Path:
    """Backup destination: BACKUP_DIR env, else a backups/ folder beside the DB."""
    override = os.getenv("BACKUP_DIR", "").strip()
    return Path(override).expanduser() if override else DB_PATH.parent / "backups"


def ensure_db_parent_dir() -> Path:
    """Create the directory that must hold the database file.

    Required for Render persistent disks: /var/data exists but is empty on first
    deploy, and sqlite3 refuses to create a file in a missing directory
    ("unable to open database file").
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return DB_PATH


def list_tables(conn: sqlite3.Connection) -> List[str]:
    return [r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()]


def missing_tables(conn: sqlite3.Connection) -> List[str]:
    present = set(list_tables(conn))
    return [t for t in REQUIRED_TABLES if t not in present]


def apply_schema(conn: sqlite3.Connection) -> None:
    """Create any missing tables from schema.sql (all DDL is IF NOT EXISTS)."""
    if not SCHEMA_PATH.exists():
        raise RuntimeError(f"schema.sql not found at {SCHEMA_PATH}")
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()


def apply_indexes() -> int:
    """Create the performance indexes. Idempotent, so safe on every boot."""
    created = 0
    with get_connection() as conn:
        for ddl in INDEX_DDL:
            conn.execute(ddl)
            created += 1
        conn.commit()
    return created


def verify_integrity() -> str:
    """PRAGMA integrity_check. Returns 'ok' or the reported problem."""
    with get_connection() as conn:
        row = conn.execute("PRAGMA integrity_check").fetchone()
    return str(row[0]) if row else "no-result"


def _is_unseeded(conn: sqlite3.Connection) -> bool:
    """True when reference data is absent, i.e. a brand-new volume-mounted DB."""
    try:
        stations = conn.execute("SELECT COUNT(*) FROM monitoring_stations").fetchone()[0]
        grap = conn.execute("SELECT COUNT(*) FROM grap_stages").fetchone()[0]
    except sqlite3.Error:
        return True
    return stations == 0 and grap == 0


def _run_seeder() -> None:
    """Seed reference data through the existing database/init_db.py.

    Loaded by file path because database/ is a plain directory, not an importable
    package, and backend/database.py is what 'import database' already resolves
    to. One source of truth for seed rows, so bootstrap can never drift from the
    initializer.
    """
    import importlib.util

    if not INIT_SCRIPT_PATH.exists():
        raise RuntimeError(f"init_db.py not found at {INIT_SCRIPT_PATH}")
    spec = importlib.util.spec_from_file_location("agrismoke_init_db", INIT_SCRIPT_PATH)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError(f"cannot load initializer from {INIT_SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.init_database()


def runtime_diagnostics() -> Dict[str, Any]:
    """Snapshot of the live database configuration. Logged at startup and
    asserted by the Phase 2 regression tests."""
    info: Dict[str, Any] = {
        "db_path": str(DB_PATH),
        "exists": DB_PATH.exists(),
        "size_bytes": DB_PATH.stat().st_size if DB_PATH.exists() else 0,
        "busy_timeout_ms": BUSY_TIMEOUT_MS,
        "wal_requested": WAL_ENABLED,
        "sqlite_version": sqlite3.sqlite_version,
    }
    for sidecar in ("-wal", "-shm"):
        p = Path(str(DB_PATH) + sidecar)
        info[f"sidecar{sidecar}_present"] = p.exists()
    if DB_PATH.exists():
        with get_connection() as conn:
            info["journal_mode"] = conn.execute("PRAGMA journal_mode").fetchone()[0]
            info["synchronous"] = conn.execute("PRAGMA synchronous").fetchone()[0]
            info["foreign_keys"] = conn.execute("PRAGMA foreign_keys").fetchone()[0]
            info["page_size"] = conn.execute("PRAGMA page_size").fetchone()[0]
            info["tables"] = sorted(list_tables(conn))
            info["missing_tables"] = missing_tables(conn)
            info["indexes"] = [
                r["name"] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%' ORDER BY name"
                ).fetchall()
            ]
    return info


def ensure_ready(seed_if_empty: bool = True) -> Dict[str, Any]:
    """Validate (and if necessary build) the production database. Safe to call
    on every boot; never modifies existing rows.

    Order matters: create the directory, then the file/schema, then indexes,
    then WAL (a journal-mode change must not race table creation), then optional
    seeding of a brand-new volume, and finally an integrity check.

    Raises only when the database is genuinely unusable (missing/unwritable
    directory, missing schema.sql, corrupt file) so a broken deployment fails
    fast and loudly instead of returning 500s per request.
    """
    ensure_db_parent_dir()
    created_new = not DB_PATH.exists()

    with get_connection() as conn:
        apply_schema(conn)

    apply_indexes()
    _try_enable_wal()

    seeded = False
    if seed_if_empty:
        with get_connection() as conn:
            needs_seed = created_new or _is_unseeded(conn)
        if needs_seed:
            logger.warning("Database at %s has no reference data - seeding via %s", DB_PATH, INIT_SCRIPT_PATH)
            _run_seeder()
            apply_indexes()
            seeded = True

    with get_connection() as conn:
        still_missing = missing_tables(conn)
    if still_missing:
        raise RuntimeError(f"Database validation failed - missing tables after bootstrap: {still_missing}")

    integrity = verify_integrity()
    if integrity != "ok":
        raise RuntimeError(f"Database integrity check failed: {integrity}")

    diag = runtime_diagnostics()
    diag["created_new_file"] = created_new
    diag["seeded"] = seeded
    logger.info(
        "SQLite ready: %s (journal=%s, busy_timeout=%sms, foreign_keys=%s, tables=%d, size=%.1f MB)",
        DB_PATH, diag.get("journal_mode"), BUSY_TIMEOUT_MS, diag.get("foreign_keys"),
        len(diag.get("tables", [])), diag.get("size_bytes", 0) / 1048576.0,
    )
    return diag


# ---------------------------------------------------------------------------
# Online backup / restore
# ---------------------------------------------------------------------------
#
# A plain file copy of a live SQLite database is NOT safe: with WAL the newest
# committed rows may still be sitting in the -wal sidecar, and copying mid-write
# can capture a torn page. sqlite3's backup API reads through the database
# engine, so it produces a consistent snapshot while ingestion and API traffic
# continue.

_BACKUPABLE_TABLES = (
    "monitoring_stations", "fire_observations", "fire_events", "alert_records",
    "data_sync_jobs", "simulation_history", "districts",
)


def _connect_for_admin(path: Path, readonly: bool = False) -> sqlite3.Connection:
    # The URI must be parsed (uri=True) only in the readonly case, where the
    # path is a "file:...?mode=ro" URI; otherwise the whole string would be
    # treated as a literal filename and the open would fail.
    conn_str = f"file:{Path(path).as_posix()}?mode=ro" if readonly else str(path)
    conn = sqlite3.connect(conn_str, uri=readonly, timeout=BUSY_TIMEOUT_MS / 1000.0)
    conn.row_factory = sqlite3.Row
    return conn


def backup_database(dest_dir: Optional[str] = None, label: Optional[str] = None) -> Dict[str, Any]:
    """Take a consistent online snapshot of the database.

    Returns metadata including the destination path, size, integrity verdict and
    per-table row counts, so an operator (or a scheduled job) can tell that the
    backup actually captured data.
    """
    if not DB_PATH.exists():
        raise RuntimeError(f"Nothing to back up - database file {DB_PATH} does not exist")

    target_dir = Path(dest_dir).expanduser() if dest_dir else _backup_dir()
    target_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    tag = f"-{label}" if label else ""
    dest_path = target_dir / f"{DB_PATH.stem}{tag}-{stamp}.db"

    source = _connect_for_admin(DB_PATH)
    try:
        destination = _connect_for_admin(dest_path)
        try:
            source.backup(destination)          # instance = source, arg = target
            integrity = destination.execute("PRAGMA integrity_check").fetchone()[0]
            counts = {}
            for table in _BACKUPABLE_TABLES:
                try:
                    counts[table] = destination.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                except sqlite3.Error:
                    counts[table] = None
            destination.commit()
        finally:
            destination.close()
    finally:
        source.close()

    if str(integrity) != "ok":
        dest_path.unlink(missing_ok=True)
        raise RuntimeError(f"Backup failed integrity check and was discarded: {integrity}")

    result = {
        "backup_path": str(dest_path),
        "size_bytes": dest_path.stat().st_size,
        "integrity": str(integrity),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_db": str(DB_PATH),
        "table_counts": counts,
        "total_rows": sum(v for v in counts.values() if isinstance(v, int)),
    }
    logger.info("Backup written to %s (%d rows, %.1f MB)", dest_path, result["total_rows"],
                result["size_bytes"] / 1048576.0)
    return result


def restore_database(backup_path: str, target_path: Optional[str] = None, confirm: bool = False) -> Dict[str, Any]:
    """Replace a database file with a verified backup.

    Deliberately guarded: the destination is snapshotted first, so a restore can
    always be rolled back, and an existing target requires confirm=True. The copy
    goes through the backup API inside a transaction rather than a file overwrite,
    so a crash mid-restore cannot leave a half-written database.
    """
    source_path = Path(backup_path).expanduser()
    if not source_path.exists():
        raise FileNotFoundError(f"Backup not found: {source_path}")

    target = Path(target_path).expanduser() if target_path else DB_PATH
    if target.exists() and not confirm:
        raise RuntimeError(
            f"Refusing to overwrite existing database {target} without confirm=True. "
            f"Stop the app first (or use a maintenance window), then re-run."
        )
    target.parent.mkdir(parents=True, exist_ok=True)

    preflight = None
    if target.exists():
        preflight = backup_database(dest_dir=str(target.parent / "pre-restore"), label="pre-restore")

    # Validate the backup before touching the live file.
    check = _connect_for_admin(source_path, readonly=True)
    try:
        integrity = check.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        check.close()
    if str(integrity) != "ok":
        raise RuntimeError(f"Backup failed integrity check, restore aborted: {source_path} ({integrity})")

    source = _connect_for_admin(source_path)
    try:
        destination = _connect_for_admin(target)
        try:
            source.backup(destination)
            destination.commit()
            restored_rows = destination.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
            post_integrity = destination.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            destination.close()
    finally:
        source.close()

    if str(post_integrity) != "ok":
        raise RuntimeError(f"Restored database reports integrity problem: {post_integrity}")

    result = {
        "restored_from": str(source_path),
        "target": str(target),
        "tables": restored_rows,
        "integrity": str(post_integrity),
        "pre_restore_snapshot": preflight["backup_path"] if preflight else None,
    }
    logger.info("Restored %s from %s", target, source_path)
    return result


def list_backups(dest_dir: Optional[str] = None) -> List[Dict[str, Any]]:
    """Newest-first inventory of backup snapshots, newest first."""
    target_dir = Path(dest_dir).expanduser() if dest_dir else _backup_dir()
    if not target_dir.exists():
        return []
    items = []
    for p in sorted(target_dir.glob(f"{DB_PATH.stem}-*.db"), reverse=True):
        items.append({"path": str(p), "size_bytes": p.stat().st_size,
                      "modified_at": datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat()})
    return items


def prune_backups(keep: int, dest_dir: Optional[str] = None) -> List[str]:
    """Delete all but the newest `keep` snapshots. keep <= 0 is a no-op.

    Only files matching the '<dbname>-*.db' pattern inside the backup directory
    are ever considered - the live database is never a candidate.
    """
    if keep <= 0:
        return []
    backups = list_backups(dest_dir)
    removed = []
    for entry in backups[keep:]:
        p = Path(entry["path"])
        try:
            target_dir = Path(dest_dir).expanduser() if dest_dir else _backup_dir()
            if target_dir not in p.parents or not p.name.startswith(f"{DB_PATH.stem}-"):
                continue
            p.unlink()
            removed.append(str(p))
        except OSError as exc:  # pragma: no cover - permission/disk edge
            logger.warning("Could not prune backup %s: %s", p, exc)
    return removed


# ---------------------------------------------------------------------------
# Retention / space management
# ---------------------------------------------------------------------------
#
# fire_observations grows with every 3-hourly ingestion (thousands of rows per
# sync on a multi-sensor setup) and simulation_history grows with every public
# /api/predict call. Both are append-only, so without a retention policy the disk
# fills up and SQLite starts failing on the mount.

#: table -> (timestamp column, default retention days). Whitelisted so the
#: pruning helper can never be steered by caller-supplied identifiers.
RETENTION_TARGETS: Dict[str, tuple] = {
    "fire_observations": ("acq_date", 180),
    "fire_events": ("start_time", 180),
    "simulation_history": ("created_at", 90),
    "data_sync_jobs": ("started_at", 90),
}


def prune_aged_data(table: str, retention_days: int, apply_changes: bool = False) -> Dict[str, Any]:
    """Count (and optionally delete) rows older than the retention window.

    Defaults to a dry run: callers must pass apply_changes=True to delete, and
    the recommendation is to take a backup first.
    """
    if table not in RETENTION_TARGETS:
        raise ValueError(f"table must be one of {sorted(RETENTION_TARGETS)}")
    column, default_days = RETENTION_TARGETS[table]
    days = int(retention_days or default_days)
    if days <= 0:
        raise ValueError("retention_days must be a positive number of days")

    # Parameterised date arithmetic; the identifier comes from the whitelist above.
    sql = f'DELETE FROM "{table}" WHERE "{column}" < date(\'now\', ?)'
    count_sql = f'SELECT COUNT(*) FROM "{table}" WHERE "{column}" < date(\'now\', ?)'
    cutoff = f"-{days} days"
    with get_connection() as conn:
        stale = conn.execute(count_sql, (cutoff,)).fetchone()[0]
        total = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        deleted = 0
        if stale and apply_changes:
            conn.execute(sql, (cutoff,))
            deleted = conn.execute("SELECT changes()").fetchone()[0]
    return {
        "table": table,
        "column": column,
        "retention_days": days,
        "rows_total": total,
        "rows_older_than_cutoff": stale,
        "rows_deleted": deleted,
        "applied": bool(apply_changes),
    }


def storage_report() -> Dict[str, Any]:
    """Sizes and row counts per table, plus reclaimable pages."""
    with get_connection() as conn:
        page_size = conn.execute("PRAGMA page_size").fetchone()[0]
        page_count = conn.execute("PRAGMA page_count").fetchone()[0]
        freelist = conn.execute("PRAGMA freelist_count").fetchone()[0]
        tables = {}
        for name in list_tables(conn):
            try:
                tables[name] = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            except sqlite3.Error:
                tables[name] = None
    return {
        "db_path": str(DB_PATH),
        "file_bytes": DB_PATH.stat().st_size if DB_PATH.exists() else 0,
        "page_size": page_size,
        "page_count": page_count,
        "reclaimable_bytes": int(freelist) * int(page_size),
        "table_rows": tables,
    }


def checkpoint_and_optimize(mode: str = "TRUNCATE") -> Dict[str, Any]:
    """Fold the WAL back into the main file and refresh planner statistics.

    TRUNCATE also shrinks the -wal sidecar, which is what keeps a bounded disk
    footprint on a small Render volume after a large ingestion.
    """
    if mode.upper() not in {"PASSIVE", "FULL", "RESTART", "TRUNCATE"}:
        raise ValueError("mode must be PASSIVE, FULL, RESTART or TRUNCATE")
    with get_connection() as conn:
        row = conn.execute(f"PRAGMA wal_checkpoint({mode})").fetchone()
        conn.execute("PRAGMA optimize")
        conn.commit()
    return {
        "mode": mode.upper(),
        # (busy, wal pages before checkpoint, pages moved) - busy=1 means the
        # checkpoint could not complete because a reader held the log open.
        "busy": int(row[0]) if row else None,
        "wal_pages": int(row[1]) if row and row[1] is not None else None,
        "checkpointed_pages": int(row[2]) if row and row[2] is not None else None,
    }


def run_vacuum(reclaim_space: bool = True) -> Dict[str, Any]:
    """Compact the database file. VACUUM needs an exclusive, transaction-free
    connection, so it runs outside get_connection() and should be done in a
    maintenance window rather than while the API is serving."""
    before = DB_PATH.stat().st_size if DB_PATH.exists() else 0
    conn = _connect_for_admin(DB_PATH)
    try:
        if reclaim_space:
            conn.isolation_level = None      # autocommit: VACUUM cannot run in a transaction
            conn.execute("VACUUM")
    finally:
        conn.close()
    after = DB_PATH.stat().st_size if DB_PATH.exists() else 0
    return {"before_bytes": before, "after_bytes": after, "reclaimed_bytes": max(0, before - after)}


# ---------------------------------------------------------------------------
# Scheduled maintenance: disk monitoring, off-site distribution, and the
# backup / retention cycles that the background MaintenanceScheduler drives.
# These are plain functions (safe to call directly), and every value is read
# from the environment AT CALL TIME so a running deployment can be re-tuned
# and tests can patch os.environ without re-importing this module.
# ---------------------------------------------------------------------------

#: Where completed snapshots are ALSO copied so a lost disk is recoverable.
#:   none     - local snapshot only (NOT disaster recovery on its own)
#:   directory- copy to OFFSITE_BACKUP_DIR (a second mounted volume/path)
#:   s3       - upload to an S3-compatible bucket (R2/B2/MinIO/S3) via boto3
OFFSITE_BACKEND_ENV = "OFFSITE_BACKEND"

#: Env key -> default retention days for each whitelisted table. Env override
#: keys are the upper-cased form, e.g. FIRE_OBS_RETENTION_DAYS.
_RETENTION_ENV_KEYS = {
    "fire_observations": ("FIRE_OBS_RETENTION_DAYS", 180),
    "fire_events": ("FIRE_EVENTS_RETENTION_DAYS", 180),
    "simulation_history": ("SIM_HISTORY_RETENTION_DAYS", 90),
    "data_sync_jobs": ("SYNC_JOBS_RETENTION_DAYS", 90),
}


def retention_days_for(table: str) -> int:
    """Configurable per-table retention window (env-overridable)."""
    env_key, default = _RETENTION_ENV_KEYS.get(table, (None, RETENTION_TARGETS.get(table, ("", 180))[1]))
    if env_key:
        return max(1, _get_int(env_key, default))
    return max(1, default)


def backup_retention_keep() -> int:
    """Number of local snapshots to retain (oldest pruned beyond this)."""
    return _get_int("BACKUP_RETENTION_KEEP", 10)


def min_free_mb() -> int:
    """Free-space floor the disk must clear before maintenance is considered safe."""
    return max(0, _get_int("SQLITE_MIN_FREE_MB", 512))


def offsite_configured() -> bool:
    """True when a real off-site destination is selected (not 'none')."""
    return os.getenv(OFFSITE_BACKEND_ENV, "none").strip().lower() in {"directory", "s3"}


def check_disk_space(path: Optional[str] = None) -> Dict[str, Any]:
    """Free/total space for the volume holding the database (or a given path).

    Never raises: if the resolved directory does not exist yet it reports the
    nearest existing ancestor so a pre-bootstrap call still yields a usable
    reading.
    """
    target = Path(path).expanduser() if path else DB_PATH.parent
    probe = target
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    try:
        usage = shutil.disk_usage(str(probe))
    except OSError as exc:  # pragma: no cover - exotic filesystems
        logger.warning("Could not read disk usage for %s: %s", probe, exc)
        return {"path": str(target), "available": False, "ok": True,
                "free_mb": None, "min_free_mb": min_free_mb(), "error": str(exc)}
    free_mb = usage.free / 1048576.0
    floor = min_free_mb()
    return {
        "path": str(target),
        "available": True,
        "free_bytes": usage.free,
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_mb": round(free_mb, 1),
        "min_free_mb": floor,
        "ok": free_mb >= floor,
    }


def _upload_backup_to_s3(src: Path) -> Dict[str, Any]:
    """Optional S3-compatible upload. boto3 is imported lazily so the base app
    has no hard dependency on it (off-site S3 is opt-in)."""
    bucket = os.getenv("OFFSITE_S3_BUCKET", "").strip()
    if not bucket:
        return {"backend": "s3", "delivered": False, "reason": "OFFSITE_S3_BUCKET not set"}
    try:
        import boto3
    except ImportError:
        return {"backend": "s3", "delivered": False,
                "reason": "boto3 not installed; run `pip install boto3` to enable S3 off-site"}
    endpoint = os.getenv("OFFSITE_S3_ENDPOINT", "").strip() or None
    region = os.getenv("OFFSITE_S3_REGION", "").strip() or None
    access_key = os.getenv("OFFSITE_S3_ACCESS_KEY", "").strip() or os.getenv("AWS_ACCESS_KEY_ID", "").strip() or None
    secret_key = os.getenv("OFFSITE_S3_SECRET_KEY", "").strip() or os.getenv("AWS_SECRET_ACCESS_KEY", "").strip() or None
    prefix = os.getenv("OFFSITE_S3_PREFIX", "backups").strip("/") or "backups"
    key = f"{prefix}/{src.name}"
    try:
        client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
        client.upload_file(str(src), bucket, key)
    except Exception as exc:
        # Off-site failure must be REPORTED (delivered=False), never raised over
        # the local snapshot that is already on disk. Echo only the exception
        # class - botocore messages can include the request URL / credential
        # scope, so we deliberately don't include str(exc).
        logger.error("S3 off-site upload failed: %s", type(exc).__name__)
        return {"backend": "s3", "delivered": False,
                "reason": f"S3 upload failed: {type(exc).__name__}"}
    return {"backend": "s3", "delivered": True, "bucket": bucket, "key": key}


def distribute_backup_offsite(backup_path: str) -> Dict[str, Any]:
    """Copy a completed snapshot to the configured off-site destination.

    A local snapshot on the same persistent disk is NOT disaster recovery - if
    the volume dies the backup dies with it. This pushes a copy somewhere
    independent. Integrity is re-verified after a directory copy so a torn
    transfer is caught, never trusted.
    """
    backend = os.getenv(OFFSITE_BACKEND_ENV, "none").strip().lower()
    src = Path(backup_path)
    if backend in ("", "none"):
        return {"backend": backend or "none", "delivered": False, "reason": "off-site disabled"}
    if not src.exists():
        return {"backend": backend, "delivered": False, "reason": f"snapshot missing: {src}"}

    if backend == "directory":
        dest_dir = os.getenv("OFFSITE_BACKUP_DIR", "").strip()
        if not dest_dir:
            return {"backend": "directory", "delivered": False, "reason": "OFFSITE_BACKUP_DIR not set"}
        dest = Path(dest_dir).expanduser()
        try:
            if dest.resolve() == src.parent.resolve():
                return {"backend": "directory", "delivered": False,
                        "reason": "OFFSITE_BACKUP_DIR equals the backup dir - that is not off-site"}
        except OSError:
            pass
        dest.mkdir(parents=True, exist_ok=True)
        target = dest / src.name
        shutil.copy2(src, target)
        check = _connect_for_admin(target, readonly=True)
        try:
            integrity = str(check.execute("PRAGMA integrity_check").fetchone()[0])
        finally:
            check.close()
        if integrity != "ok":
            target.unlink(missing_ok=True)
            return {"backend": "directory", "delivered": False, "reason": f"off-site copy failed integrity: {integrity}"}
        return {"backend": "directory", "delivered": True, "path": str(target), "integrity": integrity}

    if backend == "s3":
        return _upload_backup_to_s3(src)

    return {"backend": backend, "delivered": False, "reason": f"unknown OFFSITE_BACKEND '{backend}'"}


def run_backup_cycle(label: Optional[str] = None, push_offsite: bool = True,
                     prune_old_snapshots: bool = True) -> Dict[str, Any]:
    """One full maintenance backup: monitor disk, snapshot (integrity-checked),
    prune local snapshots to the retention count, then push an off-site copy.

    backup_database() already runs PRAGMA integrity_check on the destination and
    discards a bad snapshot, so a corrupt backup is never reported as success.
    Raises on snapshot failure so the caller (scheduler) logs it redacted;
    off-site delivery failure is reported in the result, not raised, because the
    local snapshot is still valid and should not be lost over a network blip.
    """
    report: Dict[str, Any] = {"ok": True, "steps": []}

    disk = check_disk_space()
    report["disk"] = disk
    if disk.get("available") and not disk.get("ok"):
        logger.warning(
            "Low disk space before backup: %s MB free (minimum %s MB) on %s",
            disk.get("free_mb"), disk.get("min_free_mb"), disk.get("path"),
        )

    info = backup_database(label=label)          # integrity verified inside
    report["backup"] = info
    report["steps"].append("snapshot")

    if prune_old_snapshots:
        keep = backup_retention_keep()
        if keep > 0:
            report["pruned"] = prune_backups(keep=keep)
            report["steps"].append("prune")

    if push_offsite:
        off = distribute_backup_offsite(info["backup_path"])
        report["offsite"] = off
        report["steps"].append("offsite")
        if offsite_configured() and not off.get("delivered"):
            report["ok"] = False
            logger.error("Backup snapshot OK but off-site delivery failed: %s", off.get("reason"))

    return report


def run_retention_cycle(apply_changes: bool = False, backup_first: bool = True,
                        tables: Optional[List[str]] = None) -> Dict[str, Any]:
    """Prune aged rows from the whitelisted historical tables.

    Safety: when actually deleting (apply_changes=True) a fresh backup is taken
    first (backup_first) so destructive maintenance is always recoverable. Only
    tables present in RETENTION_TARGETS are eligible - the whitelist makes it
    impossible to steer the DELETE at an operational table by accident. Runs on
    the single maintenance thread and through get_connection(), so it serializes
    behind any in-flight ingestion write rather than conflicting with it.
    """
    eligible = [t for t in (tables or list(RETENTION_TARGETS)) if t in RETENTION_TARGETS]
    rejected = [t for t in (tables or []) if t not in RETENTION_TARGETS]

    pre_backup = None
    if apply_changes and backup_first:
        try:
            pre_backup = run_backup_cycle(label="pre-retain")
        except Exception as exc:
            # A snapshot failure (corrupt destination, disk full, DB missing)
            # must NEVER be followed by a destructive prune: abort and let the
            # operator see why via the returned report.
            logger.error("Pre-retention backup raised; deletion aborted: %s", type(exc).__name__)
            return {
                "applied": False,
                "aborted": True,
                "reason": "pre_retention_backup_error",
                "error": type(exc).__name__,
                "eligible_tables": eligible,
                "rejected_tables": rejected,
                "pre_retention_backup": None,
                "tables": {},
            }
        if not pre_backup.get("ok") or not pre_backup.get("backup"):
            # Local snapshot succeeded but the cycle reported incomplete (e.g.,
            # off-site configured and delivery failed). Under an opt-in apply
            # mode we treat any non-ok pre-retain cycle as unsafe and abort.
            logger.error("Pre-retention backup incomplete; deletion aborted")
            return {
                "applied": False,
                "aborted": True,
                "reason": "pre_retention_backup_incomplete",
                "eligible_tables": eligible,
                "rejected_tables": rejected,
                "pre_retention_backup": pre_backup.get("backup"),
                "tables": {},
            }

    results: Dict[str, Any] = {}
    for table in eligible:
        days = retention_days_for(table)
        results[table] = prune_aged_data(table, days, apply_changes=apply_changes)

    return {
        "applied": bool(apply_changes),
        "eligible_tables": eligible,
        "rejected_tables": rejected,
        "pre_retention_backup": (pre_backup.get("backup") if pre_backup else None),
        "tables": results,
    }




