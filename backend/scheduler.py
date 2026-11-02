"""
AgriSmoke AI - Background Ingestion, Telemetry & Database-Maintenance Scheduler

Periodically triggers NASA FIRMS satellite data ingestion and meteorological
cache refreshes without blocking API execution, and drives the SQLite backup /
retention maintenance cycle (snapshot -> integrity -> prune -> off-site push)
so a continuously running Render deployment stays recoverable on its own.

Design notes:
  * each scheduler is a single daemon thread, so a tick can never overlap itself;
  * start() is idempotent (guarded by _running);
  * the loop sleeps in 1s increments so stop() is responsive and shutdown is
    graceful without killing an in-flight job abruptly;
  * failures are caught per-branch, logged with credentials scrubbed, and stored
    in last_error (surfaced by the status endpoints) - they never crash the API;
  * a non-blocking lock prevents a manual trigger and a scheduled tick from
    running the same ingestion / backup concurrently.
"""

import os
import time
import threading
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone, timedelta

try:
    from backend.security import known_env_secrets, safe_error
    from backend import database as db
except ImportError:  # pragma: no cover - supports flat/direct imports
    from security import known_env_secrets, safe_error
    import database as db

logger = logging.getLogger("agri_smoke.scheduler")


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


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class IngestionScheduler:
    def __init__(self, firms_interval_seconds: Optional[int] = None,
                 weather_interval_seconds: Optional[int] = None):
        """
        :param firms_interval_seconds: Satellite sync interval (default env
            FIRMS_INTERVAL_SECONDS, else 3 hours = 10800s)
        :param weather_interval_seconds: Weather refresh interval (default env
            WEATHER_INTERVAL_SECONDS, else 15 mins = 900s)

        Passing an explicit value always wins over the environment, so callers
        and tests are unaffected; omitted values are read live from env.
        """
        self.firms_interval = int(
            firms_interval_seconds if firms_interval_seconds is not None
            else _get_int("FIRMS_INTERVAL_SECONDS", 10800)
        )
        self.weather_interval = int(
            weather_interval_seconds if weather_interval_seconds is not None
            else _get_int("WEATHER_INTERVAL_SECONDS", 900)
        )
        self._running = False
        self._thread: Optional[threading.Thread] = None
        # Guards against a scheduled tick and a manual trigger ingesting at the
        # same time (two concurrent writers on the same FIRMS window).
        self._firms_lock = threading.Lock()

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
                if self._firms_lock.acquire(blocking=False):
                    try:
                        self._run_firms_ingest(now_dt)
                    finally:
                        self._firms_lock.release()
                else:
                    # A manual trigger is mid-ingest. Starting a second writer
                    # on the same FIRMS window would be a duplicate, so advance
                    # the schedule and skip this tick.
                    logger.info("FIRMS scheduled tick skipped: an ingestion is already running")
                    self.next_firms_sync = (now_dt + timedelta(seconds=self.firms_interval)).isoformat()
                last_firms_time = now

            # Sleep briefly in small increments so stop() responds quickly
            for _ in range(10):
                if not self._running:
                    break
                time.sleep(1.0)

    def _run_firms_ingest(self, now_dt: datetime) -> None:
        """Perform one NASA FIRMS ingestion pass. Caller must hold _firms_lock.

        All exceptions are caught here so a provider outage, a bad MAP_KEY or a
        transient DB lock is recorded (with credentials scrubbed) and simply
        retried on the next interval - none of it can crash the API process.
        """
        try:
            from backend.integrations.nasa_firms import FirmsConfig, FirmsIngestionService
            config = FirmsConfig()
            if config.is_configured:
                service = FirmsIngestionService(config)
                service.ingest_observations()
                self.total_firms_jobs += 1
                self.last_firms_sync = now_dt.isoformat()
            else:
                # NASA FIRMS not configured with MAP_KEY; wait before checking again
                self.last_firms_sync = "SKIPPED_UNCONFIGURED"
            self.next_firms_sync = (now_dt + timedelta(seconds=self.firms_interval)).isoformat()
        except Exception as e:
            self.last_error = f"FIRMS sync error: {safe_error(e, known_env_secrets())}"
            logger.warning(self.last_error)

    def trigger_firms_sync_now(self) -> Dict[str, Any]:
        """Manually trigger immediate FIRMS ingestion (guarded against overlap)."""
        if not self._firms_lock.acquire(blocking=False):
            logger.info("Manual FIRMS trigger skipped: an ingestion is already running")
            return {"status": "SKIPPED", "reason": "A FIRMS ingestion is already running"}
        try:
            from backend.integrations.nasa_firms import FirmsConfig, FirmsIngestionService
            config = FirmsConfig()
            service = FirmsIngestionService(config)
            summary = service.ingest_observations()
            self.last_firms_sync = _utcnow().isoformat()
            self.total_firms_jobs += 1
            return summary.model_dump() if hasattr(summary, "model_dump") else summary.dict()
        finally:
            self._firms_lock.release()

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


class MaintenanceScheduler:
    """Drives scheduled SQLite snapshots, retention pruning and off-site copies.

    Runs on its own single daemon thread, so a backup and a retention pass can
    never overlap each other, and a _backup_lock additionally guards against a
    manual trigger colliding with the scheduled run. Every cycle routes through
    backend.database, which integrity-checks each snapshot and enforces the
    retention whitelist. All failures are logged with credentials scrubbed and
    swallowed - maintenance can never take the API down.
    """

    def __init__(self, backup_interval_seconds: Optional[int] = None,
                 retention_interval_seconds: Optional[int] = None,
                 retention_apply: Optional[bool] = None,
                 backup_before_retention: Optional[bool] = None):
        self.backup_interval = int(
            backup_interval_seconds if backup_interval_seconds is not None
            else _get_int("BACKUP_INTERVAL_SECONDS", 21600)         # 6h
        )
        self.retention_interval = int(
            retention_interval_seconds if retention_interval_seconds is not None
            else _get_int("RETENTION_INTERVAL_SECONDS", 86400)      # 24h
        )
        self.retention_apply = (
            # Dry-run is the safe default: a fresh deploy must NEVER silently
            # delete historical rows. Actual deletion requires an explicit
            # RETENTION_APPLY=true opt-in by the operator.
            _get_bool("RETENTION_APPLY", False) if retention_apply is None else retention_apply
        )
        self.backup_before_retain = (
            _get_bool("BACKUP_BEFORE_RETAIN", True) if backup_before_retention is None else backup_before_retention
        )
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._backup_lock = threading.Lock()

        self.last_backup: Optional[str] = None
        self.next_backup: Optional[str] = None
        self.last_backup_ok: Optional[bool] = None
        self.last_retention: Optional[str] = None
        self.next_retention: Optional[str] = None
        self.last_retention_summary: Optional[Dict[str, Any]] = None
        self.total_backups = 0
        self.total_retention_runs = 0
        self.last_error: Optional[str] = None

    def start(self):
        """Starts the maintenance thread (idempotent)."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="AgriSmoke-Maintenance")
        self._thread.start()
        logger.info("Database Maintenance Scheduler started (backup every %.1fh).",
                    self.backup_interval / 3600.0)

    def stop(self):
        """Signals the maintenance thread to stop and waits briefly."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        logger.info("Database Maintenance Scheduler stopped.")

    def _run_loop(self):
        last_backup_time = 0.0
        # Retention is DEFERRED until a full interval has elapsed since boot, so
        # a redeploy can never immediately prune data (even when an operator has
        # explicitly opted in to apply mode). Backup is still allowed to fire at
        # boot via the first_backup_done flag below, because a fresh snapshot on
        # startup is a safety feature, not a destructive one.
        last_retention_time = time.time()
        first_backup_done = False

        while self._running:
            now = time.time()
            now_dt = _utcnow()

            # 1. Backup cycle. An initial snapshot runs right after boot (so a
            #    restart always leaves a fresh off-site copy), then every
            #    backup_interval thereafter.
            if not first_backup_done or (now - last_backup_time) >= self.backup_interval:
                self.run_backup_now()
                last_backup_time = now
                first_backup_done = True

            # 2. Retention pruning (aged rows only, whitelist-enforced, and a
            #    backup is taken first when it actually deletes).
            if (now - last_retention_time) >= self.retention_interval:
                self.run_retention_now()
                last_retention_time = now
                self.next_retention = (now_dt + timedelta(seconds=self.retention_interval)).isoformat()

            for _ in range(10):
                if not self._running:
                    break
                time.sleep(1.0)

    def run_backup_now(self, push_offsite: bool = True) -> Dict[str, Any]:
        """Take one integrity-checked snapshot, prune old ones and push off-site."""
        if not self._backup_lock.acquire(blocking=False):
            logger.info("Backup skipped: a backup/retention cycle is already running")
            return {"ok": False, "status": "SKIPPED", "reason": "A backup is already running"}
        try:
            report = db.run_backup_cycle(push_offsite=push_offsite)
            self.last_backup = _utcnow().isoformat()
            self.next_backup = (_utcnow() + timedelta(seconds=self.backup_interval)).isoformat()
            self.total_backups += 1
            self.last_backup_ok = bool(report.get("ok"))
            if not self.last_backup_ok:
                logger.warning("Backup cycle completed with problems: %s", report.get("offsite"))
            return report
        except Exception as e:
            self.last_error = f"Backup error: {safe_error(e, known_env_secrets())}"
            self.last_backup_ok = False
            logger.warning(self.last_error)
            return {"ok": False, "error": self.last_error}
        finally:
            self._backup_lock.release()

    def run_retention_now(self, apply_changes: Optional[bool] = None) -> Dict[str, Any]:
        """Prune aged rows. Shares the backup lock because a pre-retention
        snapshot is taken inside the cycle, so the two must not interleave."""
        if apply_changes is None:
            apply_changes = self.retention_apply
        if not self._backup_lock.acquire(blocking=False):
            logger.info("Retention skipped: a backup/retention cycle is already running")
            return {"ok": False, "status": "SKIPPED", "reason": "A backup is already running"}
        try:
            report = db.run_retention_cycle(apply_changes=apply_changes,
                                            backup_first=self.backup_before_retain)
            self.last_retention = _utcnow().isoformat()
            if report.get("aborted"):
                # A destructive prune was blocked (the pre-retention backup did
                # not fully succeed). Record it, but do NOT count it as a
                # completed retention cycle - nothing was deleted.
                self.last_error = f"Retention aborted: {report.get('reason', 'pre-retention backup failed')}"
                logger.warning(self.last_error)
                return report
            self.total_retention_runs += 1
            self.last_retention_summary = {
                t: r.get("rows_deleted", 0) for t, r in report.get("tables", {}).items()
            }
            return report
        except Exception as e:
            self.last_error = f"Retention error: {safe_error(e, known_env_secrets())}"
            logger.warning(self.last_error)
            return {"ok": False, "error": self.last_error}
        finally:
            self._backup_lock.release()

    def get_status(self) -> Dict[str, Any]:
        """Maintenance telemetry for GET /api/v1/maintenance/status."""
        return {
            "isRunning": self._running,
            "backupIntervalHours": round(self.backup_interval / 3600.0, 1),
            "retentionIntervalHours": round(self.retention_interval / 3600.0, 1),
            "retentionApply": self.retention_apply,
            # Unambiguous human-readable mode: an operator (or an auditor) must
            # be able to tell at a glance that production is NOT deleting data.
            "retentionMode": "apply" if self.retention_apply else "dry-run",
            "backupBeforeRetention": self.backup_before_retain,
            "lastBackup": self.last_backup,
            "nextBackup": self.next_backup,
            "lastBackupOk": self.last_backup_ok,
            "totalBackups": self.total_backups,
            "lastRetention": self.last_retention,
            "totalRetentionRuns": self.total_retention_runs,
            "lastRetentionSummary": self.last_retention_summary,
            "offsiteConfigured": db.offsite_configured(),
            "disk": db.check_disk_space(),
            "lastError": self.last_error,
        }


# Global singleton instances. A deployment MUST run a single app instance /
# worker so these background jobs run exactly once (see render.yaml); the API
# can be disabled from starting them entirely via SCHEDULER_ENABLED /
# MAINTENANCE_ENABLED (handled at startup in main.py).
scheduler = IngestionScheduler()
maintenance_scheduler = MaintenanceScheduler()


