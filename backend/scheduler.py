"""
AgriSmoke AI - Background Ingestion & Telemetry Scheduler
Periodically triggers NASA FIRMS satellite data ingestion and updates
meteorological weather caches without blocking API execution.
"""

import time
import threading
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone, timedelta

try:
    from backend.security import known_env_secrets, safe_error
except ImportError:  # pragma: no cover - supports flat/direct imports
    from security import known_env_secrets, safe_error

logger = logging.getLogger("agri_smoke.scheduler")


class IngestionScheduler:
    def __init__(self, firms_interval_seconds: int = 10800, weather_interval_seconds: int = 900):
        """
        :param firms_interval_seconds: Satellite sync interval (default: 3 hours = 10800s)
        :param weather_interval_seconds: Weather refresh interval (default: 15 mins = 900s)
        """
        self.firms_interval = firms_interval_seconds
        self.weather_interval = weather_interval_seconds
        self._running = False
        self._thread: Optional[threading.Thread] = None

        self.last_firms_sync: Optional[str] = None
        self.next_firms_sync: Optional[str] = None
        self.last_weather_sync: Optional[str] = None
        self.next_weather_sync: Optional[str] = None

        self.total_firms_jobs = 0
        self.total_weather_refreshes = 0
        self.last_error: Optional[str] = None

    def start(self):
        """Starts the scheduler thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="AgriSmoke-Scheduler")
        self._thread.start()
        logger.info("Background Ingestion Scheduler started.")

    def stop(self):
        """Signals the scheduler thread to stop."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("Background Ingestion Scheduler stopped.")

    def _run_loop(self):
        last_firms_time = 0.0
        last_weather_time = 0.0

        while self._running:
            now = time.time()
            now_dt = datetime.now(timezone.utc)

            # 1. Weather Update
            if (now - last_weather_time) >= self.weather_interval:
                try:
                    from backend.integrations.weather.service import weather_service
                    weather_service.refresh_cache("delhi_ncr")
                    self.total_weather_refreshes += 1
                    self.last_weather_sync = now_dt.isoformat()
                    self.next_weather_sync = (now_dt + timedelta(seconds=self.weather_interval)).isoformat()
                    last_weather_time = now
                except Exception as e:
                    # last_error is surfaced by GET /api/v1/scheduler/status; scrub
                    # credentials (MAP_KEY, Redis/DB passwords echoed in URLs) first.
                    self.last_error = f"Weather update error: {safe_error(e, known_env_secrets())}"
                    logger.warning(self.last_error)

            # 2. NASA FIRMS Ingestion
            if (now - last_firms_time) >= self.firms_interval:
                try:
                    from backend.integrations.nasa_firms import FirmsConfig, FirmsIngestionService
                    config = FirmsConfig()
                    if config.is_configured:
                        service = FirmsIngestionService(config)
                        service.ingest_observations()
                        self.total_firms_jobs += 1
                        self.last_firms_sync = now_dt.isoformat()
                        self.next_firms_sync = (now_dt + timedelta(seconds=self.firms_interval)).isoformat()
                        last_firms_time = now
                    else:
                        # NASA FIRMS not configured with MAP_KEY; wait before checking again
                        self.last_firms_sync = "SKIPPED_UNCONFIGURED"
                        self.next_firms_sync = (now_dt + timedelta(seconds=self.firms_interval)).isoformat()
                        last_firms_time = now
                except Exception as e:
                    self.last_error = f"FIRMS sync error: {safe_error(e, known_env_secrets())}"
                    logger.warning(self.last_error)

            # Sleep briefly in small increments so stop() responds quickly
            for _ in range(10):
                if not self._running:
                    break
                time.sleep(1.0)

    def trigger_firms_sync_now(self) -> Dict[str, Any]:
        """Manually trigger immediate FIRMS ingestion."""
        from backend.integrations.nasa_firms import FirmsConfig, FirmsIngestionService
        config = FirmsConfig()
        service = FirmsIngestionService(config)
        summary = service.ingest_observations()
        self.last_firms_sync = datetime.now(timezone.utc).isoformat()
        self.total_firms_jobs += 1
        return summary.model_dump() if hasattr(summary, "model_dump") else summary.dict()

    def trigger_weather_refresh_now(self) -> Dict[str, Any]:
        """Manually trigger immediate weather refresh."""
        from backend.integrations.weather.service import weather_service
        snapshot = weather_service.refresh_cache("delhi_ncr")
        self.last_weather_sync = datetime.now(timezone.utc).isoformat()
        self.total_weather_refreshes += 1
        return snapshot.model_dump() if hasattr(snapshot, "model_dump") else snapshot.dict()

    def get_status(self) -> Dict[str, Any]:
        """Returns scheduler telemetry."""
        return {
            "isRunning": self._running,
            "firmsIntervalHours": round(self.firms_interval / 3600.0, 1),
            "weatherIntervalMinutes": round(self.weather_interval / 60.0, 1),
            "lastFirmsSync": self.last_firms_sync,
            "nextFirmsSync": self.next_firms_sync,
            "lastWeatherSync": self.last_weather_sync,
            "nextWeatherSync": self.next_weather_sync,
            "totalFirmsJobs": self.total_firms_jobs,
            "totalWeatherRefreshes": self.total_weather_refreshes,
            "lastError": self.last_error
        }


# Global singleton scheduler instance
scheduler = IngestionScheduler()

