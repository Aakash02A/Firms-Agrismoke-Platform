"""
AgriSmoke AI - Live Air Quality Ingestion Service
Fetches real-time particulate matter (PM2.5 / PM10) concentrations for any
coordinate from the Open-Meteo Air Quality API (free, no API key), converts
them to the Indian CPCB AQI scale, and enriches monitoring-station records
with live readings. Includes an in-memory TTL cache and graceful fallback.

This replaces the previously hardcoded/mock station AQI values with genuine
live sensor-modelled air quality data.
"""

import time
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List

import requests

logger = logging.getLogger("agri_smoke.air_quality")

AIR_QUALITY_API_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

# Compact CPCB PM2.5 breakpoints, used ONLY as a last-resort fallback if the
# canonical model_inference engine cannot be imported. Mirrors CPCB_BREAKPOINTS.
_FALLBACK_CPCB_BREAKPOINTS = [
    {"bpLow": 0, "bpHigh": 30, "iLow": 0, "iHigh": 50},
    {"bpLow": 31, "bpHigh": 60, "iLow": 51, "iHigh": 100},
    {"bpLow": 61, "bpHigh": 90, "iLow": 101, "iHigh": 200},
    {"bpLow": 91, "bpHigh": 120, "iLow": 201, "iHigh": 300},
    {"bpLow": 121, "bpHigh": 250, "iLow": 301, "iHigh": 400},
    {"bpLow": 251, "bpHigh": 350, "iLow": 401, "iHigh": 450},
    {"bpLow": 351, "bpHigh": 500, "iLow": 451, "iHigh": 500},
]

# Reuse the canonical CPCB AQI + category engine from the ML module when possible.
try:
    from model_inference import predictor as _predictor
except Exception:  # pragma: no cover - depends on sys.path setup by entry point
    _predictor = None


def _cpcb_aqi_from_pm25(pm25: float) -> int:
    """Convert PM2.5 (ug/m3) to Indian CPCB AQI. Prefers the shared ML engine."""
    if _predictor is not None and hasattr(_predictor, "calculate_aqi_from_pm25"):
        return int(_predictor.calculate_aqi_from_pm25(pm25))
    if pm25 <= 0:
        return 0
    for bp in _FALLBACK_CPCB_BREAKPOINTS:
        if bp["bpLow"] <= pm25 <= bp["bpHigh"]:
            aqi = ((bp["iHigh"] - bp["iLow"]) / (bp["bpHigh"] - bp["bpLow"])) * (pm25 - bp["bpLow"]) + bp["iLow"]
            return round(aqi)
    highest = _FALLBACK_CPCB_BREAKPOINTS[-1]
    overflow = (pm25 - highest["bpHigh"]) * 0.8
    return min(999, round(highest["iHigh"] + overflow))


def _category_for_aqi(aqi: int) -> str:
    """Return the CPCB category label for an AQI value."""
    if _predictor is not None and hasattr(_predictor, "get_category_for_aqi"):
        return _predictor.get_category_for_aqi(aqi)["category"]
    if aqi <= 50:
        return "Good"
    if aqi <= 100:
        return "Satisfactory"
    if aqi <= 200:
        return "Moderate"
    if aqi <= 300:
        return "Poor"
    if aqi <= 400:
        return "Very Poor"
    if aqi <= 450:
        return "Severe"
    return "Severe+ / Emergency"


class AirQualityService:
    """Live air-quality client with caching and thread-safe enrichment."""

    def __init__(self, cache_ttl_seconds: int = 900):
        self.cache_ttl = cache_ttl_seconds
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_time: Dict[str, float] = {}
        self._forecast_cache: Dict[str, Any] = {}
        self._forecast_cache_time: Dict[str, float] = {}
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "AgriSmoke-AI/2.0 (Open-Meteo Air Quality Ingestion)"
        })

    def _cache_key(self, lat: float, lng: float) -> str:
        return f"{round(lat, 3)},{round(lng, 3)}"

    def get_live_reading(self, lat: float, lng: float) -> Optional[Dict[str, Any]]:
        """
        Fetch live PM2.5/PM10 for a coordinate and convert to CPCB AQI.
        Returns None on failure (caller should then fall back to stored/mock values).
        """
        key = self._cache_key(lat, lng)
        now = time.time()
        cached = self._cache.get(key)
        if cached and (now - self._cache_time.get(key, 0)) < self.cache_ttl:
            return cached

        try:
            params = {
                "latitude": lat,
                "longitude": lng,
                "current": "pm2_5,pm10",
                "timezone": "Asia/Kolkata",
            }
            resp = self.session.get(AIR_QUALITY_API_URL, params=params, timeout=10)
            if resp.status_code != 200:
                logger.warning("Open-Meteo Air Quality returned HTTP %s for %s", resp.status_code, key)
                return None

            current = resp.json().get("current", {})
            pm25 = current.get("pm2_5")
            pm10 = current.get("pm10")
            if pm25 is None:
                logger.warning("Open-Meteo Air Quality missing pm2_5 for %s", key)
                return None

            pm25 = float(pm25)
            pm10 = float(pm10) if pm10 is not None else round(pm25 * 1.9, 1)
            aqi = _cpcb_aqi_from_pm25(pm25)

            reading = {
                "pm25": round(pm25, 1),
                "pm10": round(pm10, 1),
                "aqi": aqi,
                "category": _category_for_aqi(aqi),
                "source": "OPEN_METEO_AIR_QUALITY_LIVE",
                "isLive": True,
                "timestamp": current.get("time") or datetime.now(timezone.utc).isoformat(),
            }
            self._cache[key] = reading
            self._cache_time[key] = now
            return reading

        except Exception as e:  # network, JSON, or conversion error
            logger.warning("Live air quality fetch failed for %s: %s", key, e)
            return None

    def get_forecast_hours(self, lat: float, lng: float, hours: int = 72) -> List[Dict[str, Any]]:
        """
        Fetch a real per-location hourly PM2.5 -> CPCB AQI forecast for the next
        `hours` from Open-Meteo Air Quality, starting at the current IST hour.
        Returns a list of {"time", "hourLabel", "dayLabel", "aqi", "pm25", "category"},
        or [] on failure so the caller can degrade gracefully.
        """
        key = self._cache_key(lat, lng) + f":fc:{hours}"
        now = time.time()
        cached = self._forecast_cache.get(key)
        if cached and (now - self._forecast_cache_time.get(key, 0)) < self.cache_ttl:
            return cached

        try:
            params = {
                "latitude": lat,
                "longitude": lng,
                "hourly": "pm2_5,pm10",
                "forecast_days": 3,
                "timezone": "Asia/Kolkata",
            }
            resp = self.session.get(AIR_QUALITY_API_URL, params=params, timeout=12)
            if resp.status_code != 200:
                logger.warning("Open-Meteo AQI forecast returned HTTP %s for %s", resp.status_code, key)
                return []

            hourly = resp.json().get("hourly", {})
            times = hourly.get("time", [])
            pm25s = hourly.get("pm2_5", [])
            if not times:
                return []

            # Align to the current hour in IST (Open-Meteo returns local IST strings).
            ist = timezone(timedelta(hours=5, minutes=30))
            start_str = datetime.now(ist).strftime("%Y-%m-%dT%H:00")
            start_idx = next((i for i, t in enumerate(times) if t >= start_str), 0)

            out: List[Dict[str, Any]] = []
            for i in range(start_idx, min(start_idx + hours, len(times))):
                pm = pm25s[i] if i < len(pm25s) else None
                if pm is None:
                    continue
                pm = float(pm)
                aqi = _cpcb_aqi_from_pm25(pm)
                t = times[i]
                out.append({
                    "time": t,
                    "hourLabel": t[11:16],
                    "dayLabel": t[:10],
                    "aqi": aqi,
                    "pm25": round(pm, 1),
                    "category": _category_for_aqi(aqi),
                })

            if out:
                self._forecast_cache[key] = out
                self._forecast_cache_time[key] = now
                return out
            logger.warning("Open-Meteo AQI forecast had no usable rows for %s", key)
        except Exception as e:  # network / JSON / conversion
            logger.warning("Live AQI forecast fetch failed for %s: %s", key, e)

        return []

    def enrich_stations(self, stations: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Overlay live PM2.5/PM10/AQI onto station dicts (mutates in place).
        Stations with lat/lng are fetched concurrently; failures keep existing values.
        Returns {"live": n, "fallback": m} counts for provider-status reporting.
        """
        live = 0
        fallback = 0
        targets = [s for s in stations if s.get("lat") is not None and s.get("lng") is not None]

        def apply(station: Dict[str, Any], reading: Optional[Dict[str, Any]]) -> None:
            nonlocal live, fallback
            if reading:
                station["aqi"] = reading["aqi"]
                station["category"] = reading["category"]
                station["pm25"] = reading["pm25"]
                station["pm10"] = reading["pm10"]
                station["live"] = True
                station["liveTimestamp"] = reading["timestamp"]
                live += 1
            else:
                station["live"] = False
                fallback += 1

        with ThreadPoolExecutor(max_workers=min(4, max(1, len(targets)))) as pool:
            futures = {pool.submit(self.get_live_reading, s["lat"], s["lng"]): s for s in targets}
            for fut in futures:
                station = futures[fut]
                try:
                    apply(station, fut.result())
                except Exception:
                    apply(station, None)

        # Sort by live AQI descending so the worst station leads (matches UI expectation)
        stations.sort(key=lambda s: s.get("aqi", 0), reverse=True)
        return {"live": live, "fallback": fallback}


# Global service instance
air_quality_service = AirQualityService()
