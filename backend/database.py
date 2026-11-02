"""
AgriSmoke AI - Database Access Layer
Provides clean CRUD helpers and queries for the SQLite database.
"""

import os
import sqlite3
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

# Default to the repo-local SQLite file, but allow an env override (DB_PATH) so
# PaaS/container deployments can point the database at a mounted, persistent
# volume instead of the ephemeral app directory.
_default_db = Path(__file__).resolve().parent.parent / "database" / "agri_smoke.db"
DB_PATH = Path(os.getenv("DB_PATH", "").strip()).expanduser() if os.getenv("DB_PATH", "").strip() else _default_db


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

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
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT aqi_threshold, fires_threshold FROM custom_thresholds WHERE id = 1")
        row = cursor.fetchone()
        if row:
            return {"aqi": row["aqi_threshold"], "fires": row["fires_threshold"]}
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

