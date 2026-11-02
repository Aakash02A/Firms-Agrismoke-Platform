"""
Test Suite: Ingestion & Backup Automation (Phase 4)

Isolation contract (identical to the Phase 2 suite): every test re-points
backend.database at a throwaway SQLite file inside a fresh temp directory, and
redirects BACKUP_DIR / OFFSITE_BACKUP_DIR into that same directory, so the
production database/agri_smoke.db and the real backup folder are never opened,
snapshotted, pruned or copied by this suite. Background threads are always
stopped and joined in tearDown.

Coverage maps one-to-one onto the Phase 4 Stage 5 checklist:
  1. Scheduler starts exactly once (idempotent start, env kill-switches).
  2. Duplicate ingestion prevention (manual trigger vs scheduled tick).
  3. Backup scheduling (boot snapshot + interval, retention interval).
  4. Backup integrity (integrity_check recorded, corrupt snapshot discarded).
  5. Backup retention (BACKUP_RETENTION_KEEP) and data retention (whitelist,
     dry-run, env windows, backup-before-prune).
  6. Off-site distribution (directory backend, same-dir refusal, disabled and
     uninstalled-backend paths) and disk-space monitoring.
  7. Failure handling - a provider outage or a backup crash is recorded with
     credentials scrubbed and can never take the API down.
  8. Concurrent ingestion + backup on one database, and graceful shutdown.
"""

import os
import sys
import shutil
import sqlite3
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend import database as db                     # noqa: E402
from backend.app_config import AppConfig               # noqa: E402
from backend.scheduler import IngestionScheduler, MaintenanceScheduler  # noqa: E402

FAKE_KEY = "ABCD1234EFGH5678IJKL"          # 20 chars -> FirmsConfig.is_configured True
LEAK_URL = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{FAKE_KEY}/VIIRS_NOAA20_NRT/73,27,78,32/3"

SCHEDULER_THREAD_NAMES = {"AgriSmoke-Scheduler", "AgriSmoke-Maintenance"}

#: Sentinel raised by fake ingest entry points so a test can prove that real
#: NASA FIRMS network calls are never attempted from this suite.
_NO_NETWORK = RuntimeError("Phase 4 suite must never call the real FIRMS API")


class CorruptReportingConnection(sqlite3.Connection):
    """A genuine sqlite3.Connection (so the backup API still accepts it as a
    target) that reports a corrupted database when integrity_check is run.

    Used to prove a torn snapshot is discarded instead of being handed back as
    a usable recovery point.
    """

    def execute(self, sql, *args, **kwargs):  # noqa: D102
        if "integrity_check" in str(sql):
            return super().execute("SELECT 'corrupt page chain'")
        return super().execute(sql, *args, **kwargs)


class FakeDateTime(datetime):
    """datetime substitute whose now()/today() advance 1 second per call.

    Snapshot filenames carry second precision, so several backups taken inside
    one test second would otherwise overwrite each other and make retention
    counting meaningless. Class attributes are reset with every patch.
    """
    BASE = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    STEP = 0

    @classmethod
    def _advance(cls):
        cls.STEP += 1
        return cls.BASE + timedelta(seconds=cls.STEP)

    @classmethod
    def now(cls, tz=None):
        value = cls._advance()
        return value if tz is None else value.astimezone(tz)

    @classmethod
    def today(cls):
        return cls._advance()


def patch_module_clock(module):
    """Install FakeDateTime in `module` for the duration of one test."""
    FakeDateTime.STEP = 0
    return mock.patch.object(module, "datetime", FakeDateTime)


def count_scheduler_threads() -> int:
    return sum(1 for t in threading.enumerate() if t.name in SCHEDULER_THREAD_NAMES)


class Phase4TestCase(unittest.TestCase):
    """Temp DB + temp backup/off-site directory + hermetic scheduler state."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="agrismoke_phase4_"))
        self.db_path = self.tmp / "agri_smoke_test.db"
        self.backup_dir = self.tmp / "backups"
        self.offsite_dir = self.tmp / "offsite"

        self._saved = {}
        for key, value in {
            "DB_PATH": str(self.db_path),
            "BACKUP_DIR": str(self.backup_dir),
            "OFFSITE_BACKEND": "none",
            "OFFSITE_BACKUP_DIR": str(self.offsite_dir),
            "OFFSITE_S3_BUCKET": "",
            "BACKUP_RETENTION_KEEP": "10",
            "SQLITE_MIN_FREE_MB": "1",
            "FIRE_OBS_RETENTION_DAYS": "",
            "SIM_HISTORY_RETENTION_DAYS": "",
            "RETENTION_APPLY": "",
            "BACKUP_BEFORE_RETAIN": "",
            "SCHEDULER_ENABLED": "",
            "MAINTENANCE_ENABLED": "",
        }.items():
            self._saved[key] = os.environ.get(key)
            if value:
                os.environ[key] = value
            else:
                os.environ.pop(key, None)

        db.DB_PATH = self.db_path
        db._wal_active = None
        self.threads = []

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        for thread in self.threads:
            thread.join(timeout=5)
        # A leaked scheduler thread would pollute every later test in the run.
        leaked = [t for t in threading.enumerate() if t.name in SCHEDULER_THREAD_NAMES]
        for t in leaked:
            t.join(timeout=5)
        db._wal_active = None
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ------------------------------------------------------------------ helpers

    def boot_db(self):
        """Create + seed the isolated database (schema, indexes, WAL)."""
        db.ensure_ready()

    def snapshot_files(self, directory: Path = None):
        directory = directory or self.backup_dir
        if not directory.exists():
            return []
        return sorted(p.name for p in directory.glob(f"{self.db_path.stem}-*.db"))

    def start_thread(self, thread: threading.Thread) -> threading.Thread:
        thread.daemon = True
        thread.start()
        self.threads.append(thread)
        return thread


# =============================================================================
# Stage 5.1 - Scheduler starts exactly once
# =============================================================================

class TestSchedulerStartsOnce(Phase4TestCase):

    def _block_in_loop(self, sched):
        """Park the loop body in 0.2s slices so start()/stop() are deterministic.

        Patched onto the CLASS, so it is bound as a method and must accept the
        instance argument - otherwise the worker thread dies instantly and the
        "exactly one live thread" assertions below would pass vacuously.
        """
        def fake_loop(_self):
            while sched._running:
                time.sleep(0.2)
        return fake_loop

    def test_ingestion_scheduler_start_is_idempotent(self):
        sched = IngestionScheduler(firms_interval_seconds=999999, weather_interval_seconds=999999)
        with mock.patch.object(IngestionScheduler, "_run_loop", self._block_in_loop(sched)):
            sched.start()
            sched.start()
            first = sched._thread
            sched.start()
            self.assertIs(first, sched._thread, "start() replaced the worker thread")
            self.assertEqual(1, count_scheduler_threads(), "duplicate scheduler threads running")
            self.assertTrue(first.is_alive())
            sched.stop()
        first.join(timeout=5)
        self.assertFalse(first.is_alive())

    def test_maintenance_scheduler_start_is_idempotent(self):
        sched = MaintenanceScheduler(backup_interval_seconds=999999, retention_interval_seconds=999999)
        with mock.patch.object(MaintenanceScheduler, "_run_loop", self._block_in_loop(sched)):
            sched.start()
            sched.start()
            first = sched._thread
            self.assertEqual(1, count_scheduler_threads())
            self.assertIs(first, sched._thread)
            sched.stop()
        first.join(timeout=5)
        self.assertFalse(first.is_alive())

    def test_stop_without_start_is_safe(self):
        IngestionScheduler().stop()
        MaintenanceScheduler().stop()
        self.assertEqual(0, count_scheduler_threads())


class TestSchedulerKillSwitches(Phase4TestCase):

    def test_config_reads_disable_flags(self):
        from backend import app_config as app_config_module
        app_config_module.config = AppConfig()
        with mock.patch.dict(os.environ, {"SCHEDULER_ENABLED": "false", "MAINTENANCE_ENABLED": "false"}):
            cfg = AppConfig()
            self.assertFalse(cfg.scheduler_enabled)
            self.assertFalse(cfg.maintenance_enabled)
        with mock.patch.dict(os.environ, {"SCHEDULER_ENABLED": "true", "MAINTENANCE_ENABLED": "true"}):
            cfg = AppConfig()
            self.assertTrue(cfg.scheduler_enabled)
            self.assertTrue(cfg.maintenance_enabled)
        # Default stays on, so a normal Render deploy still runs its own backups.
        os.environ.pop("SCHEDULER_ENABLED", None)
        os.environ.pop("MAINTENANCE_ENABLED", None)
        cfg = AppConfig()
        self.assertTrue(cfg.scheduler_enabled)
        self.assertTrue(cfg.maintenance_enabled)

    def test_startup_honours_env_kill_switches(self):
        """SCHEDULER_ENABLED/MAINTENANCE_ENABLED=false must keep both threads down."""
        import backend.main as main_module
        started = []
        with mock.patch.object(main_module, "scheduler") as api_sched, \
             mock.patch.object(main_module, "maintenance_scheduler") as maint_sched, \
             mock.patch.object(main_module, "config",
                               mock.Mock(scheduler_enabled=False, maintenance_enabled=False)), \
             mock.patch.object(main_module.db, "ensure_ready", return_value={"tables": [], "journal_mode": "wal"}):
            api_sched.start.side_effect = lambda: started.append("ingestion")
            maint_sched.start.side_effect = lambda: started.append("maintenance")
            main_module.startup_event()
        self.assertEqual([], started, "a disabled scheduler was still started")

        with mock.patch.object(main_module, "scheduler") as api_sched, \
             mock.patch.object(main_module, "maintenance_scheduler") as maint_sched, \
             mock.patch.object(main_module, "config",
                               mock.Mock(scheduler_enabled=True, maintenance_enabled=True)), \
             mock.patch.object(main_module.db, "ensure_ready", return_value={"tables": [], "journal_mode": "wal"}):
            main_module.startup_event()
            api_sched.start.assert_called_once_with()
            maint_sched.start.assert_called_once_with()
            main_module.shutdown_event()
            api_sched.stop.assert_called_once_with()
            maint_sched.stop.assert_called_once_with()


# =============================================================================
# Stage 5.2 - Duplicate ingestion prevention
# =============================================================================

class TestDuplicateIngestionPrevention(Phase4TestCase):

    def test_manual_trigger_skipped_while_ingestion_holds_the_lock(self):
        sched = IngestionScheduler()
        self.assertTrue(sched._firms_lock.acquire(blocking=False))
        try:
            with mock.patch("backend.integrations.nasa_firms.FirmsIngestionService") as svc:
                result = sched.trigger_firms_sync_now()
        finally:
            sched._firms_lock.release()
        self.assertEqual("SKIPPED", result["status"])
        self.assertIn("already running", result["reason"])
        svc.return_value.ingest_observations.assert_not_called()

    def test_scheduled_tick_skipped_while_manual_trigger_runs(self):
        sched = IngestionScheduler(firms_interval_seconds=0, weather_interval_seconds=10 ** 9)
        self.assertTrue(sched._firms_lock.acquire(blocking=False))
        try:
            with mock.patch("backend.integrations.nasa_firms.FirmsIngestionService") as svc, \
                 mock.patch("backend.integrations.weather.service.weather_service.refresh_cache",
                            return_value=mock.MagicMock()):
                sched._running = True
                with mock.patch("backend.scheduler.time.sleep",
                                side_effect=lambda *_a: setattr(sched, "_running", False)):
                    sched._run_loop()
            svc.return_value.ingest_observations.assert_not_called()
        finally:
            sched._firms_lock.release()
        self.assertEqual(0, sched.total_firms_jobs)
        self.assertIsNotNone(sched.next_firms_sync, "skipped tick must still reschedule")

    def test_lock_released_after_manual_trigger(self):
        sched = IngestionScheduler()
        cfg = mock.Mock(is_configured=True)
        summary = mock.Mock()
        summary.model_dump.return_value = {"status": "SUCCESS"}
        service = mock.Mock()
        service.ingest_observations.return_value = summary
        with mock.patch("backend.integrations.nasa_firms.FirmsConfig", return_value=cfg), \
             mock.patch("backend.integrations.nasa_firms.FirmsIngestionService", return_value=service):
            result = sched.trigger_firms_sync_now()
        self.assertEqual({"status": "SUCCESS"}, result)
        self.assertEqual(1, sched.total_firms_jobs)
        self.assertTrue(sched._firms_lock.acquire(blocking=False), "lock leaked after trigger")
        sched._firms_lock.release()

    def test_lock_released_when_manual_trigger_fails(self):
        sched = IngestionScheduler()
        cfg = mock.Mock(is_configured=True)
        with mock.patch("backend.integrations.nasa_firms.FirmsConfig", return_value=cfg), \
             mock.patch("backend.integrations.nasa_firms.FirmsIngestionService",
                        side_effect=_NO_NETWORK):
            with self.assertRaises(RuntimeError):
                sched.trigger_firms_sync_now()
        self.assertTrue(sched._firms_lock.acquire(blocking=False), "lock leaked after failed trigger")
        sched._firms_lock.release()


class TestBackupOverlapPrevention(Phase4TestCase):

    def test_backup_and_retention_share_one_lock(self):
        sched = MaintenanceScheduler()
        self.assertTrue(sched._backup_lock.acquire(blocking=False))
        try:
            with mock.patch.object(db, "run_backup_cycle") as backup, \
                 mock.patch.object(db, "run_retention_cycle") as retain:
                b = sched.run_backup_now()
                r = sched.run_retention_now()
                d = sched.run_retention_now(apply_changes=False)
        finally:
            sched._backup_lock.release()
        for report in (b, r, d):
            self.assertEqual("SKIPPED", report["status"])
        backup.assert_not_called()
        retain.assert_not_called()

    def test_only_one_scheduled_backup_runs_under_concurrency(self):
        sched = MaintenanceScheduler()
        concurrent = []
        peak = []

        def slow_cycle(*_a, **_k):
            concurrent.append(1)
            peak.append(len(concurrent))
            time.sleep(0.15)
            concurrent.pop()
            return {"ok": True}

        with mock.patch.object(db, "run_backup_cycle", side_effect=slow_cycle):
            threads = [self.start_thread(threading.Thread(target=sched.run_backup_now)) for _ in range(3)]
            for t in threads:
                t.join(timeout=10)
        self.assertEqual(1, max(peak), "two backups executed at once")
        self.assertEqual(1, sched.total_backups)


# =============================================================================
# Stage 5.3 - Backup cycle: snapshot, integrity, retention, disk, off-site
# =============================================================================

class TestBackupCycle(Phase4TestCase):

    def test_snapshot_records_integrity_and_row_counts(self):
        self.boot_db()
        with patch_module_clock(db):
            report = db.run_backup_cycle(label="unit")
        self.assertTrue(report["ok"], report)
        info = report["backup"]
        self.assertEqual("ok", info["integrity"])
        self.assertGreater(info["total_rows"], 0, "snapshot captured no data")
        self.assertTrue(Path(info["backup_path"]).exists())
        self.assertIn("-unit-", Path(info["backup_path"]).name)
        self.assertIn("snapshot", report["steps"])

    def test_snapshot_is_restorable_round_trip(self):
        self.boot_db()
        with db.get_connection() as conn:
            conn.execute(
                "INSERT INTO simulation_history (created_at, fire_count, wind_speed, wind_dir, pbl_height,"
                " baseline_aqi, bio_dec_pct, happy_seeder_pct, predicted_aqi, predicted_pm25, predicted_pm10,"
                " parali_pct, grap_stage, mitigation_drop) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("2026-01-02 10:00:00", 5, 90, 200, 100, 0, 0, 120, 40, 70, 5, 30.0, "Stage I", 5),
            )
            conn.commit()
        with patch_module_clock(db):
            info = db.backup_database(label="roundtrip")
        restored = self.tmp / "restored.db"
        result = db.restore_database(info["backup_path"], target_path=str(restored), confirm=True)
        self.assertEqual("ok", result["integrity"])
        with sqlite3.connect(str(restored)) as conn:
            rows = conn.execute("SELECT COUNT(*) FROM simulation_history").fetchone()[0]
        self.assertGreaterEqual(rows, 1)

    def test_corrupt_snapshot_is_discarded_not_reported_ok(self):
        """backup_database() integrity-checks the DESTINATION and unlinks a bad
        snapshot, so a corrupt backup can never be reported (or pruned-in) as a
        valid recovery point."""
        self.boot_db()
        real_connect = db._connect_for_admin
        calls = []

        def fake_connect(path, readonly=False):
            calls.append(Path(path))
            if len(calls) == 2:            # the freshly written destination
                conn = CorruptReportingConnection(str(path))
                conn.row_factory = sqlite3.Row
                return conn
            return real_connect(path, readonly)

        with mock.patch.object(db, "_connect_for_admin", side_effect=fake_connect), \
             patch_module_clock(db):
            with self.assertRaises(Exception) as ctx:
                db.backup_database(label="corrupt")
        self.assertIn("corrupt", str(ctx.exception))
        self.assertEqual([], self.snapshot_files(), "a corrupt snapshot was left on disk")

    def test_local_snapshot_retention_honours_keep_count(self):
        self.boot_db()
        os.environ["BACKUP_RETENTION_KEEP"] = "2"
        with patch_module_clock(db):
            for _ in range(5):
                db.run_backup_cycle(label="rot", push_offsite=False)
        remaining = self.snapshot_files()
        self.assertEqual(2, len(remaining), remaining)
        self.assertTrue(self.db_path.exists(), "retention must never touch the live database")

    def test_keep_zero_disables_pruning(self):
        self.boot_db()
        os.environ["BACKUP_RETENTION_KEEP"] = "0"
        with patch_module_clock(db):
            for _ in range(3):
                db.run_backup_cycle(label="nokeep", push_offsite=False)
        self.assertEqual(3, len(self.snapshot_files()))

    def test_disk_headroom_is_reported_and_never_blocks_a_healthy_run(self):
        self.boot_db()
        disk = db.check_disk_space()
        self.assertTrue(disk["available"])
        self.assertGreaterEqual(disk["free_mb"], 0)
        os.environ["SQLITE_MIN_FREE_MB"] = "200000000"
        low = db.check_disk_space()
        self.assertFalse(low["ok"], "an impossible floor must flag the disk as full")
        report = db.run_backup_cycle(label="lowdisk", push_offsite=False)
        self.assertTrue(report["ok"])
        self.assertIn("-lowdisk-", Path(report["backup"]["backup_path"]).name)

    def test_disk_probe_falls_back_to_existing_ancestor(self):
        missing = self.tmp / "not" / "created" / "yet.db"
        disk = db.check_disk_space(str(missing))
        # The requested path does not exist yet; the probe silently walks up to
        # the nearest existing ancestor so a pre-bootstrap read still works.
        self.assertTrue(disk["available"])
        self.assertEqual(str(missing), disk["path"])


class TestOffsiteDistribution(Phase4TestCase):
    """A same-disk snapshot is NOT disaster recovery: these tests pin the
    behaviour of the real off-site paths and of refusing a fake one."""

    def test_disabled_backend_reports_not_delivered_without_failing(self):
        self.boot_db()
        with patch_module_clock(db):
            report = db.run_backup_cycle(label="offnone")
        self.assertTrue(report["ok"])
        self.assertFalse(report["offsite"]["delivered"])
        self.assertFalse(db.offsite_configured())

    def test_directory_backend_delivers_and_verifies_the_copy(self):
        self.boot_db()
        os.environ["OFFSITE_BACKEND"] = "directory"
        with patch_module_clock(db):
            report = db.run_backup_cycle(label="offdir")
        self.assertTrue(report["ok"], report)
        self.assertTrue(report["offsite"]["delivered"])
        self.assertEqual("ok", report["offsite"]["integrity"])
        self.assertTrue(Path(report["offsite"]["path"]).exists())
        self.assertTrue(db.offsite_configured())

    def test_directory_backend_refuses_to_call_the_same_dir_offsite(self):
        self.boot_db()
        os.environ["OFFSITE_BACKEND"] = "directory"
        os.environ["OFFSITE_BACKUP_DIR"] = str(self.backup_dir)
        with patch_module_clock(db):
            report = db.run_backup_cycle(label="offsamedir")
        self.assertFalse(report["offsite"]["delivered"])
        self.assertIn("not off-site", report["offsite"]["reason"])
        self.assertFalse(report["ok"], "a configured off-site target that failed must not report success")

    def test_directory_backend_reports_missing_target(self):
        self.boot_db()
        os.environ["OFFSITE_BACKEND"] = "directory"
        os.environ.pop("OFFSITE_BACKUP_DIR", None)
        info = db.backup_database(label="offmissing")
        result = db.distribute_backup_offsite(info["backup_path"])
        self.assertFalse(result["delivered"])
        self.assertIn("OFFSITE_BACKUP_DIR", result["reason"])

    def test_s3_backend_without_sdk_degrades_to_a_logged_reason(self):
        """Off-site S3 must degrade gracefully (a logged reason, not a crash)
        when boto3 is not installed - it is an optional dependency."""
        self.boot_db()
        os.environ["OFFSITE_BACKEND"] = "s3"
        os.environ["OFFSITE_S3_BUCKET"] = "unit-test-bucket"
        info = db.backup_database(label="offs3")
        real_import = __import__

        def _import_no_boto3(name, *args, **kwargs):
            if name == "boto3":
                raise ImportError("simulated: boto3 not installed")
            return real_import(name, *args, **kwargs)

        with mock.patch("backend.database.shutil.copy2") as copy2, \
             mock.patch("builtins.__import__", side_effect=_import_no_boto3):
            result = db.distribute_backup_offsite(info["backup_path"])
        self.assertFalse(result["delivered"])
        self.assertIn("boto3", result["reason"])
        copy2.assert_not_called()

    def test_unknown_backend_is_rejected(self):
        self.boot_db()
        info = db.backup_database(label="offbogus")
        os.environ["OFFSITE_BACKEND"] = "carrier-pigeon"
        result = db.distribute_backup_offsite(info["backup_path"])
        self.assertFalse(result["delivered"])
        self.assertIn("unknown OFFSITE_BACKEND", result["reason"])

    def test_missing_snapshot_is_reported(self):
        os.environ["OFFSITE_BACKEND"] = "directory"
        result = db.distribute_backup_offsite(str(self.tmp / "does-not-exist.db"))
        self.assertFalse(result["delivered"])
        self.assertIn("snapshot missing", result["reason"])


# =============================================================================
# Stage 5.4 - Data retention
# =============================================================================

class TestRetentionCycle(Phase4TestCase):

    def seed_obs(self, stale_days, fresh_days=0):
        """Insert one aged and one recent fire_observations row."""
        today = datetime.now(timezone.utc).date()
        with db.get_connection() as conn:
            for id_suffix, when in (("old", today - timedelta(days=stale_days)),
                                    ("new", today - timedelta(days=fresh_days))):
                conn.execute(
                    "INSERT INTO fire_observations (id, source_dataset, satellite, instrument, latitude,"
                    " longitude, acq_date, acq_time, acquisition_timestamp, confidence, confidence_score,"
                    " frp, daynight, classification) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (f"obs-{id_suffix}", "VIIRS_NOAA20_NRT", "NOAA-20", "VIIRS", 30.9, 75.8,
                     when.isoformat(), "0100", f"{when.isoformat()}T01:00:00Z", "nominal", 0.5,
                     1.2, "D", "agricultural"),
                )
            conn.commit()

    def count_observations(self):
        with db.get_connection() as conn:
            return conn.execute("SELECT COUNT(*) FROM fire_observations").fetchone()[0]

    def test_dry_run_counts_but_deletes_nothing(self):
        self.boot_db()
        self.seed_obs(stale_days=400)
        before = self.count_observations()
        report = db.run_retention_cycle(apply_changes=False)
        self.assertFalse(report["applied"])
        self.assertEqual(before, self.count_observations(), "dry run deleted rows")
        self.assertGreater(report["tables"]["fire_observations"]["rows_older_than_cutoff"], 0)
        self.assertEqual(0, report["tables"]["fire_observations"]["rows_deleted"])

    def test_apply_removes_only_aged_rows(self):
        self.boot_db()
        self.seed_obs(stale_days=400)
        report = db.run_retention_cycle(apply_changes=True, backup_first=False)
        self.assertEqual(1, report["tables"]["fire_observations"]["rows_deleted"])
        self.assertEqual(1, self.count_observations(), "recent record must be preserved")
        with db.get_connection() as conn:
            remaining = conn.execute("SELECT id FROM fire_observations").fetchone()[0]
        self.assertEqual("obs-new", remaining)

    def test_whitelist_rejects_non_historical_tables(self):
        self.boot_db()
        report = db.run_retention_cycle(apply_changes=True, backup_first=False,
                                        tables=["monitoring_stations", "custom_thresholds"])
        self.assertEqual([], report["eligible_tables"])
        self.assertCountEqual(["monitoring_stations", "custom_thresholds"], report["rejected_tables"])
        with db.get_connection() as conn:
            stations = conn.execute("SELECT COUNT(*) FROM monitoring_stations").fetchone()[0]
        self.assertGreater(stations, 0, "operational table was pruned")

    def test_backup_is_taken_before_destructive_maintenance(self):
        self.boot_db()
        self.seed_obs(stale_days=400)
        with patch_module_clock(db):
            report = db.run_retention_cycle(apply_changes=True, backup_first=True)
        self.assertIsNotNone(report["pre_retention_backup"], "no pre-retention snapshot was taken")
        self.assertIn("-pre-retain-", Path(report["pre_retention_backup"]["backup_path"]).name)
        self.assertEqual(1, self.count_observations())

    def test_no_backup_for_a_dry_run(self):
        self.boot_db()
        self.seed_obs(stale_days=400)
        with mock.patch.object(db, "run_backup_cycle") as backup:
            db.run_retention_cycle(apply_changes=False, backup_first=True)
        backup.assert_not_called()

    def test_retention_windows_are_configurable(self):
        self.boot_db()
        self.seed_obs(stale_days=10)
        self.assertEqual(180, db.retention_days_for("fire_observations"))
        with mock.patch.dict(os.environ, {"FIRE_OBS_RETENTION_DAYS": "7"}):
            self.assertEqual(7, db.retention_days_for("fire_observations"))
            report = db.run_retention_cycle(apply_changes=True, backup_first=False,
                                            tables=["fire_observations"])
        self.assertEqual(7, report["tables"]["fire_observations"]["retention_days"])
        self.assertEqual(1, report["tables"]["fire_observations"]["rows_deleted"])
        # A nonsensical window is clamped rather than allowed to wipe everything.
        with mock.patch.dict(os.environ, {"FIRE_OBS_RETENTION_DAYS": "0"}):
            self.assertEqual(1, db.retention_days_for("fire_observations"))

    def test_maintenance_scheduler_wires_retention_flags(self):
        sched = MaintenanceScheduler(retention_apply=False, backup_before_retention=True)
        with mock.patch.object(db, "run_retention_cycle", return_value={"tables": {}}) as cycle:
            sched.run_retention_now()
        self.assertFalse(cycle.call_args.kwargs["apply_changes"], "dry-run flag was overridden")
        self.assertTrue(cycle.call_args.kwargs["backup_first"])
        sched2 = MaintenanceScheduler(retention_apply=True, backup_before_retention=False)
        with mock.patch.object(db, "run_retention_cycle", return_value={"tables": {}}) as cycle2:
            sched2.run_retention_now()
        self.assertTrue(cycle2.call_args.kwargs["apply_changes"])
        self.assertFalse(cycle2.call_args.kwargs["backup_first"])


# =============================================================================
# Stage 5.5 - Backup / retention scheduling behaviour
# =============================================================================

class TestMaintenanceScheduling(Phase4TestCase):

    def test_intervals_default_from_env(self):
        with mock.patch.dict(os.environ, {"BACKUP_INTERVAL_SECONDS": "900",
                                          "RETENTION_INTERVAL_SECONDS": "1800"}, clear=False):
            sched = MaintenanceScheduler()
        self.assertEqual(900, sched.backup_interval)
        self.assertEqual(1800, sched.retention_interval)
        # An explicit argument always wins over the environment.
        self.assertEqual(60, MaintenanceScheduler(backup_interval_seconds=60).backup_interval)

    def test_first_backup_fires_on_boot_then_once(self):
        sched = MaintenanceScheduler(backup_interval_seconds=3600, retention_interval_seconds=3600)
        with mock.patch.object(db, "run_backup_cycle", return_value={"ok": True}) as cycle, \
             mock.patch.object(db, "run_retention_cycle", return_value={"tables": {}}) as retain, \
             mock.patch("backend.scheduler.time.sleep",
                        side_effect=lambda *_a: setattr(sched, "_running", False)):
            sched._running = True
            sched._run_loop()
        self.assertEqual(1, cycle.call_count)
        self.assertTrue(retain.call_count >= 1)
        self.assertEqual(1, sched.total_backups)
        self.assertIsNotNone(sched.last_backup)
        self.assertIsNotNone(sched.next_backup)
        self.assertTrue(sched.last_backup_ok)

    def test_thread_drives_the_backup_cycle(self):
        self.boot_db()
        # retention_apply=False keeps the boot retention a dry run, so it does
        # not trigger a second (pre-retain) snapshot and the count stays exact.
        sched = MaintenanceScheduler(backup_interval_seconds=3600, retention_interval_seconds=10 ** 9,
                                     retention_apply=False)
        sched.start()
        deadline = time.time() + 20
        while sched.total_backups == 0 and time.time() < deadline:
            time.sleep(0.1)
        sched.stop()
        self.assertFalse(sched._thread.is_alive(), "maintenance thread outlived stop()")
        self.assertEqual(1, sched.total_backups)
        self.assertTrue(sched.last_backup_ok)
        self.assertEqual(1, len(self.snapshot_files()))

    def test_retention_is_deferred_until_its_interval_elapses(self):
        """The loop measures against absolute time.time(); with an early clock
        the backup still runs at boot (explicit first_backup_done flag) while
        retention correctly waits for its interval rather than firing at t=0."""
        sched = MaintenanceScheduler(backup_interval_seconds=3600, retention_interval_seconds=3600,
                                     retention_apply=False)
        with mock.patch.object(db, "run_backup_cycle", return_value={"ok": True}), \
             mock.patch.object(db, "run_retention_cycle") as retain, \
             mock.patch("backend.scheduler.time.time", return_value=100.0), \
             mock.patch("backend.scheduler.time.sleep",
                        side_effect=lambda *_a: setattr(sched, "_running", False)):
            sched._running = True
            sched._run_loop()
        retain.assert_not_called()          # 100 - 0 = 100 < 3600
        self.assertEqual(1, sched.total_backups)  # boot snapshot still taken


class TestIngestionScheduling(Phase4TestCase):

    def test_intervals_default_from_env(self):
        with mock.patch.dict(os.environ, {"FIRMS_INTERVAL_SECONDS": "600",
                                          "WEATHER_INTERVAL_SECONDS": "60"}, clear=False):
            sched = IngestionScheduler()
        self.assertEqual(600, sched.firms_interval)
        self.assertEqual(60, sched.weather_interval)
        self.assertEqual(45, IngestionScheduler(firms_interval_seconds=45).firms_interval)

    def test_thread_runs_an_ingestion_pass_and_survives_failures(self):
        """A live thread must tick, fail safely on a broken provider and never
        take the process (i.e. the API) down. The FIRMS branch is forced
        unconfigured so only the weather outage surfaces as last_error, and no
        real network call is attempted on the boot tick."""
        sched = IngestionScheduler(firms_interval_seconds=10 ** 9, weather_interval_seconds=0)
        cfg = mock.Mock(is_configured=False)
        with mock.patch("backend.integrations.nasa_firms.FirmsConfig", return_value=cfg), \
             mock.patch("backend.integrations.weather.service.weather_service.refresh_cache",
                        side_effect=RuntimeError("provider outage")):
            sched.start()
            deadline = time.time() + 15
            while sched.last_error is None and time.time() < deadline:
                time.sleep(0.1)
            sched.stop()
        self.assertFalse(sched._thread.is_alive())
        self.assertIn("Weather update error", sched.last_error or "")
        self.assertIn("provider outage", sched.last_error or "")


# =============================================================================
# Stage 5.6 - Failure handling
# =============================================================================

class TestFailureHandling(Phase4TestCase):

    def test_firms_outage_is_recorded_scrubbed_and_never_propagates(self):
        sched = IngestionScheduler(firms_interval_seconds=0, weather_interval_seconds=10 ** 9)
        cfg = mock.Mock(is_configured=True)
        with mock.patch.dict(os.environ, {"NASA_FIRMS_MAP_KEY": FAKE_KEY}, clear=False), \
             mock.patch("backend.integrations.nasa_firms.FirmsConfig", return_value=cfg), \
             mock.patch("backend.integrations.nasa_firms.FirmsIngestionService") as svc, \
             mock.patch("backend.integrations.weather.service.weather_service.refresh_cache",
                        return_value=mock.MagicMock()), \
             mock.patch("backend.scheduler.time.sleep",
                        side_effect=lambda *_a: setattr(sched, "_running", False)):
            svc.return_value.ingest_observations.side_effect = RuntimeError(LEAK_URL)
            sched._running = True
            sched._run_loop()   # must not raise
        self.assertIn("FIRMS sync error", sched.last_error)
        self.assertNotIn(FAKE_KEY, sched.last_error)
        self.assertNotIn(FAKE_KEY, str(sched.get_status()))
        self.assertEqual(0, sched.total_firms_jobs)

    def test_unconfigured_key_skips_ingestion_without_error(self):
        sched = IngestionScheduler(firms_interval_seconds=0, weather_interval_seconds=10 ** 9)
        cfg = mock.Mock(is_configured=False)
        with mock.patch("backend.integrations.nasa_firms.FirmsConfig", return_value=cfg), \
             mock.patch("backend.integrations.nasa_firms.FirmsIngestionService") as svc, \
             mock.patch("backend.integrations.weather.service.weather_service.refresh_cache",
                        return_value=mock.MagicMock()), \
             mock.patch("backend.scheduler.time.sleep",
                        side_effect=lambda *_a: setattr(sched, "_running", False)):
            sched._running = True
            sched._run_loop()
        svc.return_value.ingest_observations.assert_not_called()
        self.assertEqual("SKIPPED_UNCONFIGURED", sched.last_firms_sync)
        self.assertIsNone(sched.last_error)

    def test_backup_failure_is_contained(self):
        sched = MaintenanceScheduler()
        with mock.patch.dict(os.environ, {"NASA_FIRMS_MAP_KEY": FAKE_KEY}, clear=False), \
             mock.patch.object(db, "run_backup_cycle", side_effect=RuntimeError(f"disk exploded at {LEAK_URL}")):
            report = sched.run_backup_now()
        self.assertFalse(report["ok"])
        self.assertIn("Backup error", sched.last_error)
        self.assertNotIn(FAKE_KEY, sched.last_error)
        self.assertNotIn(FAKE_KEY, str(sched.get_status()))
        self.assertFalse(sched.last_backup_ok)
        self.assertEqual(0, sched.total_backups)

    def test_retention_failure_is_contained(self):
        sched = MaintenanceScheduler()
        with mock.patch.object(db, "run_retention_cycle", side_effect=sqlite3.OperationalError("database is locked")):
            report = sched.run_retention_now()
        self.assertFalse(report["ok"])
        self.assertIn("database is locked", sched.last_error)
        self.assertEqual(0, sched.total_retention_runs)
        self.assertTrue(sched._backup_lock.acquire(blocking=False), "lock leaked after retention failure")
        sched._backup_lock.release()

    def test_missing_database_file_raises_loudly_not_silently(self):
        with self.assertRaises(RuntimeError):
            db.backup_database(label="empty")

    def test_api_stays_up_when_maintenance_fails(self):
        """A maintenance blow-up must never turn the public API into 500s, and
        the telemetry it returns must stay credential-free.

        The failure is driven through the real run_backup_now() path, so
        scrubbing is exercised where it actually happens (at write time via
        safe_error) rather than assuming the endpoint re-sanitises on read.
        """
        import json
        from fastapi.testclient import TestClient
        import backend.main as main_module
        self.boot_db()
        sched = main_module.maintenance_scheduler
        saved = (sched.last_error, sched.last_backup_ok, sched.total_backups)
        try:
            with mock.patch.dict(os.environ, {"NASA_FIRMS_MAP_KEY": FAKE_KEY}, clear=False), \
                 mock.patch.object(db, "run_backup_cycle",
                                   side_effect=RuntimeError(f"disk exploded near {LEAK_URL}")):
                sched.run_backup_now()
            client = TestClient(main_module.app)
            resp = client.get("/api/v1/maintenance/status")
            self.assertEqual(200, resp.status_code)
            body = resp.json()
            payload = json.dumps(body, default=str)
            self.assertNotIn(FAKE_KEY, payload, "MAP_KEY leaked through maintenance telemetry")
            self.assertIn("Backup error", body["lastError"])
            self.assertFalse(body["lastBackupOk"])
            for key in ("isRunning", "backupIntervalHours", "retentionIntervalHours", "retentionApply",
                        "backupBeforeRetention", "lastBackup", "nextBackup", "lastBackupOk",
                        "totalBackups", "lastRetention", "totalRetentionRuns", "offsiteConfigured",
                        "disk", "lastError"):
                self.assertIn(key, body)
            self.assertFalse(body["offsiteConfigured"])
            self.assertIn("free_mb", body["disk"])
        finally:
            sched.last_error, sched.last_backup_ok, sched.total_backups = saved


# =============================================================================
# Stage 5.7 - Concurrency and graceful shutdown
# =============================================================================

class TestConcurrentIngestionAndBackup(Phase4TestCase):

    def test_repeated_snapshot_read_and_write_cycles_stay_error_free(self):
        """A backup is a concurrent reader of a database that is being written
        (WAL + busy_timeout), so it must interleave with ingestion writes."""
        self.boot_db()

        errors = []
        stop = threading.Event()

        def ingest_writer():
            """Mimics one transaction per FirmsIngestionService ingestion pass."""
            while not stop.is_set():
                try:
                    with db.get_connection() as conn:
                        conn.execute("UPDATE data_sync_jobs SET status = status")
                        conn.execute(
                            "INSERT INTO simulation_history (created_at, fire_count,"
                            " wind_speed, wind_dir, pbl_height, baseline_aqi, bio_dec_pct,"
                            " happy_seeder_pct, predicted_aqi, predicted_pm25, predicted_pm10,"
                            " parali_pct, grap_stage, mitigation_drop) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            ("2026-01-02 10:00:00", 5, 90, 200, 100, 0, 0, 120, 40, 70, 5, 30.0, "Stage I", 5),
                        )
                except Exception as exc:  # pragma: no cover - asserted below
                    errors.append(("writer", repr(exc)))
                    return

        def backup_worker():
            while not stop.is_set():
                try:
                    db.run_backup_cycle(push_offsite=False, prune_old_snapshots=False)
                except Exception as exc:  # pragma: no cover - asserted below
                    errors.append(("backup", repr(exc)))
                    return
                time.sleep(0.02)

        writer = self.start_thread(threading.Thread(target=ingest_writer))
        copier = self.start_thread(threading.Thread(target=backup_worker))
        time.sleep(2.0)
        stop.set()
        writer.join(timeout=15)
        copier.join(timeout=15)

        self.assertFalse(errors, f"concurrent ingestion/backup raised: {errors[:3]}")
        self.assertTrue(self.db_path.exists())
        integrity = db._connect_for_admin(self.db_path, readonly=True)
        try:
            verdict = integrity.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            integrity.close()
        self.assertEqual("ok", str(verdict))
        self.assertGreaterEqual(len(self.snapshot_files()), 1)

    def test_status_endpoint_reflects_completed_backup(self):
        self.boot_db()
        sched = MaintenanceScheduler(backup_interval_seconds=3600, retention_interval_seconds=3600)
        with patch_module_clock(db):
            sched.run_backup_now()
        status = sched.get_status()
        self.assertEqual(1, status["totalBackups"])
        self.assertTrue(status["lastBackupOk"])
        self.assertIsNone(status["lastError"])


class TestGracefulShutdown(Phase4TestCase):

    def test_ingestion_loop_exits_promptly_and_leaves_no_threads(self):
        sched = IngestionScheduler(firms_interval_seconds=0, weather_interval_seconds=10 ** 9)
        cfg = mock.Mock(is_configured=False)
        sleeper = mock.Mock()

        def stop_on_second_sleep(*_a, **_k):
            sched._running = False

        sleeper.side_effect = stop_on_second_sleep
        with mock.patch("backend.integrations.nasa_firms.FirmsConfig", return_value=cfg), \
             mock.patch("backend.integrations.weather.service.weather_service.refresh_cache",
                        return_value=mock.MagicMock()), \
             mock.patch("backend.scheduler.time.sleep", sleeper):
            sched._running = True
            started = time.time()
            sched._run_loop()
        self.assertLess(time.time() - started, 5)
        self.assertFalse(sched._running)
        self.assertEqual(0, count_scheduler_threads())

    def test_stop_joins_a_live_thread(self):
        sched = MaintenanceScheduler(backup_interval_seconds=10 ** 9, retention_interval_seconds=10 ** 9)
        with mock.patch.object(sched, "run_backup_now", return_value={"ok": True}), \
             mock.patch.object(sched, "run_retention_now", return_value={}):
            sched.start()
            self.assertTrue(sched._thread.is_alive())
            sched.stop()
        self.assertFalse(sched._thread.is_alive())
        self.assertFalse(sched._running)
        self.assertEqual(0, count_scheduler_threads())

    def test_stop_while_a_backup_is_mid_flight_does_not_abort_the_file(self):
        """stop() must not kill an in-flight snapshot: the thread finishes the
        job, then exits, and the live database is left consistent."""
        self.boot_db()
        sched = MaintenanceScheduler(backup_interval_seconds=10 ** 9, retention_interval_seconds=10 ** 9)

        real_cycle = db.run_backup_cycle
        finished = []

        def slow_cycle(*a, **k):
            info = real_cycle(*a, **k)
            finished.append(info["backup"]["backup_path"])
            time.sleep(0.4)
            return info

        with mock.patch.object(db, "run_backup_cycle", side_effect=slow_cycle):
            thread = threading.Thread(target=sched.run_backup_now, daemon=True)
            thread.start()
            time.sleep(0.1)
            sched._running = False
            thread.join(timeout=15)
        sched.stop()
        self.assertFalse(thread.is_alive())
        self.assertEqual(1, len(finished))
        self.assertTrue(Path(finished[0]).exists())
        self.assertTrue(self.db_path.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
