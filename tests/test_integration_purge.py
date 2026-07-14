import tempfile
import unittest
from pathlib import Path

from integrations.purge import PurgeFileError, resolve_purge_archive_path


class PurgeSafetyContractTests(unittest.TestCase):
    def test_archive_paths_are_contained_and_traversal_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            safe = resolve_purge_archive_path(
                archive_dir=root,
                relative_path="doudian/1/orders/2026/07/1-000001.jsonl.gz.aes",
            )
            self.assertTrue(safe.is_relative_to(root.resolve()))
            for value in (
                "../escape.jsonl.gz.aes",
                "/absolute.jsonl.gz.aes",
                "exports/not-an-archive.csv",
            ):
                with self.subTest(value=value), self.assertRaises(PurgeFileError):
                    resolve_purge_archive_path(
                        archive_dir=root,
                        relative_path=value,
                    )


if __name__ == "__main__":
    unittest.main()
