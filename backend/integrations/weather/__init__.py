"""
AgriSmoke AI - Live Meteorological Weather Integration
Ingests real-time weather and planetary boundary layer (PBL) telemetry
for the Indo-Gangetic airshed using open meteorological APIs with caching and fallback.
"""

from .service import WeatherService, LiveWeatherSnapshot, weather_service

__all__ = ["WeatherService", "LiveWeatherSnapshot", "weather_service"]
