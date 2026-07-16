from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from services.canvas import storage


class CanvasStorageShareRetryTests(unittest.TestCase):
    def test_retries_only_transient_windows_share_violations(self) -> None:
        sharing_error = storage.CanvasStorageError(
            "canvas_storage_io_failed", "canvas storage I/O failed"
        )
        sharing_violation = PermissionError(32, "sharing violation")
        sharing_violation.winerror = 32
        sharing_error.__cause__ = sharing_violation
        expected = object()

        with (
            patch.object(storage.os, "name", "nt"),
            patch("services.canvas.storage.time.sleep") as sleep,
            patch(
                "services.canvas.storage._open_pinned_entry_once",
                side_effect=[sharing_error, expected],
            ) as open_once,
        ):
            result = storage._open_pinned_entry(Path("C:/canvas"), kind="directory")

        self.assertIs(result, expected)
        self.assertEqual(open_once.call_count, 2)
        sleep.assert_called_once_with(0.01)

    def test_does_not_retry_non_share_storage_errors(self) -> None:
        failure = storage.CanvasStorageError("canvas_storage_path_invalid", "invalid")

        with (
            patch.object(storage.os, "name", "nt"),
            patch("services.canvas.storage.time.sleep") as sleep,
            patch(
                "services.canvas.storage._open_pinned_entry_once",
                side_effect=failure,
            ) as open_once,
        ):
            with self.assertRaisesRegex(storage.CanvasStorageError, "invalid"):
                storage._open_pinned_entry(Path("C:/canvas"), kind="directory")

        self.assertEqual(open_once.call_count, 1)
        sleep.assert_not_called()

    def test_stops_after_the_bounded_windows_share_release_window(self) -> None:
        sharing_error = storage.CanvasStorageError(
            "canvas_storage_io_failed", "canvas storage I/O failed"
        )
        sharing_violation = PermissionError(32, "sharing violation")
        sharing_violation.winerror = 32
        sharing_error.__cause__ = sharing_violation

        with (
            patch.object(storage.os, "name", "nt"),
            patch("services.canvas.storage.time.sleep") as sleep,
            patch(
                "services.canvas.storage._open_pinned_entry_once",
                side_effect=sharing_error,
            ) as open_once,
        ):
            with self.assertRaisesRegex(storage.CanvasStorageError, "I/O failed"):
                storage._open_pinned_entry(Path("C:/canvas"), kind="directory")

        self.assertEqual(open_once.call_count, 20)
        self.assertEqual(19, sleep.call_count)
        sleep.assert_any_call(0.19)

    def test_publish_retries_transient_windows_share_violations(self) -> None:
        source_parent = storage._PinnedEntry(
            Path("C:/canvas/tmp"), 11, (1, 1), 1, 0, 0, 0, True
        )
        destination_parent = storage._PinnedEntry(
            Path("C:/canvas/generated"), 12, (1, 2), 2, 0, 0, 0, True
        )
        pin = storage._PinnedEntry(
            Path("C:/canvas/tmp/result.partial"), 13, (1, 3), 3, 0, 0, 4, False,
            parent=source_parent,
            name="result.partial",
        )

        with (
            patch.object(storage.os, "name", "nt"),
            patch("services.canvas.storage.time.sleep") as sleep,
            patch("services.canvas.storage._NtSetInformationFile", side_effect=[-1, 0]) as rename,
            patch("services.canvas.storage._RtlNtStatusToDosError", return_value=32),
        ):
            storage._rename_pinned_file_no_replace(pin, destination_parent, "result.verified")

        self.assertEqual(rename.call_count, 2)
        sleep.assert_called_once_with(0.01)
        self.assertEqual(pin.path, Path("C:/canvas/generated/result.verified"))
        self.assertIs(pin.parent, destination_parent)
        self.assertEqual(pin.name, "result.verified")


if __name__ == "__main__":
    unittest.main()
