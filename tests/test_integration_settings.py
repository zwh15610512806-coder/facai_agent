import base64
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

import config

from integrations.settings import IntegrationSettings, load_integration_settings


ROOT = Path(__file__).resolve().parents[1]


def _base64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _valid_environment(*, archive_dir: Path | None = None) -> dict[str, str]:
    archive = archive_dir or (ROOT / "data" / "integration-archive")
    return {
        "FACAI_INTEGRATIONS_MASTER_KEY": _base64url(b"m" * 32),
        "FACAI_INTEGRATIONS_INTERNAL_BASE_URL": "https://admin.example.test:8443",
        "FACAI_INTEGRATIONS_PUBLIC_BASE_URL": "https://callbacks.example.test",
        "FACAI_INTEGRATION_ARCHIVE_DIR": str(archive.resolve()),
        "FACAI_INTEGRATIONS_TRUSTED_PROXY_CIDRS": "10.20.0.0/16,2001:db8::/32",
        "FACAI_INTEGRATION_WORKER_CONCURRENCY": "3",
        "DATABASE_URL": "postgresql+psycopg://facai@db.example/facai",
    }


class IntegrationDependencyContractTests(unittest.TestCase):
    def test_runtime_dependencies_are_pinned(self):
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("alembic==1.18.5", requirements)
        self.assertIn("psycopg[binary]==3.3.4", requirements)
        self.assertIn("cryptography==49.0.0", requirements)

    def test_env_example_documents_integration_settings_without_secrets(self):
        content = (ROOT / ".env.example").read_text(encoding="utf-8")
        for key in (
            "FACAI_INTEGRATIONS_MASTER_KEY",
            "FACAI_INTEGRATIONS_INTERNAL_BASE_URL",
            "FACAI_INTEGRATIONS_PUBLIC_BASE_URL",
            "FACAI_INTEGRATION_ARCHIVE_DIR",
            "FACAI_INTEGRATIONS_TRUSTED_PROXY_CIDRS",
            "FACAI_DESTRUCTIVE_TEST_DATABASE_ACK",
        ):
            self.assertRegex(content, rf"(?m)^{key}=$")


class IntegrationSettingsTests(unittest.TestCase):
    def test_missing_configuration_returns_stable_readiness_errors(self):
        settings = load_integration_settings({})

        self.assertIsInstance(settings, IntegrationSettings)
        self.assertFalse(settings.credential_ready)
        self.assertEqual(
            settings.errors,
            (
                "FACAI_INTEGRATIONS_MASTER_KEY",
                "FACAI_INTEGRATIONS_INTERNAL_BASE_URL",
                "FACAI_INTEGRATIONS_PUBLIC_BASE_URL",
                "FACAI_INTEGRATION_ARCHIVE_DIR",
                "DATABASE_URL",
            ),
        )
        self.assertEqual(settings.trusted_proxy_networks, ())
        self.assertEqual(settings.worker_concurrency, 4)

    def test_valid_configuration_is_frozen_and_credential_ready(self):
        settings = load_integration_settings(_valid_environment())

        self.assertTrue(settings.credential_ready)
        self.assertEqual(settings.errors, ())
        self.assertEqual(settings.master_key, b"m" * 32)
        self.assertEqual(settings.worker_concurrency, 3)
        self.assertEqual(
            tuple(str(network) for network in settings.trusted_proxy_networks),
            ("10.20.0.0/16", "2001:db8::/32"),
        )
        with self.assertRaises(FrozenInstanceError):
            settings.worker_concurrency = 9

    def test_master_key_requires_canonical_urlsafe_base64_and_exactly_32_bytes(self):
        cases = {
            "too-short": _base64url(b"m" * 31),
            "too-long": _base64url(b"m" * 33),
            "standard-alphabet": base64.b64encode(bytes([251]) * 32).decode("ascii"),
            "malformed": "not base64url!",
        }
        for name, value in cases.items():
            with self.subTest(name=name):
                values = _valid_environment()
                values["FACAI_INTEGRATIONS_MASTER_KEY"] = value
                settings = load_integration_settings(values)
                self.assertFalse(settings.credential_ready)
                self.assertIsNone(settings.master_key)
                self.assertIn("FACAI_INTEGRATIONS_MASTER_KEY", settings.errors)

    def test_master_secret_rejects_base64_padding(self):
        values = _valid_environment()
        values["FACAI_INTEGRATIONS_MASTER_KEY"] += "="
        settings = load_integration_settings(values)
        self.assertIn("FACAI_INTEGRATIONS_MASTER_KEY", settings.errors)
        self.assertIsNone(settings.master_key)
        self.assertFalse(settings.credential_ready)

    def test_urls_must_be_origin_only_and_https_outside_loopback(self):
        invalid_origins = (
            "http://admin.example.test",
            "https://admin.example.test/",
            "https://admin.example.test/path",
            "https://admin.example.test?query=1",
            "https://admin.example.test?",
            "https://admin.example.test#fragment",
            "https://admin.example.test#",
            "https://user@admin.example.test",
            "https://admin.example.test:",
            "https://admin.example.test:0",
            "\x01https://admin.example.test",
            "https://admin.example.test\x7f",
            "https://admin.example.test\\@evil.example.test",
            "ftp://admin.example.test",
            "https://",
        )
        for origin in invalid_origins:
            with self.subTest(origin=origin):
                values = _valid_environment()
                values["FACAI_INTEGRATIONS_INTERNAL_BASE_URL"] = origin
                settings = load_integration_settings(values)
                self.assertFalse(settings.credential_ready)
                self.assertIn("FACAI_INTEGRATIONS_INTERNAL_BASE_URL", settings.errors)

    def test_http_is_allowed_only_for_exact_localhost_and_loopback_ips(self):
        for origin in (
            "http://localhost:8001",
            "http://127.0.0.1:8001",
            "http://[::1]:8001",
        ):
            with self.subTest(origin=origin):
                values = _valid_environment()
                values["FACAI_INTEGRATIONS_INTERNAL_BASE_URL"] = origin
                settings = load_integration_settings(values)
                self.assertTrue(settings.credential_ready, settings.errors)

        values = _valid_environment()
        values["FACAI_INTEGRATIONS_INTERNAL_BASE_URL"] = "http://localhost.example.test:8001"
        settings = load_integration_settings(values)
        self.assertFalse(settings.credential_ready)

    def test_production_internal_and_public_hosts_must_differ(self):
        values = _valid_environment()
        values["FACAI_INTEGRATIONS_INTERNAL_BASE_URL"] = "https://same.example.test:8443"
        values["FACAI_INTEGRATIONS_PUBLIC_BASE_URL"] = "https://same.example.test"

        settings = load_integration_settings(values)

        self.assertFalse(settings.credential_ready)
        self.assertIn("FACAI_INTEGRATIONS_PUBLIC_BASE_URL", settings.errors)

    def test_loopback_origins_require_distinct_effective_authorities(self):
        values = _valid_environment()
        values["FACAI_INTEGRATIONS_INTERNAL_BASE_URL"] = "http://127.0.0.1:8001"
        values["FACAI_INTEGRATIONS_PUBLIC_BASE_URL"] = "http://127.0.0.1:8001"
        same = load_integration_settings(values)
        self.assertFalse(same.credential_ready)
        self.assertIn("FACAI_INTEGRATIONS_PUBLIC_BASE_URL", same.errors)

        values["FACAI_INTEGRATIONS_PUBLIC_BASE_URL"] = "http://127.0.0.1:8002"
        distinct = load_integration_settings(values)
        self.assertTrue(distinct.credential_ready, distinct.errors)

        for internal_origin, public_origin in (
            ("http://localhost", "https://localhost"),
            ("http://localhost:80", "http://localhost:8002"),
            ("http://127.0.0.1:8001", "https://127.0.0.1:443"),
        ):
            with self.subTest(
                internal_origin=internal_origin,
                public_origin=public_origin,
            ):
                values = _valid_environment()
                values["FACAI_INTEGRATIONS_INTERNAL_BASE_URL"] = internal_origin
                values["FACAI_INTEGRATIONS_PUBLIC_BASE_URL"] = public_origin
                ambiguous = load_integration_settings(values)
                self.assertFalse(ambiguous.credential_ready)
                self.assertIn(
                    "FACAI_INTEGRATIONS_PUBLIC_BASE_URL",
                    ambiguous.errors,
                )

    def test_equivalent_ipv6_spellings_are_the_same_production_hostname(self):
        values = _valid_environment()
        values["FACAI_INTEGRATIONS_INTERNAL_BASE_URL"] = "https://[2001:db8::1]:8443"
        values["FACAI_INTEGRATIONS_PUBLIC_BASE_URL"] = (
            "https://[2001:0db8:0000:0000:0000:0000:0000:0001]"
        )

        settings = load_integration_settings(values)

        self.assertFalse(settings.credential_ready)
        self.assertEqual(settings.errors, ("FACAI_INTEGRATIONS_PUBLIC_BASE_URL",))

    def test_archive_path_is_absolute_and_validation_never_creates_it(self):
        values = _valid_environment()
        values["FACAI_INTEGRATION_ARCHIVE_DIR"] = "relative/archive"
        settings = load_integration_settings(values)
        self.assertFalse(settings.credential_ready)
        self.assertIsNone(settings.archive_dir)
        self.assertIn("FACAI_INTEGRATION_ARCHIVE_DIR", settings.errors)

        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "not-created" / "archive"
            values = _valid_environment(archive_dir=missing)
            settings = load_integration_settings(values)
            self.assertTrue(settings.credential_ready, settings.errors)
            self.assertEqual(settings.archive_dir, missing.resolve())
            self.assertFalse(missing.exists())

            existing_file = Path(temp_dir) / "not-a-directory"
            existing_file.write_text("test", encoding="utf-8")
            values = _valid_environment(archive_dir=existing_file)
            settings = load_integration_settings(values)
            self.assertFalse(settings.credential_ready)
            self.assertIsNone(settings.archive_dir)
            self.assertIn("FACAI_INTEGRATION_ARCHIVE_DIR", settings.errors)

    def test_archive_filesystem_errors_fail_closed_without_escaping_loader(self):
        values = _valid_environment()
        sentinel = "test-archive-path-value-must-not-leak"

        def assert_failed_closed() -> None:
            settings = load_integration_settings(values)
            self.assertIsNone(settings.archive_dir)
            self.assertFalse(settings.credential_ready)
            self.assertEqual(settings.errors, ("FACAI_INTEGRATION_ARCHIVE_DIR",))
            self.assertNotIn(sentinel, repr(settings.errors))

        with patch.object(Path, "resolve", side_effect=OSError(sentinel)):
            assert_failed_closed()
        with patch.object(Path, "exists", side_effect=OSError(sentinel)):
            assert_failed_closed()
        with (
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "is_dir", side_effect=OSError(sentinel)),
        ):
            assert_failed_closed()

    def test_trusted_proxy_cidrs_require_strict_canonical_non_catchall_networks(self):
        invalid_values = (
            "proxy.example.test/24",
            "10.20.0.1/16",
            "10.20.0.0/255.255.0.0",
            "10.20.0.1",
            "2001:0DB8::/32",
            "0.0.0.0/0",
            "::/0",
            "10.20.0.0/16,not-a-cidr",
        )
        for cidrs in invalid_values:
            with self.subTest(cidrs=cidrs):
                values = _valid_environment()
                values["FACAI_INTEGRATIONS_TRUSTED_PROXY_CIDRS"] = cidrs
                settings = load_integration_settings(values)
                self.assertFalse(settings.credential_ready)
                self.assertEqual(settings.trusted_proxy_networks, ())
                self.assertIn("FACAI_INTEGRATIONS_TRUSTED_PROXY_CIDRS", settings.errors)

    def test_credential_readiness_requires_postgresql_database_url(self):
        for database_url in (
            "sqlite:///./data/script_agent.db",
            "mysql://facai@db.example/facai",
            "not-a-url",
        ):
            with self.subTest(database_url=database_url):
                values = _valid_environment()
                values["DATABASE_URL"] = database_url
                settings = load_integration_settings(values)
                self.assertFalse(settings.credential_ready)
                self.assertIn("DATABASE_URL", settings.errors)

    def test_database_url_requires_explicit_psycopg_host_and_database_without_leaks(self):
        password_sentinel = "test-database-password-must-not-leak"
        query_sentinel = "test-database-query-must-not-leak"
        invalid_urls = (
            (
                "postgresql+bogus://facai:"
                f"{password_sentinel}@db.example/facai?application_name={query_sentinel}"
            ),
            f"postgresql://facai:{password_sentinel}@db.example/facai",
            "postgresql+psycopg://",
            "postgresql+psycopg:///facai",
            "postgresql+psycopg://facai@db.example",
        )
        for database_url in invalid_urls:
            with self.subTest(database_url=database_url.split("@")[-1]):
                values = _valid_environment()
                values["DATABASE_URL"] = database_url
                settings = load_integration_settings(values)

                self.assertFalse(settings.credential_ready)
                self.assertEqual(settings.errors, ("DATABASE_URL",))
                rendered_errors = repr(settings.errors)
                self.assertNotIn(password_sentinel, rendered_errors)
                self.assertNotIn(query_sentinel, rendered_errors)

    def test_worker_concurrency_uses_safe_default_for_missing_value_and_rejects_invalid(self):
        values = _valid_environment()
        values.pop("FACAI_INTEGRATION_WORKER_CONCURRENCY")
        self.assertEqual(load_integration_settings(values).worker_concurrency, 4)

        for value in ("0", "-1", "not-an-int"):
            with self.subTest(value=value):
                values = _valid_environment()
                values["FACAI_INTEGRATION_WORKER_CONCURRENCY"] = value
                settings = load_integration_settings(values)
                self.assertFalse(settings.credential_ready)
                self.assertEqual(settings.worker_concurrency, 4)
                self.assertIn("FACAI_INTEGRATION_WORKER_CONCURRENCY", settings.errors)

    def test_config_exports_non_fail_fast_settings_loader(self):
        settings = config.load_integration_settings({})
        self.assertFalse(settings.credential_ready)


if __name__ == "__main__":
    unittest.main()
