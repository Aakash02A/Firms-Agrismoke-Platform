"""
AgriSmoke AI - On-Demand NASA FIRMS Live Snapshot (stateless read path)

Public/stateless deployments run NO background scheduler, so the ingestion
that normally keeps ``fire_observations`` fresh does not happen. This module
lets the read-only dashboard endpoints (fire hotspots, district counts, and the
map's point-level observations) fetch a LIVE NASA FIRMS snapshot on demand
WITHOUT writing anything to the database, so the deployment stays stateless and
no unauthenticated request can mutate the public database.

Safety within free-tier outbound limits:
  * short-lived in-memory TTL cache (default 15m) - the number of NASA calls is
    bounded by elapsed time, NOT by visitor traffic;
  * single-flight refresh - concurrent requests never fan out to NASA; exactly
    one request does the fetch while the others are served the last snapshot
    (even if momentarily stale), so a traffic spike cannot hammer the API;
  * fail-soft - unconfigured MAP_KEY, network/parse errors or an empty feed all
    return an empty result so the caller transparently falls back to the
    seeded reference data. Nothing here can raise into the request handler.

It reuses the exact client / parser / normalizer already used (and tested) by
the scheduled ingestion path, so live results are identical in shape to
``database.get_live_fire_hotspots()`` / ``get_live_district_fire_counts()`` and
the frontend needs no changes.
"""

import os
import time
import logging
import threading
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from .config import FirmsConfig
from .client import NasaFirmsClient
from .parser import parse_firms_csv
from .normalizer import normalize_observation
from .classifier import classify_fire_observation, haversine_km

try:
    from backend import database
except ImportError:  # pragma: no cover - supports flat/direct imports
    import database as database

logger = logging.getLogger("agri_smoke.firms.on_demand")

# Proximity threshold (km) for associating a detection with a district centroid,
# mirroring the scheduled ingestion service so live and stored data agree.
_DISTRICT_MATCH_KM = 35.0

# In-memory snapshot cache. ``_data`` is (hotspots, district_counts, observations)
# or None.
_data: Optional[Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]] = None
_expires_at: float = 0.0
_read_lock = threading.Lock()        # guards _data / _expires_at
_fetch_lock = threading.Lock()       # single-flight: one refresh at a time


def _ttl_seconds() -> int:
    """Cache lifetime, read at call time so operators can retune via env."""
    try:
        return max(60, int(str(os.getenv("FIRMS_ON_DEMAND_TTL_SECONDS", "900")).strip()))
    except (TypeError, ValueError):
        return 900


def _smoke_intensity(count: int) -> str:
    if count >= 300:
        return "Very High"
    if count >= 150:
        return "High"
    if count >= 60:
        return "Moderate"
    return "Low"


def _match_district(lat: float, lon: float, districts: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Nearest district centroid within the proximity threshold, or None."""
    best = None
    min_dist = _DISTRICT_MATCH_KM
    for d in districts:
        c_lat = d.get("center_lat")
        c_lon = d.get("center_lon")
        if c_lat is None or c_lon is None:
            continue
        dist = haversine_km(lat, lon, float(c_lat), float(c_lon))
        if dist < min_dist:
            min_dist = dist
            best = d
    return best


def _build_snapshot() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Fetch + aggregate a fresh FIRMS snapshot. Raises on provider failure;
    callers must not let that reach the request handler.

    Returns (hotspots, district_counts, observations). The first two back the
    /api/hotspots and /api/districts endpoints; the third is a point-level,
    DB-shaped list (mirroring database.get_fire_observations output) so the
    map can render LIVE detections on a stateless deploy with an empty DB
    instead of silently falling back to the seeded demo hotspots."""
    config = FirmsConfig()
    if not config.is_configured:
        # MAP_KEY absent: signal "no live data" so the caller uses fallback.
        return [], [], []

    client = NasaFirmsClient(config)
    csv_data = client.get_area_observations_csv()   # defaults: region + sensor + range from config
    raw_rows, _rejected = parse_firms_csv(csv_data)
    if not raw_rows:
        return [], [], []

    districts = database.get_districts()

    # Aggregate by matched district: count, mean FRP, centroid, mean confidence.
    # Also emit a point-level, DB-compatible observation list for the map.
    grouped: Dict[str, Dict[str, Any]] = {}
    observations: List[Dict[str, Any]] = []
    for row in raw_rows:
        obs = normalize_observation(row, source_dataset=config.default_sensor)
        match = _match_district(obs["latitude"], obs["longitude"], districts)
        name = match["name"] if match else "Regional Airshed"
        state = match["state"] if match else "North India"

        # Apply the same agricultural/industrial/forest classification the
        # scheduled ingestion uses, so live and stored map points agree.
        clf = classify_fire_observation(obs, match)
        conf_norm = float(obs.get("confidence_normalized") or 0.6)

        g = grouped.get(name)
        if g is None:
            g = grouped[name] = {"state": state, "count": 0, "frp": 0.0,
                                 "lat": 0.0, "lng": 0.0, "conf": 0.0}
        g["count"] += 1
        g["frp"] += float(obs.get("frp") or 0.0)
        g["lat"] += float(obs["latitude"])
        g["lng"] += float(obs["longitude"])
        g["conf"] += conf_norm

        observations.append({
            "id": obs["id"],
            "latitude": obs["latitude"],
            "longitude": obs["longitude"],
            "frp": obs.get("frp", 0.0),
            "satellite": obs.get("satellite"),
            "instrument": obs.get("instrument"),
            "acq_date": obs.get("acq_date"),
            "acq_time": obs.get("acq_time"),
            "acquisition_timestamp": obs.get("acquisition_timestamp"),
            "confidence": obs.get("confidence_raw") or "nominal",
            "confidence_score": conf_norm,
            "confidence_normalized": conf_norm,
            "state": state,
            "district": name,
            "district_id": name,
            "classification": clf["classification"],
            "classification_confidence": clf["classification_confidence"],
            "daynight": obs.get("day_night", "D"),
            "live": True,
            "source": "NASA_FIRMS_ON_DEMAND",
        })

    hotspots: List[Dict[str, Any]] = []
    counts: List[Dict[str, Any]] = []
    for name, g in grouped.items():
        c = g["count"]
        avg_frp = round(g["frp"] / c, 1)
        intensity = _smoke_intensity(c)
        slug = name.lower().replace(" ", "_")
        hotspots.append({
            "id": f"ondemand_{slug}",
            "district": name,
            "state": g["state"],
            "lat": round(g["lat"] / c, 4),
            "lng": round(g["lng"] / c, 4),
            "fire_count": c,
            "avg_frp": avg_frp,
            "status": "Live satellite detection",
            "harvest_progress": "Live (FIRMS)",
            "confidence": f"{round(g['conf'] / c * 100)}% (VIIRS)",
            "smoke_intensity": intensity,
            "fireCount": c,
            "avgFRP": avg_frp,
            "harvestProgress": "Live (FIRMS)",
            "smokeIntensity": intensity,
            "live": True,
            "source": "NASA_FIRMS_ON_DEMAND",
            "latestAcquisition": None,
        })
        counts.append({"district": name, "state": g["state"], "fires": c})

    hotspots.sort(key=lambda h: h["fire_count"], reverse=True)
    counts.sort(key=lambda d: d["fires"], reverse=True)
    observations.sort(key=lambda o: o.get("acquisition_timestamp") or "", reverse=True)
    return hotspots, counts, observations


def _snapshot() -> Optional[Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]]:
    """Return the cached snapshot, refreshing it at most once per TTL via a
    single-flight guard. Never raises; returns the last known (possibly stale)
    snapshot on any failure so the caller can fall through to seed data."""
    global _data, _expires_at
    now = time.time()

    with _read_lock:
        cached, fresh = _data, now < _expires_at
    if cached is not None and fresh:
        return cached

    # Only one request per TTL window performs the network fetch. If another is
    # already fetching, serve the current (possibly stale) data without piling up.
    if _fetch_lock.acquire(blocking=False):
        try:
            with _read_lock:
                if _data is not None and time.time() < _expires_at:
                    return _data            # double-checked: refreshed meanwhile
            try:
                built = _build_snapshot()
            except Exception as exc:
                # Log only the exception class + redacted message; never the URL.
                logger.warning("On-demand FIRMS snapshot failed (%s); serving last known data",
                               type(exc).__name__)
                with _read_lock:
                    return _data
            with _read_lock:
                _data = built
                _expires_at = time.time() + _ttl_seconds()
            return built
        finally:
            _fetch_lock.release()

    with _read_lock:
        return _data


def get_live_hotspots() -> List[Dict[str, Any]]:
    """On-demand live fire hotspots, or [] when unavailable (caller falls back)."""
    snap = _snapshot()
    return snap[0] if snap else []


def get_live_district_counts() -> List[Dict[str, Any]]:
    """On-demand live district fire counts, or [] when unavailable."""
    snap = _snapshot()
    return snap[1] if snap else []


def get_live_observations(limit: int = 1000) -> List[Dict[str, Any]]:
    """On-demand live point-level fire detections, or [] when unavailable.

    Backs the map's /api/v1/firms/observations read path on a stateless deploy
    where the ``fire_observations`` table is empty (no ingestion scheduler). The
    rows mirror database.get_fire_observations output so the frontend map needs
    no changes; when this returns [] the caller falls back to seeded data."""
    snap = _snapshot()
    if not snap or len(snap) < 3:
        return []
    return snap[2][:max(1, limit)]
