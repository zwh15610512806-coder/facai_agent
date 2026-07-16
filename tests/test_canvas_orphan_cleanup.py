import os
import subprocess
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4


class CanvasOrphanCleanupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sandbox = Path(self.tmp.name)
        self.data_root = self.sandbox / "canvas-data"
        self.now = datetime(2026, 7, 14, 12, 0, 0, tzinfo=UTC)
        self.cutoff = self.now - timedelta(hours=24)
        self.cutoff_ns = self._datetime_ns(self.cutoff)

        from services.canvas import storage

        self.storage = storage
        self.data_patch = patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root))
        self.data_patch.start()

    def tearDown(self):
        self.data_patch.stop()
        self.tmp.cleanup()

    @staticmethod
    def _datetime_ns(value: datetime) -> int:
        epoch = datetime(1970, 1, 1, tzinfo=UTC)
        delta = value.astimezone(UTC) - epoch
        return (
            (delta.days * 86_400 + delta.seconds) * 1_000_000_000
            + delta.microseconds * 1_000
        )

    def _project_root(self, project_id: str | None = None) -> tuple[str, Path]:
        project_id = project_id or str(uuid4())
        return project_id, self.storage.ensure_project_tree(project_id)

    @staticmethod
    def _write_at(path: Path, *, mtime_ns: int, data: bytes = b"temporary") -> Path:
        path.write_bytes(data)
        os.utime(path, ns=(mtime_ns, mtime_ns))
        return path

    def _assert_storage_error(self, expected_code: str, callback) -> None:
        with self.assertRaises(self.storage.CanvasStorageError) as raised:
            callback()
        self.assertEqual(expected_code, raised.exception.code)

    def _make_directory_link(self, link: Path, target: Path) -> None:
        try:
            link.symlink_to(target, target_is_directory=True)
            return
        except OSError as symlink_error:
            if os.name != "nt":
                self.skipTest(f"directory symlinks are unavailable: {symlink_error}")
        completed = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if completed.returncode != 0:
            self.skipTest("directory symlinks and junctions are unavailable")

    def test_deletes_only_unreferenced_uploading_files_at_or_before_boundary(self):
        project_a, root_a = self._project_root()
        project_b, root_b = self._project_root()
        tmp_a = root_a / "tmp"
        tmp_b = root_b / "tmp"

        old = self._write_at(
            tmp_a / "old.uploading",
            mtime_ns=self.cutoff_ns - 1_000_000_000,
        )
        boundary = self._write_at(
            tmp_b / "boundary.uploading",
            mtime_ns=self.cutoff_ns,
        )
        young = self._write_at(
            tmp_a / "young.uploading",
            mtime_ns=self.cutoff_ns + 1_000_000_000,
        )
        referenced = self._write_at(
            tmp_a / "referenced.uploading",
            mtime_ns=self.cutoff_ns - 2_000_000_000,
        )
        upper = self._write_at(
            tmp_a / "upper.UPLOADING",
            mtime_ns=self.cutoff_ns - 2_000_000_000,
        )
        dotfile = self._write_at(
            tmp_a / ".uploading",
            mtime_ns=self.cutoff_ns - 2_000_000_000,
        )
        other_tmp = self._write_at(
            tmp_a / "compose.tmp",
            mtime_ns=self.cutoff_ns - 2_000_000_000,
        )
        uploading_directory = tmp_a / "directory.uploading"
        uploading_directory.mkdir()
        formal_asset = self._write_at(
            root_a / "working" / f"{uuid4()}.png",
            mtime_ns=self.cutoff_ns - 2_000_000_000,
        )
        outside = self._write_at(
            self.sandbox / "outside.uploading",
            mtime_ns=self.cutoff_ns - 2_000_000_000,
        )

        deleted = self.storage.cleanup_stale_temporary_files(
            referenced_relative_paths={
                f"{project_a}/tmp/{referenced.name}",
            },
            now=self.now,
        )

        self.assertEqual(2, deleted)
        self.assertFalse(old.exists())
        self.assertFalse(boundary.exists())
        for preserved in (
            young,
            referenced,
            upper,
            dotfile,
            other_tmp,
            uploading_directory,
            formal_asset,
            outside,
        ):
            self.assertTrue(preserved.exists(), preserved)
        self.assertTrue((root_a / "tmp").is_dir())
        self.assertTrue((root_b / "tmp").is_dir())
        self.assertNotEqual(project_a, project_b)

    def test_uses_pinned_handle_deletion_and_never_path_unlink(self):
        _project_id, root = self._project_root()
        candidate = self._write_at(
            root / "tmp" / "owned.uploading",
            mtime_ns=self.cutoff_ns,
        )

        with (
            patch.object(
                self.storage,
                "_dispose_pinned_entry",
                wraps=self.storage._dispose_pinned_entry,
            ) as dispose,
            patch.object(Path, "unlink", side_effect=AssertionError("path unlink is forbidden")),
        ):
            deleted = self.storage.cleanup_stale_temporary_files(
                referenced_relative_paths=set(),
                cutoff=self.cutoff,
            )

        self.assertEqual(1, deleted)
        self.assertFalse(candidate.exists())
        self.assertEqual(1, dispose.call_count)
        pin = dispose.call_args.args[0]
        self.assertEqual("tmp", pin.parent.name)
        self.assertEqual("owned.uploading", pin.name)
        self.assertTrue(pin.closed)

    def test_file_that_becomes_young_after_preflight_is_not_deleted(self):
        _project_id, root = self._project_root()
        candidate = self._write_at(
            root / "tmp" / "racing.uploading",
            mtime_ns=self.cutoff_ns - 1,
        )
        observed_times = [
            self.cutoff_ns - 1,
            self.cutoff_ns - 1,
            self.cutoff_ns + 1,
        ]
        real_last_write = self.storage._pinned_file_last_write_ns

        def changing_last_write(pin):
            if observed_times:
                return observed_times.pop(0)
            return real_last_write(pin)

        with patch.object(
            self.storage,
            "_pinned_file_last_write_ns",
            side_effect=changing_last_write,
        ) as last_write:
            deleted = self.storage.cleanup_stale_temporary_files(
                referenced_relative_paths=set(),
                cutoff=self.cutoff,
            )

        self.assertEqual(0, deleted)
        self.assertTrue(candidate.exists())
        self.assertEqual(3, last_write.call_count)

    def test_wide_tree_fails_before_deleting_any_candidate(self):
        _project_id, root = self._project_root()
        candidates = [
            self._write_at(
                root / "tmp" / f"{index}.uploading",
                mtime_ns=self.cutoff_ns - 1,
            )
            for index in range(3)
        ]

        with patch.object(self.storage, "CANVAS_MAX_TREE_ENTRIES", 2):
            self._assert_storage_error(
                "canvas_storage_entry_limit_exceeded",
                lambda: self.storage.cleanup_stale_temporary_files(
                    referenced_relative_paths=set(),
                    now=self.now,
                ),
            )

        self.assertTrue(all(path.exists() for path in candidates))

    def test_noncanonical_project_entry_fails_closed_without_partial_deletion(self):
        _project_id, root = self._project_root()
        candidate = self._write_at(
            root / "tmp" / "candidate.uploading",
            mtime_ns=self.cutoff_ns - 1,
        )
        unexpected = self.data_root / "not-a-project"
        unexpected.mkdir()
        unexpected_file = self._write_at(
            unexpected / "outside.uploading",
            mtime_ns=self.cutoff_ns - 1,
        )

        self._assert_storage_error(
            "canvas_storage_unsafe_entry",
            lambda: self.storage.cleanup_stale_temporary_files(
                referenced_relative_paths=set(),
                now=self.now,
            ),
        )

        self.assertTrue(candidate.exists())
        self.assertTrue(unexpected_file.exists())

    def test_reparse_point_fails_closed_without_partial_deletion(self):
        _project_id, root = self._project_root()
        candidate = self._write_at(
            root / "tmp" / "candidate.uploading",
            mtime_ns=self.cutoff_ns - 1,
        )
        outside = self.sandbox / "junction-target"
        outside.mkdir()
        marker = outside / "marker.txt"
        marker.write_text("outside", encoding="utf-8")
        self._make_directory_link(root / "tmp" / "linked.uploading", outside)

        self._assert_storage_error(
            "canvas_storage_reparse_point",
            lambda: self.storage.cleanup_stale_temporary_files(
                referenced_relative_paths=set(),
                now=self.now,
            ),
        )

        self.assertTrue(candidate.exists())
        self.assertEqual("outside", marker.read_text(encoding="utf-8"))

    @unittest.skipUnless(os.name == "nt", "alternate data streams are Windows-only")
    def test_alternate_data_stream_fails_closed_without_partial_deletion(self):
        _project_id, root = self._project_root()
        candidate = self._write_at(
            root / "tmp" / "candidate.uploading",
            mtime_ns=self.cutoff_ns - 1,
        )
        with_ads = self._write_at(
            root / "tmp" / "ads.uploading",
            mtime_ns=self.cutoff_ns - 1,
        )
        with open(f"{with_ads}:secret", "wb") as stream:
            stream.write(b"secret")

        self._assert_storage_error(
            "canvas_storage_unsafe_entry",
            lambda: self.storage.cleanup_stale_temporary_files(
                referenced_relative_paths=set(),
                now=self.now,
            ),
        )

        self.assertTrue(candidate.exists())
        self.assertTrue(with_ads.exists())

    def test_invalid_references_and_conflicting_time_inputs_fail_closed(self):
        self._project_root()

        for references in ({"../outside.uploading"}, {"not-a-uuid/tmp/file.uploading"}):
            with self.subTest(references=references):
                self._assert_storage_error(
                    "canvas_storage_path_invalid",
                    lambda: self.storage.cleanup_stale_temporary_files(
                        referenced_relative_paths=references,
                        now=self.now,
                    ),
                )

        self._assert_storage_error(
            "canvas_storage_cleanup_invalid",
            lambda: self.storage.cleanup_stale_temporary_files(
                referenced_relative_paths=set(),
                now=self.now,
                cutoff=self.cutoff,
            ),
        )


if __name__ == "__main__":
    unittest.main()
