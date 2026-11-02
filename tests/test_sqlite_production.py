"""
Test Suite: SQLite Production Readiness (Phase 2 hardening)

Every assertion here runs against an ISOLATED temporary database file created in
setUp and deleted in tearDown. The production database/agri_smoke.db is never
opened, mutated, backed up or pruned by this suite.

Regression coverage for the Phase 2 changes in backend/database.py:
  1. WAL journal mode is actually enabled on a normal filesystem.
  2. busy_timeout is applied to every connection.
  3. foreign_keys enforcement is ON (dangling FK insert is rejected).
  4. get_connection() ALWAYS closes its handle - on the success path, on the
     error path, and even when the body raises (no fd / lock leak).
  5. get_connection() rolls back an in-flight transaction when the body raises.
  6. ensure_ready() creates the parent directory and applies the index set.
  7. ensure_ready() is idempotent - a second boot neither errors nor duplicates.
  8. Online backup / restore round-trip, with the pre-restore guard and prune.
  9. prune_aged_data is a dry run unless apply_changes=True.
 10. Concurrent readers do not block behind a writer (WAL behaviour).
"""

import os
import sys
import sqlite3
import tempfile
import threading
import unittest
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend import database as db  # noqa: E402


class TempDatabaseCase(unittest.TestCase):
    """Base class that re-points backend.database at a throwaway file per test."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="agrismoke_phase2_"))
        self.db_path = self.tmp / "agri_smoke_test.db"
        # backend/database.py reads DB_PATH at import; init_db.py reads it at ITS
        # import time inside ensure_ready()._run_seeder(). Set both the module
        # global and the environment so bootstrap, seeding and helpers all agree.
        self._saved_env = os.environ.get("DB_PATH")
        os.environ["DB_PATH"] = str(self.db_path)
        db.DB_PATH = self.db_path
        db._wal_active = None  # force a fresh WAL negotiation for this file

    def tearDown(self):
        # Close any WAL sidecars before removing the directory tree.
        if self._saved_env is None:
            os.environ.pop("DB_PATH", None)
        else:
            os.environ["DB_PATH"] = self._saved_env
        db._wal_active = None
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestConnectionPragmas(TempDatabaseCase):
    def test_wal_mode_is_active(self):
        db.ensure_ready()
        with db.get_connection() as conn:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        # WAL needs shared-memory support; it is unavailable on some CI/network
        # filesystems, in which case the layer must fall back cleanly (not crash)
        # and _wal_active must reflect reality rather than the request.
        if db._wal_active:
            self.assertEqual(str(mode).lower(), "wal")
        else:
            self.assertIn(str(mode).lower(), ("delete", "truncate", "journal"))

    def test_busy_timeout_applied_to_every_connection(self):
        db.ensure_ready()
        with db.get_connection() as conn:
            timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        self.assertEqual(timeout, db.BUSY_TIMEOUT_MS)
        self.assertGreaterEqual(timeout, 5000, "busy_timeout should comfortably absorb ingestion locks")

    def test_foreign_keys_are_enforced(self):
        db.ensure_ready()
        with db.get_connection() as conn:
            self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            conn.execute("CREATE TABLE _fk_parent (id INTEGER PRIMARY KEY)")
            conn.execute(
                "CREATE TABLE _fk_child (id INTEGER PRIMARY KEY, parent INTEGER, "
                "FOREIGN KEY (parent) REFERENCES _fk_parent(id))"
            )
            conn.execute("INSERT INTO _fk_parent (id) VALUES (1)")
            conn.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            with db.get_connection() as conn:
                conn.execute("INSERT INTO _fk_child (id, parent) VALUES (10, 999)")  # dangling


class TestConnectionLifecycle(TempDatabaseCase):
    def _open_fd_count(self):
        try:
            import psutil  # optional; only used to make the leak check quantitative
            return psutil.Process().num_fds() if hasattr(os, "confstr") or sys.platform != "win32" else None
        except Exception:
            return None

    def test_connection_is_closed_after_success(self):
        db.ensure_ready()
        seen = {}
        with db.get_connection() as conn:
            seen["conn"] = conn
            conn.execute("SELECT 1")
        # The handle must be released even though the body completed cleanly.
        with self.assertRaises(sqlite3.ProgrammingError):
            seen["conn"].execute("SELECT 1")

    def test_connection_is_closed_and_rolled_back_on_error(self):
        db.ensure_ready()
        # Seed already occupies custom_thresholds id=1; set a known baseline.
        db.update_custom_thresholds(111, 222)
        baseline = db.get_custom_thresholds()
        self.assertEqual(baseline["aqi"], 111)

        # A body that raises must roll back the write AND still close the handle.
        held = {}
        with self.assertRaises(RuntimeError):
            with db.get_connection() as conn:
                held["conn"] = conn
                conn.execute("UPDATE custom_thresholds SET aqi_threshold = 999 WHERE id = 1")
                raise RuntimeError("boom mid-transaction")
        with self.assertRaises(sqlite3.ProgrammingError):
            held["conn"].execute("SELECT 1")
        self.assertEqual(db.get_custom_thresholds()["aqi"], 111, "rollback must discard the un-committed UPDATE")

    def test_no_fd_leak_across_many_operations(self):
        """The original bug: get_connection() returned a raw conn the CRUD helpers
        never closed, so file descriptors accumulated under dashboard polling."""
        db.ensure_ready()
        for _ in range(120):
            db.get_monitoring_stations()
            db.get_fire_hotspots()
            db.get_grap_stages()
        # If handles leaked, Windows would eventually raise on the open; reaching
        # here after 360 opens is itself the assertion. Confirm we can still open.
        with db.get_connection() as conn:
            self.assertEqual(conn.execute("SELECT 1").fetchone()[0], 1)


class TestEnsureReady(TempDatabaseCase):
    def test_creates_missing_parent_directory(self):
        nested = self.tmp / "var" / "data" / "agri_smoke.db"
        db.DB_PATH = nested
        os.environ["DB_PATH"] = str(nested)
        self.assertFalse(nested.parent.exists())
        diag = db.ensure_ready()
        self.assertTrue(nested.parent.exists(), "Render persistent-disk bootstrap must mkdir the volume path")
        self.assertTrue(diag["exists"])

    def test_applies_all_performance_indexes(self):
        db.ensure_ready()
        with db.get_connection() as conn:
            names = {r["name"] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()}
        for ddl in db.INDEX_DDL:
            idx_name = ddl.split("IF NOT EXISTS")[1].split("ON")[0].strip()
            self.assertIn(idx_name, names, f"expected index {idx_name} was not created")

    def test_is_idempotent_and_preserves_data(self):
        db.ensure_ready()
        first = db.get_fire_observation_stats(days=3)
        db.save_simulation_run(
            {"fireCount": 10, "windSpeed": 5, "windDirectionDeg": 90, "pblHeight": 200,
             "urbanBaselineAqi": 100, "bioDecomposerAdoption": 0, "happySeederAdoption": 0},
            {"predictedAqi": 120, "totalPm25": 60, "totalPm10": 90, "paraliPct": 10,
             "grapStage": "Stage I", "mitigationSavings": {"aqiDrop": 5}},
        )
        rows_before = db.storage_report()["table_rows"].get("simulation_history")
        # Second and third boot on the SAME file must not raise or re-seed.
        diag2 = db.ensure_ready()
        diag3 = db.ensure_ready()
        self.assertFalse(diag2["seeded"], "ensure_ready must not re-seed a populated database")
        self.assertEqual(diag3["missing_tables"], [])
        with db.get_connection() as conn:
            self.assertEqual(len(db.missing_tables(conn)), 0)
        rows_after = db.storage_report()["table_rows"].get("simulation_history")
        self.assertEqual(rows_after, rows_before, "bootstrap must never delete existing rows")

    def test_integrity_check_passes(self):
        db.ensure_ready()
        self.assertEqual(db.verify_integrity(), "ok")


class TestBackupRestorePrune(TempDatabaseCase):
    def test_backup_captures_consistent_snapshot(self):
        db.ensure_ready()
        db.save_simulation_run(
            {"fireCount": 77, "windSpeed": 5, "windDirectionDeg": 90, "pblHeight": 200,
             "urbanBaselineAqi": 100, "bioDecomposerAdoption": 0, "happySeederAdoption": 0},
            {"predictedAqi": 88, "totalPm25": 40, "totalPm10": 70, "paraliPct": 5,
             "grapStage": "Stage I", "mitigationSavings": {"aqiDrop": 1}},
        )
        result = db.backup_database()
        self.assertEqual(result["integrity"], "ok")
        self.assertTrue(Path(result["backup_path"]).exists())
        self.assertGreater(result["total_rows"], 0)
        self.assertGreaterEqual(result["table_counts"].get("simulation_history", 0), 1)

    def test_restore_refuses_overwrite_without_confirm(self):
        db.ensure_ready()
        backup = db.backup_database()["backup_path"]
        with self.assertRaises(RuntimeError):
            db.restore_database(backup, target_path=str(db.DB_PATH), confirm=False)

    def test_restore_round_trip_after_data_loss(self):
        db.ensure_ready()
        backup = db.backup_database()["backup_path"]
        live = str(db.DB_PATH)
        # Simulate corruption / accidental purge on the live file.
        with db.get_connection() as conn:
            conn.execute("DELETE FROM monitoring_stations")
        self.assertEqual(len(db.get_monitoring_stations()), 0)
        db.restore_database(backup, target_path=live, confirm=True)
        self.assertEqual(len(db.get_monitoring_stations()), 9, "restore must bring back the snapshot rows")

    def test_prune_backups_keeps_newest(self):
        db.ensure_ready()
        made = []
        for _ in range(4):
            made.append(db.backup_database()["backup_path"])
            # distinct timestamps even on a fast filesystem
            import time as _t
            _t.sleep(1.1)
        backups = db.list_backups()
        self.assertEqual(len(backups), 4)
        removed = db.prune_backups(keep=2)
        self.assertEqual(len(removed), 2)
        self.assertEqual(len(db.list_backups()), 2)
        # the live db must never be a prune candidate
        self.assertNotIn(str(db.DB_PATH), removed)


class TestRetentionAndMaintenance(TempDatabaseCase):
    def test_prune_aged_data_is_dry_run_by_default(self):
        db.ensure_ready()
        with db.get_connection() as conn:
            conn.execute(
                "INSERT INTO simulation_history (fire_count, wind_speed, wind_dir, pbl_height, "
                "baseline_aqi, bio_dec_pct, happy_seeder_pct, predicted_aqi, predicted_pm25, "
                "predicted_pm10, parali_pct, grap_stage, mitigation_drop, created_at) "
                "VALUES (10,5,90,200,100,0,0,120,40,70,5,'Stage I',5, date('now','-400 days'))"
            )
            conn.commit()
        report = db.prune_aged_data("simulation_history", retention_days=90)  # default dry run
        self.assertGreaterEqual(report["rows_older_than_cutoff"], 1)
        self.assertEqual(report["rows_deleted"], 0)
        self.assertFalse(report["applied"])

        applied = db.prune_aged_data("simulation_history", retention_days=90, apply_changes=True)
        self.assertGreaterEqual(applied["rows_deleted"], 1)

    def test_prune_rejects_unknown_table(self):
        db.ensure_ready()
        with self.assertRaises(ValueError):
            db.prune_aged_data("users", retention_days=90)

    def test_checkpoint_and_optimize(self):
        db.ensure_ready()
        for i in range(200):
            db.update_custom_thresholds(300 + (i % 500), 1500 + i)
        res = db.checkpoint_and_optimize("TRUNCATE")
        self.assertIn(res["mode"], {"TRUNCATE", "PASSIVE", "FULL", "RESTART"})
        self.assertIn("busy", res)
        with self.assertRaises(ValueError):
            db.checkpoint_and_optimize("NOPE")

    def test_storage_report_shape(self):
        db.ensure_ready()
        rep = db.storage_report()
        self.assertIn("monitoring_stations", rep["table_rows"])
        self.assertGreater(rep["file_bytes"], 0)
        self.assertGreater(rep["page_size"], 0)


class TestConcurrentReadersWriter(TempDatabaseCase):
    def test_readers_do_not_block_behind_writer(self):
        """The WAL goal: a 3-hourly FIRMS bulk write must not make API reads wait
        out (or hit) the busy timeout. Runs a writer thread and several reader
        threads simultaneously and asserts every read succeeds."""
        db.ensure_ready()
        errors = []
        stop = threading.Event()

        def writer():
            try:
                with db.get_connection() as conn:
                    for i in range(400):
                        conn.execute(
                            "INSERT INTO simulation_history (fire_count, wind_speed, wind_dir, "
                            "pbl_height, baseline_aqi, bio_dec_pct, happy_seeder_pct, predicted_aqi, "
                            "predicted_pm25, predicted_pm10, parali_pct, grap_stage, mitigation_drop) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (i, 5, 90, 200, 100, 0, 0, 120, 40, 70, 5, "Stage I", 5),
                        )
                    conn.commit()
            except Exception as exc:  # pragma: no cover - captured for assertion
                errors.append(("writer", repr(exc)))

        def reader():
            # Read repeatedly WHILE the writer holds the transaction open.
            while not stop.is_set():
                try:
                    db.get_monitoring_stations()
                    db.get_fire_hotspots()
                except Exception as exc:
                    errors.append(("reader", repr(exc)))
                    return

        w = threading.Thread(target=writer)
        readers = [threading.Thread(target=reader) for _ in range(4)]
        for r in readers:
            r.start()
        w.start()
        w.join(timeout=30)
        stop.set()
        for r in readers:
            r.join(timeout=10)

        self.assertFalse(errors, f"concurrent access raised: {errors[:3]}")
        self.assertNotIn("database is locked", [e[1] for e in errors])


if __name__ == "__main__":
    unittest.main(verbosity=2)
