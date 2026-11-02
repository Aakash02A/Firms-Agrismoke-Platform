"""
AgriSmoke AI - Live Meteorological Ingestion Service
Queries Open-Meteo API for real-time wind, temperature, relative humidity,
and planetary boundary layer (PBL) height across Delhi-NCR and the Punjab agricultural corridor.
Includes in-memory TTL caching and calibrated seasonal fallback.
"""

import time
import math
import logging
from typing import Dict, Any
from datetime import datetime, timezone
import requests
from pydantic import BaseModel, Field

logger = logging.getLogger("agri_smoke.weather")

# Indo-Gangetic Reference Locations
LOCATIONS = {
    "delhi_ncr": {"lat": 28.6139, "lng": 77.2090, "name": "Delhi-NCR Central"},
    "punjab_source": {"lat": 30.9010, "lng": 75.8573, "name": "Punjab Farm Belt (Ludhiana/Sangrur)"},
    "haryana_transit": {"lat": 29.6857, "lng": 76.9905, "name": "Haryana Airshed Transit (Karnal)"}
}

DEFAULT_SEASONAL_FALLBACK = {
    "temperature": 24.2,
    "humidity": 62.0,
    "windSpeed": 11.5,
    "windDirectionDeg": 305,
    "pblHeight": 480,
    "surfacePressure": 1012.5,
    "source": "SEASONAL_CALIBRATED_FALLBACK",
    "location": "Delhi-NCR Central",
    "ventilationIndex": 1533,
    "inversionRisk": "MODERATE",
    "corridorAlignmentPct": 98.2,
    "isLive": False,
    "timestamp": datetime.now(timezone.utc).isoformat()
}


class LiveWeatherSnapshot(BaseModel):
    temperature: float = Field(description="Ambient temperature in °C")
    humidity: float = Field(description="Relative humidity %")
    windSpeed: float = Field(description="Wind speed at 10m in km/h")
    windDirectionDeg: int = Field(description="Wind direction in degrees (0-360)")
    pblHeight: int = Field(description="Planetary Boundary Layer height in meters")
    surfacePressure: float = Field(description="Surface atmospheric pressure in hPa")
    source: str = Field(description="Data provider source name")
    location: str = Field(description="Geographic reference location")
    ventilationIndex: int = Field(description="Ventilation Index (wind speed m/s * PBL height)")
    inversionRisk: str = Field(description="Atmospheric inversion trapping risk: LOW, MODERATE, HIGH")
    corridorAlignmentPct: float = Field(description="Alignment with NW stubble transport corridor (312°)")
    isLive: bool = Field(description="True if live API data, False if seasonal fallback")
    timestamp: str = Field(description="ISO-8601 timestamp")


class WeatherService:
    def __init__(self, cache_ttl_seconds: int = 900):
        self.cache_ttl: int = cache_ttl_seconds
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_time: Dict[str, float] = {}
        self._forecast_cache: Dict[str, Any] = {}
        self._forecast_cache_time: Dict[str, float] = {}
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "AgriSmoke-AI/2.0 (Open-Meteo Environmental Weather Ingestion)"})

    def _compute_airshed_metrics(self, wind_speed_kmh: float, wind_dir_deg: int, pbl_height: int) -> Dict[str, Any]:
        """Calculates ventilation index, corridor alignment, and inversion risk."""
        wind_speed_ms = max(0.5, wind_speed_kmh / 3.6)
        ventilation_index = int(round(wind_speed_ms * max(100, pbl_height)))

        # Inversion risk based on nocturnal boundary layer trapping
        if pbl_height <= 250:
            inversion_risk = "EXTREME_TRAPPING"
        elif pbl_height <= 400:
            inversion_risk = "HIGH"
        elif pbl_height <= 650:
            inversion_risk = "MODERATE"
        else:
            inversion_risk = "LOW"

        # Directional alignment to Punjab -> Delhi transport bearing (312°)
        deviation_rad = math.radians(abs((wind_dir_deg - 312 + 180) % 360 - 180))
        alignment_pct = round(max(0.0, math.cos(deviation_rad) ** 1.8) * 100.0, 1)

        return {
            "ventilationIndex": ventilation_index,
            "inversionRisk": inversion_risk,
            "corridorAlignmentPct": alignment_pct
        }

    def get_live_weather(self, location_key: str = "delhi_ncr") -> LiveWeatherSnapshot:
        """
        Fetches real-time weather from Open-Meteo with caching and fallback.
        """
        now = time.time()
        loc = LOCATIONS.get(location_key, LOCATIONS["delhi_ncr"])

        # Check in-memory cache
        if location_key in self._cache and (now - self._cache_time.get(location_key, 0)) < self.cache_ttl:
            return LiveWeatherSnapshot(**self._cache[location_key])

        # Fetch from Open-Meteo
        try:
            url = (
                f"https://api.open-meteo.com/v1/forecast?"
                f"latitude={loc['lat']}&longitude={loc['lng']}"
                f"&current=temperature_2m,relative_humidity_2m,surface_pressure,wind_speed_10m,wind_direction_10m"
                f"&hourly=boundary_layer_height"
                f"&forecast_days=1"
            )
            resp = self.session.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                current = data.get("current", {})
                hourly = data.get("hourly", {})

                temp = float(current.get("temperature_2m", 24.0))
                humidity = float(current.get("relative_humidity_2m", 60.0))
                wind_speed = float(current.get("wind_speed_10m", 11.0))
                wind_dir = int(current.get("wind_direction_10m", 305))
                pressure = float(current.get("surface_pressure", 1012.0))

                # Estimate PBL height from hourly boundary layer height array corresponding to current hour
                pbl_height = 480
                bl_heights = hourly.get("boundary_layer_height", [])
                if bl_heights:
                    current_hour = datetime.now().hour
                    if current_hour < len(bl_heights) and bl_heights[current_hour] is not None:
                        pbl_height = int(round(bl_heights[current_hour]))
                    elif bl_heights[0] is not None:
                        pbl_height = int(round(bl_heights[0]))

                # Ensure physically realistic bounds
                pbl_height = max(120, min(2500, pbl_height))

                metrics = self._compute_airshed_metrics(wind_speed, wind_dir, pbl_height)

                snapshot_data = {
                    "temperature": round(temp, 1),
                    "humidity": round(humidity, 1),
                    "windSpeed": round(wind_speed, 1),
                    "windDirectionDeg": wind_dir,
                    "pblHeight": pbl_height,
                    "surfacePressure": round(pressure, 1),
                    "source": "OPEN_METEO_LIVE",
                    "location": loc["name"],
                    "ventilationIndex": metrics["ventilationIndex"],
                    "inversionRisk": metrics["inversionRisk"],
                    "corridorAlignmentPct": metrics["corridorAlignmentPct"],
                    "isLive": True,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }

                # Update cache
                self._cache[location_key] = snapshot_data
                self._cache_time[location_key] = now
                logger.info(f"Updated live weather for {loc['name']} from Open-Meteo")
                return LiveWeatherSnapshot(**snapshot_data)

            else:
                logger.warning(f"Open-Meteo returned status {resp.status_code}. Using seasonal fallback.")
        except Exception as e:
            logger.warning(f"Failed to fetch live weather from Open-Meteo ({e}). Using seasonal fallback.")

        # Fallback to calibrated seasonal snapshot
        fallback_data = dict(DEFAULT_SEASONAL_FALLBACK)
        fallback_data["location"] = loc["name"]
        fallback_data["timestamp"] = datetime.now(timezone.utc).isoformat()
        return LiveWeatherSnapshot(**fallback_data)

    def get_forecast_hours(self, location_key: str = "delhi_ncr", hours: int = 72) -> list:
        """
        Fetches the next `hours` hours of REAL hourly meteorology from Open-Meteo
        (wind speed/direction, planetary boundary layer height, temperature) to
        drive the multi-day dispersion outlook. Returns a list of dicts:
            {"time", "windSpeed", "windDirectionDeg", "pblHeight", "temperature"}
        Returns [] on any failure so callers can fall back to the heuristic model.
        """
        now = time.time()
        loc = LOCATIONS.get(location_key, LOCATIONS["delhi_ncr"])
        cache_key = f"{location_key}:{hours}"

        cached = self._forecast_cache.get(cache_key)
        if cached and (now - self._forecast_cache_time.get(cache_key, 0)) < self.cache_ttl:
            return cached

        try:
            url = (
                f"https://api.open-meteo.com/v1/forecast?"
                f"latitude={loc['lat']}&longitude={loc['lng']}"
                f"&hourly=wind_speed_10m,wind_direction_10m,boundary_layer_height,temperature_2m"
                f"&forecast_hours={hours}"
                f"&timezone=Asia%2FKolkata"
            )
            resp = self.session.get(url, timeout=12)
            if resp.status_code == 200:
                hourly = resp.json().get("hourly", {})
                times = hourly.get("time", [])
                winds = hourly.get("wind_speed_10m", [])
                dirs = hourly.get("wind_direction_10m", [])
                pbls = hourly.get("boundary_layer_height", [])
                temps = hourly.get("temperature_2m", [])

                forecast = []
                for i, t in enumerate(times):
                    wind = winds[i] if i < len(winds) else None
                    pbl = pbls[i] if i < len(pbls) else None
                    if wind is None:
                        continue
                    pbl_val = int(round(pbl)) if pbl is not None else 480
                    pbl_val = max(120, min(3000, pbl_val))
                    forecast.append({
                        "time": t,
                        "windSpeed": round(float(wind), 1),
                        "windDirectionDeg": int(round(float(dirs[i]))) if i < len(dirs) and dirs[i] is not None else 305,
                        "pblHeight": pbl_val,
                        "temperature": round(float(temps[i]), 1) if i < len(temps) and temps[i] is not None else 24.0,
                    })

                if forecast:
                    self._forecast_cache[cache_key] = forecast
                    self._forecast_cache_time[cache_key] = now
                    logger.info("Fetched %dh live hourly forecast for %s from Open-Meteo", len(forecast), loc["name"])
                    return forecast
                logger.warning("Open-Meteo forecast returned no usable hourly rows for %s. Using heuristic fallback.", loc["name"])
            else:
                logger.warning("Open-Meteo forecast returned status %s for %s. Using heuristic fallback.", resp.status_code, loc["name"])
        except Exception as e:
            logger.warning("Failed to fetch hourly forecast from Open-Meteo (%s). Using heuristic fallback.", e)

        return []

    def refresh_cache(self, location_key: str = "delhi_ncr") -> LiveWeatherSnapshot:
        """Explicitly forces a cache invalidation and fresh fetch."""
        if location_key in self._cache:
            del self._cache[location_key]
        return self.get_live_weather(location_key)


# Global service instance
weather_service = WeatherService()

