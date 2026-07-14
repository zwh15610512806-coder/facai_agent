import os
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path

from services.backup_manager import (
    create_backup,
    ensure_daily_backup,
    prune_backups,
    restore_backup,
    verify_backup,
    verify_restore_drill,
)


class BackupManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "business.db"
        with closing(sqlite3.connect(self.source)) as connection:
            connection.execute("CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
            connection.execute("INSERT INTO products(name) VALUES ('奶冻粉')")
            connection.commit()

    def tearDown(self):
        self.temp.cleanup()

    def test_backup_is_consistent_copied_offsite_and_restorable(self):
        backup_dir = self.root / "backups"
        offsite_dir = self.root / "offsite"

        backup = create_backup(self.source, backup_dir=backup_dir, offsite_dir=offsite_dir)
        report = verify_backup(backup)
        restored = restore_backup(backup, self.root / "restored.db")

        self.assertEqual(report["integrity_check"], "ok")
        self.assertGreaterEqual(report["table_count"], 1)
        self.assertTrue((offsite_dir / backup.name).exists())
        self.assertFalse(Path(str(backup) + "-wal").exists())
        self.assertFalse(Path(str(backup) + "-shm").exists())
        with closing(sqlite3.connect(restored)) as connection:
            self.assertEqual(connection.execute("SELECT name FROM products").fetchone()[0], "奶冻粉")

    def test_restore_drill_verifies_backup_without_leaving_a_copy(self):
        backup = create_backup(self.source, backup_dir=self.root / "backups")

        report = verify_restore_drill(backup, work_dir=self.root / "drills")

        self.assertEqual(report["integrity_check"], "ok")
        self.assertGreaterEqual(report["table_count"], 1)
        self.assertEqual(list((self.root / "drills").iterdir()), [])

    def test_daily_backup_is_idempotent_and_retention_is_bounded(self):
        backup_dir = self.root / "backups"
        first = ensure_daily_backup(self.source, backup_dir=backup_dir)
        second = ensure_daily_backup(self.source, backup_dir=backup_dir)
        self.assertEqual(first, second)

        old_files = []
        for index in range(4):
            path = backup_dir / f"business_daily_2020010{index}_000000.db"
            path.write_bytes(b"old")
            timestamp = time.time() - (index + 40) * 86400
            os.utime(path, (timestamp, timestamp))
            old_files.append(path)
            Path(str(path) + "-shm").write_bytes(b"sidecar")

        removed = prune_backups(
            backup_dir,
            retention_days=30,
            max_daily_backups=2,
            max_migration_backups=1,
        )

        self.assertTrue(any(path in removed for path in old_files))
        for path in removed:
            self.assertFalse(Path(str(path) + "-shm").exists())
        self.assertTrue(first.exists())


if __name__ == "__main__":
    unittest.main()
