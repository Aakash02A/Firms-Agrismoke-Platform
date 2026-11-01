"""
AgriSmoke AI - Live Air Quality Integration
Ingests real-time PM2.5 / PM10 and CPCB AQI for monitoring stations via the
key-free Open-Meteo Air Quality API, replacing static mock station values.
"""

from .service import AirQualityService, air_quality_service

__all__ = ["AirQualityService", "air_quality_service"]
