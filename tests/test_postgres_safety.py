import io
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

from integrations.db_safety import assert_disposable_postgres
from scripts.assert_disposable_postgres import main as assert_postgres_main


SAFE_DATABASE = "facai_ecommerce_test"
SAFE_URL = (
    "postgresql+psycopg://facai_test@127.0.0.1:55432/"
    f"{SAFE_DATABASE}"
)


def _verification_engine(database_name: str) -> tuple[MagicMock, MagicMock]:
    engine = MagicMock()
    connection = engine.connect.return_value.__enter__.return_value
    connection.execute.return_value.scalar_one.return_value = database_name
    return engine, connection


class DisposablePostgresSafetyTests(unittest.TestCase):
    def _assert_rejected_before_connect(
        self,
        *,
        url: str | None = SAFE_URL,
        acknowledgement: str | None = SAFE_DATABASE,
        extra_environment: dict[str, str] | None = None,
    ) -> str:
        environment: dict[str, str] = {}
        if url is not None:
            environment["TARGET_URL"] = url
        if acknowledgement is not None:
            environment["TARGET_ACK"] = acknowledgement
        environment.update(extra_environment or {})

        with patch.dict(os.environ, environment, clear=True), patch(
            "integrations.db_safety.create_engine"
        ) as create_engine:
            with self.assertRaises(RuntimeError) as raised:
                assert_disposable_postgres(
                    url_env="TARGET_URL",
                    acknowledgement_env="TARGET_ACK",
                )

        create_engine.assert_not_called()
        return str(raised.exception)

    def test_missing_url_or_acknowledgement_fails_before_connect(self):
        for url, acknowledgement in (
            (None, SAFE_DATABASE),
            ("", SAFE_DATABASE),
            (SAFE_URL, None),
            (SAFE_URL, ""),
            (SAFE_URL, "wrong_test"),
        ):
            with self.subTest(url_present=bool(url), acknowledgement=acknowledgement):
                self._assert_rejected_before_connect(
                    url=url,
                    acknowledgement=acknowledgement,
                )

    def test_non_psycopg_or_non_loopback_targets_fail_before_connect(self):
        unsafe_urls = (
            "sqlite:///facai_ecommerce_test",
            "postgresql://facai_test@127.0.0.1:55432/facai_ecommerce_test",
            "postgresql+psycopg2://facai_test@127.0.0.1:55432/facai_ecommerce_test",
            "postgresql+psycopg://facai_test@db.example:55432/facai_ecommerce_test",
            "postgresql+psycopg://facai_test@localhost:55432/facai_ecommerce_test",
            "postgresql+psycopg://facai_test@[0:0:0:0:0:0:0:1]:55432/facai_ecommerce_test",
            "postgresql+psycopg://facai_test@[0000:0000:0000:0000:0000:0000:0000:0001]:55432/facai_ecommerce_test",
            "postgresql+psycopg://facai_test@[::01]:55432/facai_ecommerce_test",
            "postgresql+psycopg://facai_test@127.0.0.2:55432/facai_ecommerce_test",
            "postgresql+psycopg://facai_test@127.0.0.1/facai_ecommerce_test",
            "postgresql+psycopg://127.0.0.1:55432/facai_ecommerce_test",
        )
        for url in unsafe_urls:
            with self.subTest(url=url.split(":", 1)[0]):
                self._assert_rejected_before_connect(url=url)

    def test_database_suffix_must_be_explicitly_disposable(self):
        for database_name in (
            "facai_ecommerce",
            "facai_ecommerce_prod",
            "test",
            "ci",
        ):
            with self.subTest(database_name=database_name):
                self._assert_rejected_before_connect(
                    url=(
                        "postgresql+psycopg://facai_test@127.0.0.1:55432/"
                        f"{database_name}"
                    ),
                    acknowledgement=database_name,
                )

    def test_encoded_database_delimiters_fail_before_connect(self):
        encoded_database_names = (
            (
                "facai%3Fhost%3Ddb.example%26dbname%3Dfacai_test",
                "facai?host=db.example&dbname=facai_test",
            ),
            ("facai%23fragment_test", "facai#fragment_test"),
            ("facai%26host%3Ddb.example_test", "facai&host=db.example_test"),
            ("facai%3Ddbname_test", "facai=dbname_test"),
        )
        for encoded_name, decoded_name in encoded_database_names:
            with self.subTest(decoded_name=decoded_name):
                self._assert_rejected_before_connect(
                    url=(
                        "postgresql+psycopg://facai_test@127.0.0.1:55432/"
                        f"{encoded_name}"
                    ),
                    acknowledgement=decoded_name,
                )

    def test_application_database_equality_fails_on_normalized_target(self):
        message = self._assert_rejected_before_connect(
            url=(
                "postgresql+psycopg://facai_test:target-secret@127.0.0.1:55432/"
                "facai%5Fecommerce%5Ftest"
            ),
            extra_environment={
                "DATABASE_URL": (
                    "postgresql+psycopg://application:production-secret@127.0.0.1:55432/"
                    "facai_ecommerce_test"
                )
            },
        )

        self.assertNotIn("target-secret", message)
        self.assertNotIn("production-secret", message)
        self.assertNotIn("postgresql", message)

    def test_migration_test_database_equality_fails_on_normalized_target(self):
        self._assert_rejected_before_connect(
            extra_environment={
                "FACAI_MIGRATION_TEST_DATABASE_URL": (
                    "postgresql+psycopg://another_user@127.0.0.1:55432/"
                    "facai%5Fecommerce%5Ftest"
                )
            }
        )

    def test_protected_loopback_aliases_match_literal_target_before_connect(self):
        protected_hosts = (
            "localhost.",
            "localhost",
            "[0:0:0:0:0:0:0:1]",
            "[::1]",
            "127.0.0.1",
        )
        for environment_name in (
            "DATABASE_URL",
            "FACAI_MIGRATION_TEST_DATABASE_URL",
        ):
            for protected_host in protected_hosts:
                with self.subTest(
                    environment=environment_name,
                    protected_host=protected_host,
                ):
                    self._assert_rejected_before_connect(
                        extra_environment={
                            environment_name: (
                                "postgresql+psycopg://protected_user@"
                                f"{protected_host}:55432/{SAFE_DATABASE}"
                            )
                        }
                    )

    def test_query_override_and_fragment_bypasses_fail_before_connect(self):
        unsafe_suffixes = (
            "?host=db.example",
            "?host=%2Ftmp",
            "?port=5432",
            "?dbname=facai_migration_ci",
            "?user=admin",
            "?password=secret",
            "?options=-csearch_path%3Dpublic",
            "?sslmode=require",
            "?sslmode=disable&sslmode=disable",
            "?sslmode=disable&host=db.example",
            "#",
            "#fragment",
            "?sslmode=disable#",
            "?sslmode=disable#fragment",
        )
        for suffix in unsafe_suffixes:
            with self.subTest(suffix=suffix):
                message = self._assert_rejected_before_connect(url=f"{SAFE_URL}{suffix}")
                self.assertNotIn("db.example", message)
                self.assertNotIn("secret", message)

    def test_exact_sslmode_allowlist_is_accepted(self):
        url = f"{SAFE_URL}?sslmode=disable"
        engine, connection = _verification_engine(SAFE_DATABASE)
        with patch.dict(
            os.environ,
            {"TARGET_URL": url, "TARGET_ACK": SAFE_DATABASE},
            clear=True,
        ), patch(
            "integrations.db_safety.create_engine",
            return_value=engine,
        ) as create_engine:
            result = assert_disposable_postgres(
                url_env="TARGET_URL",
                acknowledgement_env="TARGET_ACK",
            )

        self.assertEqual(result, url)
        create_engine.assert_called_once()
        self.assertEqual(create_engine.call_args.args[0], url)
        self.assertEqual(
            str(connection.execute.call_args.args[0]),
            "SELECT current_database()",
        )
        engine.dispose.assert_called_once_with()

    def test_literal_ipv6_loopback_is_accepted_without_live_connection(self):
        url = (
            "postgresql+psycopg://facai_test@[::1]:55432/"
            f"{SAFE_DATABASE}"
        )
        engine, _ = _verification_engine(SAFE_DATABASE)
        with patch.dict(
            os.environ,
            {"TARGET_URL": url, "TARGET_ACK": SAFE_DATABASE},
            clear=True,
        ), patch(
            "integrations.db_safety.create_engine",
            return_value=engine,
        ) as create_engine:
            result = assert_disposable_postgres(
                url_env="TARGET_URL",
                acknowledgement_env="TARGET_ACK",
            )

        self.assertEqual(result, url)
        self.assertEqual(create_engine.call_args.args[0], url)
        engine.dispose.assert_called_once_with()

    def test_acknowledgement_compares_to_decoded_database_name(self):
        encoded_url = (
            "postgresql+psycopg://facai_test@127.0.0.1:55432/"
            "facai%5Fecommerce%5Ftest"
        )
        engine, _ = _verification_engine(SAFE_DATABASE)
        with patch.dict(
            os.environ,
            {"TARGET_URL": encoded_url, "TARGET_ACK": SAFE_DATABASE},
            clear=True,
        ), patch(
            "integrations.db_safety.create_engine",
            return_value=engine,
        ) as create_engine:
            result = assert_disposable_postgres(
                url_env="TARGET_URL",
                acknowledgement_env="TARGET_ACK",
            )

        self.assertEqual(result, SAFE_URL)
        self.assertEqual(create_engine.call_args.args[0], SAFE_URL)

    def test_connected_database_must_match_acknowledgement_exactly(self):
        engine, _ = _verification_engine("facai_other_test")
        with patch.dict(
            os.environ,
            {"TARGET_URL": SAFE_URL, "TARGET_ACK": SAFE_DATABASE},
            clear=True,
        ), patch("integrations.db_safety.create_engine", return_value=engine):
            with self.assertRaisesRegex(RuntimeError, "current database"):
                assert_disposable_postgres(
                    url_env="TARGET_URL",
                    acknowledgement_env="TARGET_ACK",
                )

        engine.dispose.assert_called_once_with()

    def test_connection_failure_does_not_expose_credentials_or_url(self):
        credential_url = (
            "postgresql+psycopg://facai_test:do-not-print@127.0.0.1:55432/"
            f"{SAFE_DATABASE}"
        )
        engine = MagicMock()
        engine.connect.side_effect = RuntimeError(credential_url)
        with patch.dict(
            os.environ,
            {"TARGET_URL": credential_url, "TARGET_ACK": SAFE_DATABASE},
            clear=True,
        ), patch("integrations.db_safety.create_engine", return_value=engine):
            with self.assertRaises(RuntimeError) as raised:
                assert_disposable_postgres(
                    url_env="TARGET_URL",
                    acknowledgement_env="TARGET_ACK",
                )

        message = str(raised.exception)
        self.assertNotIn("do-not-print", message)
        self.assertNotIn(credential_url, message)
        self.assertNotIn("postgresql", message)
        engine.dispose.assert_called_once_with()

    def test_disposal_failure_does_not_expose_credentials_or_url(self):
        credential_url = (
            "postgresql+psycopg://facai_test:do-not-print@127.0.0.1:55432/"
            f"{SAFE_DATABASE}"
        )
        engine, _ = _verification_engine(SAFE_DATABASE)
        engine.dispose.side_effect = RuntimeError(credential_url)
        with patch.dict(
            os.environ,
            {"TARGET_URL": credential_url, "TARGET_ACK": SAFE_DATABASE},
            clear=True,
        ), patch("integrations.db_safety.create_engine", return_value=engine):
            with self.assertRaises(RuntimeError) as raised:
                assert_disposable_postgres(
                    url_env="TARGET_URL",
                    acknowledgement_env="TARGET_ACK",
                )

        message = str(raised.exception)
        self.assertNotIn("do-not-print", message)
        self.assertNotIn(credential_url, message)
        self.assertNotIn("postgresql", message)


class DisposablePostgresCliTests(unittest.TestCase):
    def test_cli_prints_only_safe_host_database_and_boolean(self):
        credential_url = (
            "postgresql+psycopg://facai_test:do-not-print@127.0.0.1:55432/"
            f"{SAFE_DATABASE}"
        )
        stdout = io.StringIO()
        with patch(
            "scripts.assert_disposable_postgres.assert_disposable_postgres",
            return_value=credential_url,
        ), redirect_stdout(stdout):
            result = assert_postgres_main(
                ["--env", "TARGET_URL", "--ack-env", "TARGET_ACK"]
            )

        self.assertEqual(result, 0)
        self.assertEqual(
            stdout.getvalue(),
            "host=127.0.0.1 database=facai_ecommerce_test safe=true\n",
        )
        self.assertNotIn("facai_test", stdout.getvalue())
        self.assertNotIn("do-not-print", stdout.getvalue())
        self.assertNotIn("postgresql", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
