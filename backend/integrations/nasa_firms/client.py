"""
NASA FIRMS HTTP Client
Secure communication with the official NASA FIRMS Area API.
Implements retry logic, status validation, rate limit handling, and timeout safeguards.
"""

import time
import logging
import requests
from typing import Optional, Dict, Any, Tuple
from .config import FirmsConfig
from .exceptions import (
    FirmsAuthenticationError,
    FirmsRateLimitError,
    FirmsNetworkError,
    FirmsValidationError,
    FirmsError
)

logger = logging.getLogger("agri_smoke.firms.client")

USER_AGENT = "AgriSmoke-AI/2.0 (Geospatial Environmental Air Quality Platform)"


class NasaFirmsClient:
    def __init__(self, config: Optional[FirmsConfig] = None):
        self.config = config or FirmsConfig()
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def get_area_observations_csv(
        self,
        sensor: Optional[str] = None,
        coords: Optional[Tuple[float, float, float, float]] = None,
        day_range: Optional[int] = None,
        date: Optional[str] = None
    ) -> str:
        """
        Retrieves satellite fire observations as CSV from the official NASA FIRMS Area API.
        
        URL pattern:
        {base_url}/api/area/csv/{map_key}/{source}/{west,south,east,north}/{day_range}[/{date}]
        """
        if not self.config.is_configured:
            raise FirmsAuthenticationError(
                "NASA_FIRMS_MAP_KEY is not configured or is invalid. "
                "Obtain a free MAP_KEY at https://firms.modaps.eosdis.nasa.gov/api/map_key/ "
                "and set NASA_FIRMS_MAP_KEY in your environment or .env file."
            )

        active_sensor = sensor or self.config.default_sensor
        target_coords = coords or self.config.get_bounding_box()
        formatted_coords = self.config.format_area_coords(target_coords)
        
        range_val = day_range or self.config.day_range
        if not (1 <= range_val <= 5):
            raise FirmsValidationError(f"NASA FIRMS API day_range must be between 1 and 5 (got {range_val})")

        url = f"{self.config.base_url}/api/area/csv/{self.config.map_key}/{active_sensor}/{formatted_coords}/{range_val}"
        if date:
            url += f"/{date}"

        logger.info(f"Querying NASA FIRMS: sensor={active_sensor}, area={formatted_coords}, range={range_val}, date={date or 'latest'}")

        # Retries with exponential backoff
        max_retries = 3
        backoff_seconds = 2.0

        for attempt in range(1, max_retries + 1):
            try:
                response = self.session.get(url, timeout=self.config.timeout)
                
                # Check for HTTP status errors
                if response.status_code == 200:
                    text = response.text
                    if "Invalid MAP_KEY" in text or "Bad MAP_KEY" in text:
                        raise FirmsAuthenticationError(f"NASA FIRMS rejected MAP_KEY: {self.config.masked_map_key}")
                    return text
                elif response.status_code in (401, 403):
                    raise FirmsAuthenticationError(
                        f"NASA FIRMS Authentication failed (HTTP {response.status_code}). Check your MAP_KEY."
                    )
                elif response.status_code == 429:
                    if attempt < max_retries:
                        sleep_time = backoff_seconds * (2 ** (attempt - 1))
                        logger.warning(f"Rate limited by NASA FIRMS (429). Retrying in {sleep_time}s...")
                        time.sleep(sleep_time)
                        continue
                    raise FirmsRateLimitError("NASA FIRMS rate limit reached (HTTP 429). Try again later.")
                elif response.status_code >= 500:
                    if attempt < max_retries:
                        time.sleep(backoff_seconds)
                        continue
                    raise FirmsNetworkError(f"NASA FIRMS server error (HTTP {response.status_code})")
                else:
                    raise FirmsError(f"NASA FIRMS API returned unexpected HTTP {response.status_code}: {response.text[:200]}")

            except requests.exceptions.Timeout as te:
                if attempt < max_retries:
                    time.sleep(backoff_seconds)
                    continue
                raise FirmsNetworkError(f"Connection to NASA FIRMS timed out after {self.config.timeout}s: {te}")
            except requests.exceptions.RequestException as re:
                if attempt < max_retries:
                    time.sleep(backoff_seconds)
                    continue
                raise FirmsNetworkError(f"Network error communicating with NASA FIRMS: {re}")

        raise FirmsNetworkError("Exceeded maximum retries contacting NASA FIRMS")

    def check_data_availability(self, sensor: Optional[str] = None) -> str:
        """Checks data availability dates for a satellite sensor product."""
        if not self.config.is_configured:
            raise FirmsAuthenticationError("NASA_FIRMS_MAP_KEY is required to check data availability")

        active_sensor = sensor or self.config.default_sensor
        url = f"{self.config.base_url}/api/data_availability/csv/{self.config.map_key}/{active_sensor}"
        
        try:
            resp = self.session.get(url, timeout=self.config.timeout)
            if resp.status_code == 200:
                return resp.text
            raise FirmsError(f"Failed to check data availability (HTTP {resp.status_code})")
        except Exception as e:
            raise FirmsNetworkError(f"Error checking data availability: {e}")
