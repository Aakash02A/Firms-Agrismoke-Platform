"""
NASA FIRMS Configuration Module
Handles environment variable loading, bounds validation, and sensor catalog.
"""

import os
from typing import Dict, Any, Tuple

SUPPORTED_SENSORS = [
    "VIIRS_NOAA20_NRT",
    "VIIRS_SNPP_NRT",
    "VIIRS_NOAA21_NRT",
    "MODIS_NRT"
]

DEFAULT_REGIONS: Dict[str, Tuple[float, float, float, float]] = {
    # format: (west, south, east, north)
    "indo_gangetic_airshed": (73.5, 27.5, 78.5, 32.5),
    "punjab_haryana": (73.8, 27.6, 77.6, 32.5),
    "delhi_ncr": (76.5, 28.1, 77.7, 29.0),
    "north_india": (72.0, 25.0, 81.0, 33.5),
}


class FirmsConfig:
    def __init__(self):
        self.map_key: str = os.getenv("NASA_FIRMS_MAP_KEY", "").strip()
        self.base_url: str = os.getenv("NASA_FIRMS_BASE_URL", "https://firms.modaps.eosdis.nasa.gov").rstrip("/")
        self.default_sensor: str = os.getenv("NASA_FIRMS_DEFAULT_SENSOR", "VIIRS_NOAA20_NRT")
        
        # Day range must be 1 to 5 as per NASA documentation
        try:
            day_range = int(os.getenv("NASA_FIRMS_DAY_RANGE", "3"))
            self.day_range: int = max(1, min(5, day_range))
        except ValueError:
            self.day_range = 3

        try:
            self.timeout: int = int(os.getenv("NASA_FIRMS_REQUEST_TIMEOUT", "30"))
        except ValueError:
            self.timeout = 30

        try:
            self.cache_ttl: int = int(os.getenv("NASA_FIRMS_CACHE_TTL", "900"))
        except ValueError:
            self.cache_ttl = 900

        self.default_region: str = "indo_gangetic_airshed"

    @property
    def is_configured(self) -> bool:
        """Returns True if a non-empty MAP_KEY is set."""
        return bool(self.map_key and len(self.map_key) >= 10)

    @property
    def masked_map_key(self) -> str:
        """Returns masked MAP_KEY safe for logging and display."""
        if not self.map_key:
            return "UNCONFIGURED"
        if len(self.map_key) <= 6:
            return "******"
        return f"{'*' * (len(self.map_key) - 4)}{self.map_key[-4:]}"

    def get_bounding_box(self, region_name: str = "indo_gangetic_airshed") -> Tuple[float, float, float, float]:
        """Returns (west, south, east, north) tuple for a given region."""
        return DEFAULT_REGIONS.get(region_name, DEFAULT_REGIONS["indo_gangetic_airshed"])

    def format_area_coords(self, coords: Tuple[float, float, float, float]) -> str:
        """Formats (west, south, east, north) for NASA Area API string."""
        west, south, east, north = coords
        if not (-180 <= west < east <= 180) or not (-90 <= south < north <= 90):
            raise ValueError(f"Invalid bounding box coordinates: {coords}")
        return f"{west:.2f},{south:.2f},{east:.2f},{north:.2f}"

    def to_safe_dict(self) -> Dict[str, Any]:
        """Returns safe configuration summary without leaking secrets."""
        return {
            "configured": self.is_configured,
            "masked_map_key": self.masked_map_key,
            "base_url": self.base_url,
            "default_sensor": self.default_sensor,
            "supported_sensors": SUPPORTED_SENSORS,
            "day_range": self.day_range,
            "timeout_seconds": self.timeout,
            "cache_ttl_seconds": self.cache_ttl,
            "regions": list(DEFAULT_REGIONS.keys())
        }

    def __repr__(self) -> str:
        return f"<FirmsConfig sensor={self.default_sensor} configured={self.is_configured} key={self.masked_map_key}>"
