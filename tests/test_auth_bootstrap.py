import tempfile
import unittest
from pathlib import Path

from scripts.bootstrap_auth import ROLE_KEYS, bootstrap_auth


class AuthBootstrapTests(unittest.TestCase):
    def test_enables_auth_generates_missing_roles_and_preserves_existing_token(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text(
                "DEEPSEEK_API_KEY=keep-me\n"
                "FACAI_AUTH_ENABLED=0\n"
                "FACAI_ADMIN_TOKEN=already-configured\n",
                encoding="utf-8",
            )

            created = bootstrap_auth(path)
            values = dict(
                line.split("=", 1)
                for line in path.read_text(encoding="utf-8").splitlines()
                if "=" in line
            )

        self.assertEqual(values["DEEPSEEK_API_KEY"], "keep-me")
        self.assertEqual(values["FACAI_AUTH_ENABLED"], "1")
        self.assertEqual(values["FACAI_ADMIN_TOKEN"], "already-configured")
        self.assertEqual(set(created), set(ROLE_KEYS) - {"FACAI_ADMIN_TOKEN"})
        self.assertGreaterEqual(len(values["FACAI_OPERATOR_TOKEN"]), 40)
        self.assertNotEqual(values["FACAI_OPERATOR_TOKEN"], values["FACAI_VIEWER_TOKEN"])

    def test_rotate_replaces_all_role_tokens(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text(
                "FACAI_ADMIN_TOKEN=old-admin\n"
                "FACAI_OPERATOR_TOKEN=old-operator\n"
                "FACAI_VIEWER_TOKEN=old-viewer\n",
                encoding="utf-8",
            )

            rotated = bootstrap_auth(path, rotate=True)
            values = dict(
                line.split("=", 1)
                for line in path.read_text(encoding="utf-8").splitlines()
                if "=" in line
            )

        self.assertEqual(set(rotated), set(ROLE_KEYS))
        self.assertNotEqual(values["FACAI_ADMIN_TOKEN"], "old-admin")
        self.assertNotEqual(values["FACAI_OPERATOR_TOKEN"], "old-operator")
        self.assertNotEqual(values["FACAI_VIEWER_TOKEN"], "old-viewer")


if __name__ == "__main__":
    unittest.main()
