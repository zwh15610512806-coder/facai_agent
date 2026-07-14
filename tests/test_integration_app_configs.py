import base64
import json
import logging
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from io import StringIO
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import event, inspect, select
from sqlalchemy.exc import StatementError
from sqlalchemy.orm import Session as SqlAlchemySession
from sqlalchemy.orm import sessionmaker

from database import Base, create_database_engine, get_db
from integrations.admin_auth import (
    INTEGRATION_ADMIN_COOKIE,
    hash_admin_password,
    issue_admin_session,
)
from integrations.app_configs import upsert_provider_app_config
from integrations.audit import write_security_audit
from integrations.crypto import CredentialPurpose, decrypt_credential
from integrations.db_safety import assert_disposable_postgres
from integrations.schemas import AppConfigUpdate, AppConfigView
from integrations.settings import (
    ADMIN_PASSWORD_HASH_ENV,
    ARCHIVE_DIR_ENV,
    DATABASE_URL_ENV,
    INTERNAL_BASE_URL_ENV,
    MASTER_KEY_ENV,
    PUBLIC_BASE_URL_ENV,
    SESSION_SECRET_ENV,
    TRUSTED_PROXY_CIDRS_ENV,
    WORKER_CONCURRENCY_ENV,
    load_integration_settings,
)
from integrations.types import Provider
from integration_models import IntegrationAppConfig, IntegrationSecurityAudit
from main import app


SESSION_SECRET = b"task-eight-session-secret-material" * 2
MASTER_KEY = b"m" * 32
APP_CONFIG_TABLES = (
    IntegrationSecurityAudit.__table__,
    IntegrationAppConfig.__table__,
)


def _base64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


class AppConfigSchemaContractTests(unittest.TestCase):
    def test_update_body_is_strict_and_secret_clear_is_mutually_exclusive(self):
        secret = "task-eight-plaintext-secret"

        with self.assertRaises(ValidationError):
            AppConfigUpdate.model_validate(
                {"app_id": "merchant-app", "unexpected": "rejected"}
            )
        with self.assertRaises(ValidationError) as raised:
            AppConfigUpdate.model_validate(
                {
                    "app_id": "merchant-app",
                    "app_secret": secret,
                    "clear_secret": True,
                }
            )
        for invalid_app_id in ("", "x" * 201):
            with self.subTest(length=len(invalid_app_id)):
                with self.assertRaises(ValidationError):
                    AppConfigUpdate.model_validate({"app_id": invalid_app_id})
        for invalid_secret in ("", "s" * 4097):
            with self.subTest(secret_length=len(invalid_secret)):
                with self.assertRaises(ValidationError):
                    AppConfigUpdate.model_validate(
                        {
                            "app_id": "merchant-app",
                            "app_secret": invalid_secret,
                        }
                    )

        self.assertNotIn(secret, str(raised.exception))

    def test_secretstr_masks_plaintext_in_repr(self):
        secret = "task-eight-repr-secret"

        update = AppConfigUpdate(app_id="merchant-app", app_secret=secret)

        self.assertNotIn(secret, repr(update))
        self.assertNotIn(secret, repr(update.model_dump()))
        self.assertNotIn(secret, json.dumps(update.model_dump(mode="json")))
        self.assertNotIn(secret, update.model_dump_json())

    def test_clear_secret_accepts_only_actual_json_booleans(self):
        invalid_values = (
            "true",
            "false",
            "clear-string-sentinel",
            1,
            0,
            1.0,
            0.0,
            None,
            ["clear-list-sentinel"],
        )

        for value in invalid_values:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                AppConfigUpdate.model_validate(
                    {"app_id": "merchant-app", "clear_secret": value}
                )
        self.assertTrue(
            AppConfigUpdate(
                app_id="merchant-app",
                clear_secret=True,
            ).clear_secret
        )
        self.assertFalse(
            AppConfigUpdate(
                app_id="merchant-app",
                clear_secret=False,
            ).clear_secret
        )


class IntegrationAppConfigEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = assert_disposable_postgres(
            url_env="FACAI_TEST_DATABASE_URL",
            acknowledgement_env="FACAI_DESTRUCTIVE_TEST_DATABASE_ACK",
        )
        cls.engine = create_database_engine(cls.database_url)
        cls.Session = sessionmaker(bind=cls.engine, expire_on_commit=False)
        cls.password_hash = hash_admin_password(
            "task-eight-admin-password",
            salt=b"8" * 16,
        )
        cls.environment = {
            ADMIN_PASSWORD_HASH_ENV: cls.password_hash,
            SESSION_SECRET_ENV: _base64url(SESSION_SECRET),
            MASTER_KEY_ENV: _base64url(MASTER_KEY),
            INTERNAL_BASE_URL_ENV: "https://internal.integration.test",
            PUBLIC_BASE_URL_ENV: "https://public.integration.test",
            ARCHIVE_DIR_ENV: str(
                (Path(__file__).resolve().parents[1] / "data" / "task8-archive")
                .resolve()
            ),
            TRUSTED_PROXY_CIDRS_ENV: "",
            WORKER_CONCURRENCY_ENV: "1",
            DATABASE_URL_ENV: cls.database_url,
        }
        try:
            Base.metadata.drop_all(
                cls.engine,
                tables=APP_CONFIG_TABLES,
                checkfirst=True,
            )
            Base.metadata.create_all(
                cls.engine,
                tables=APP_CONFIG_TABLES,
                checkfirst=False,
            )
        except Exception:
            Base.metadata.drop_all(
                cls.engine,
                tables=APP_CONFIG_TABLES,
                checkfirst=True,
            )
            cls.engine.dispose()
            raise

    @classmethod
    def tearDownClass(cls):
        try:
            Base.metadata.drop_all(
                cls.engine,
                tables=APP_CONFIG_TABLES,
                checkfirst=True,
            )
            remaining = set(inspect(cls.engine).get_table_names()) & {
                table.name for table in APP_CONFIG_TABLES
            }
            if remaining:
                raise AssertionError(
                    f"Integration app-config cleanup left tables behind: "
                    f"{sorted(remaining)}"
                )
        finally:
            cls.engine.dispose()

    def setUp(self):
        Base.metadata.drop_all(
            self.engine,
            tables=APP_CONFIG_TABLES,
            checkfirst=True,
        )
        Base.metadata.create_all(
            self.engine,
            tables=APP_CONFIG_TABLES,
            checkfirst=False,
        )
        self.environment_patch = patch.dict(
            os.environ,
            self.environment,
            clear=False,
        )
        self.environment_patch.start()

        def override_db():
            session = self.Session()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_db
        self.session_cookie = issue_admin_session(session_secret=SESSION_SECRET)

    def tearDown(self):
        app.dependency_overrides.pop(get_db, None)
        self.environment_patch.stop()

    @contextmanager
    def _client(self, *, authenticated: bool):
        client = TestClient(
            app,
            base_url="https://127.0.0.1:8001",
            client=("198.51.100.88", 50000),
            raise_server_exceptions=False,
        )
        if authenticated:
            client.cookies.set(INTEGRATION_ADMIN_COOKIE, self.session_cookie)
        try:
            yield client
        finally:
            client.close()

    @contextmanager
    def _sqlalchemy_logs(self):
        logger = logging.getLogger("sqlalchemy.engine")
        previous_level = logger.level
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        try:
            yield stream
        finally:
            logger.removeHandler(handler)
            logger.setLevel(previous_level)

    def _put(self, client: TestClient, provider: str, payload: dict):
        return client.put(
            f"/api/integrations/providers/{provider}/app-config",
            json=payload,
        )

    def test_provider_endpoints_require_admin_session_with_json_401(self):
        secret = "unauthenticated-secret-must-not-echo"
        with self._client(authenticated=False) as client:
            listed = client.get("/api/integrations/providers")
            updated = self._put(
                client,
                Provider.QIANCHUAN.value,
                {"app_id": "merchant-app", "app_secret": secret},
            )

        for response in (listed, updated):
            self.assertEqual(response.status_code, 401, response.text)
            self.assertTrue(
                response.headers["content-type"].startswith("application/json")
            )
            self.assertEqual(
                response.json(),
                {"detail": "Integration administrator session required"},
            )
            self.assertNotIn(secret, response.text)

    def test_provider_list_separates_documented_configured_and_live_stages(self):
        with self._client(authenticated=True) as client:
            before = client.get("/api/integrations/providers")
            configured = self._put(
                client,
                Provider.QIANCHUAN.value,
                {
                    "app_id": "qianchuan-app",
                    "app_secret": "configured-secret-4433",
                },
            )
            after = client.get("/api/integrations/providers")

        self.assertEqual(before.status_code, 200, before.text)
        self.assertEqual(configured.status_code, 200, configured.text)
        self.assertEqual(after.status_code, 200, after.text)
        before_items = before.json()["providers"]
        after_items = after.json()["providers"]
        self.assertEqual(
            [item["provider"] for item in before_items],
            [provider.value for provider in Provider],
        )
        for item in before_items:
            self.assertEqual(
                set(item),
                {
                    "provider",
                    "documented",
                    "configured",
                    "live_verified",
                    "live_status",
                    "app_config",
                },
            )
            self.assertTrue(item["documented"])
            self.assertFalse(item["configured"])
            self.assertFalse(item["live_verified"])
            self.assertEqual(item["live_status"], "pending")
            self.assertEqual(item["app_config"]["status"], "not_configured")
        qianchuan = after_items[0]
        self.assertTrue(qianchuan["documented"])
        self.assertTrue(qianchuan["configured"])
        self.assertFalse(qianchuan["live_verified"])
        self.assertEqual(qianchuan["live_status"], "pending")
        for item in after_items[1:]:
            self.assertFalse(item["configured"])
            self.assertFalse(item["live_verified"])
            self.assertEqual(item["live_status"], "pending")

    def test_put_encrypts_app_secret_and_returns_only_masked_safe_fields(self):
        plaintext = "task-eight-super-secret-7890"
        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        logging.getLogger().addHandler(handler)
        try:
            with self._client(authenticated=True) as client:
                response = self._put(
                    client,
                    Provider.DOUDIAN.value,
                    {"app_id": "doudian-app", "app_secret": plaintext},
                )
        finally:
            logging.getLogger().removeHandler(handler)

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(
            set(body),
            {
                "provider",
                "app_id",
                "secret_configured",
                "secret_mask",
                "status",
                "updated_at",
            },
        )
        self.assertEqual(body["provider"], Provider.DOUDIAN.value)
        self.assertEqual(body["app_id"], "doudian-app")
        self.assertTrue(body["secret_configured"])
        self.assertEqual(body["secret_mask"], "****7890")
        self.assertEqual(body["status"], "configured")
        self.assertIsNotNone(body["updated_at"])

        with self.Session() as session:
            row = session.execute(select(IntegrationAppConfig)).scalar_one()
            audit = session.execute(select(IntegrationSecurityAudit)).scalar_one()
        ciphertext = row.app_secret_ciphertext
        self.assertIsNotNone(ciphertext)
        self.assertNotEqual(ciphertext, plaintext)
        self.assertEqual(row.app_secret_tail, "7890")
        self.assertEqual(
            decrypt_credential(
                ciphertext,
                master_key=MASTER_KEY,
                purpose=CredentialPurpose.APP_SECRET,
            ),
            plaintext,
        )
        self.assertEqual(audit.event_type, "app_config_changed")
        self.assertEqual(audit.summary_code, "app_config_created")
        self.assertEqual(audit.provider, Provider.DOUDIAN)
        self.assertEqual(audit.target_type, "app_config")
        self.assertEqual(audit.target_id, Provider.DOUDIAN.value)
        self.assertEqual(audit.details, {})
        self.assertRegex(audit.session_digest or "", r"^[0-9a-f]{64}$")
        self.assertNotEqual(audit.session_digest, self.session_cookie)
        safe_result = AppConfigView.model_validate(body)
        audit_values = {
            column.name: getattr(audit, column.name)
            for column in IntegrationSecurityAudit.__table__.columns
        }
        rendered = "\n".join(
            (
                response.text,
                repr(response.headers),
                log_stream.getvalue(),
                repr(body),
                repr(safe_result),
                repr(row),
                repr(audit),
                json.dumps(audit_values, default=str),
                repr(
                    AppConfigUpdate(
                        app_id="doudian-app",
                        app_secret=plaintext,
                    )
                ),
            )
        )
        self.assertNotIn(plaintext, rendered)
        self.assertNotIn(ciphertext, rendered)
        self.assertNotIn(self.session_cookie, rendered)

    def test_sqlalchemy_logging_never_renders_encrypted_bound_parameters(self):
        plaintext = "sql-log-plaintext-sentinel-7788"
        ciphertext = "sql-log-ciphertext-sentinel-envelope"

        with (
            self._sqlalchemy_logs() as log_stream,
            patch(
                "integrations.app_configs.encrypt_credential",
                return_value=ciphertext,
            ),
            self._client(authenticated=True) as client,
        ):
            response = self._put(
                client,
                Provider.QIANCHUAN.value,
                {"app_id": "sql-log-app", "app_secret": plaintext},
            )

        self.assertEqual(response.status_code, 200, response.text)
        rendered = log_stream.getvalue()
        self.assertNotIn(plaintext, rendered)
        self.assertNotIn(ciphertext, rendered)

    def test_omitted_and_explicit_null_secret_preserve_ciphertext(self):
        with self._client(authenticated=True) as client:
            created = self._put(
                client,
                Provider.TAOBAO.value,
                {
                    "app_id": "taobao-one",
                    "app_secret": "preserved-secret-2468",
                },
            )
            with self.Session() as session:
                original = session.execute(
                    select(IntegrationAppConfig)
                ).scalar_one()
                original_ciphertext = original.app_secret_ciphertext
            omitted = self._put(
                client,
                Provider.TAOBAO.value,
                {"app_id": "taobao-two"},
            )
            explicit_null = self._put(
                client,
                Provider.TAOBAO.value,
                {"app_id": "taobao-three", "app_secret": None},
            )

        self.assertEqual(created.status_code, 200, created.text)
        self.assertEqual(omitted.status_code, 200, omitted.text)
        self.assertEqual(explicit_null.status_code, 200, explicit_null.text)
        self.assertEqual(omitted.json()["secret_mask"], "****2468")
        self.assertEqual(explicit_null.json()["secret_mask"], "****2468")
        with self.Session() as session:
            current = session.execute(select(IntegrationAppConfig)).scalar_one()
            summaries = list(
                session.execute(
                    select(IntegrationSecurityAudit.summary_code).order_by(
                        IntegrationSecurityAudit.id
                    )
                ).scalars()
            )
        self.assertEqual(current.app_id, "taobao-three")
        self.assertEqual(current.app_secret_ciphertext, original_ciphertext)
        self.assertEqual(current.app_secret_tail, "2468")
        self.assertEqual(
            summaries,
            ["app_config_created", "app_config_updated", "app_config_updated"],
        )

    def test_clear_secret_removes_ciphertext_tail_and_marks_unconfigured(self):
        with self._client(authenticated=True) as client:
            created = self._put(
                client,
                Provider.PDD.value,
                {
                    "app_id": "pdd-app",
                    "app_secret": "clear-this-secret-1357",
                },
            )
            cleared = self._put(
                client,
                Provider.PDD.value,
                {"app_id": "pdd-app", "clear_secret": True},
            )
            listed = client.get("/api/integrations/providers")

        self.assertEqual(created.status_code, 200, created.text)
        self.assertEqual(cleared.status_code, 200, cleared.text)
        self.assertFalse(cleared.json()["secret_configured"])
        self.assertIsNone(cleared.json()["secret_mask"])
        self.assertEqual(cleared.json()["status"], "setup_required")
        pdd = listed.json()["providers"][-1]
        self.assertFalse(pdd["configured"])
        self.assertFalse(pdd["live_verified"])
        self.assertEqual(pdd["live_status"], "pending")
        with self.Session() as session:
            row = session.execute(select(IntegrationAppConfig)).scalar_one()
            summaries = list(
                session.execute(
                    select(IntegrationSecurityAudit.summary_code).order_by(
                        IntegrationSecurityAudit.id
                    )
                ).scalars()
            )
        self.assertIsNone(row.app_secret_ciphertext)
        self.assertIsNone(row.app_secret_tail)
        self.assertEqual(
            summaries,
            ["app_config_created", "app_secret_cleared"],
        )

    def test_new_app_id_without_secret_is_setup_required_not_configured(self):
        with self._client(authenticated=True) as client:
            created = self._put(
                client,
                Provider.QIANCHUAN.value,
                {"app_id": "app-id-only"},
            )
            cleared_without_secret = self._put(
                client,
                Provider.QIANCHUAN.value,
                {"app_id": "app-id-only", "clear_secret": True},
            )
            listed = client.get("/api/integrations/providers")

        self.assertEqual(created.status_code, 200, created.text)
        self.assertFalse(created.json()["secret_configured"])
        self.assertIsNone(created.json()["secret_mask"])
        self.assertEqual(created.json()["status"], "setup_required")
        self.assertEqual(cleared_without_secret.status_code, 200)
        qianchuan = listed.json()["providers"][0]
        self.assertFalse(qianchuan["configured"])
        self.assertFalse(qianchuan["live_verified"])
        self.assertEqual(qianchuan["live_status"], "pending")
        with self.Session() as session:
            summaries = list(
                session.execute(
                    select(IntegrationSecurityAudit.summary_code).order_by(
                        IntegrationSecurityAudit.id
                    )
                ).scalars()
            )
        self.assertEqual(
            summaries,
            ["app_config_created", "app_config_updated"],
        )

    def test_clear_on_first_write_audits_configuration_creation(self):
        with self._client(authenticated=True) as client:
            response = self._put(
                client,
                Provider.QIANCHUAN.value,
                {"app_id": "new-clear-app", "clear_secret": True},
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["secret_configured"])
        with self.Session() as session:
            audit = session.execute(select(IntegrationSecurityAudit)).scalar_one()
        self.assertEqual(audit.summary_code, "app_config_created")

    def test_short_and_unicode_secrets_use_the_last_four_characters(self):
        with self._client(authenticated=True) as client:
            short = self._put(
                client,
                Provider.DOUDIAN.value,
                {"app_id": "short-secret-app", "app_secret": "abc"},
            )
            unicode_secret = self._put(
                client,
                Provider.DOUDIAN.value,
                {"app_id": "unicode-secret-app", "app_secret": "甲乙丙丁戊"},
            )

        self.assertEqual(short.status_code, 200, short.text)
        self.assertEqual(short.json()["secret_mask"], "****abc")
        self.assertEqual(unicode_secret.status_code, 200, unicode_secret.text)
        self.assertEqual(unicode_secret.json()["secret_mask"], "****乙丙丁戊")
        with self.Session() as session:
            row = session.execute(select(IntegrationAppConfig)).scalar_one()
        self.assertEqual(row.app_secret_tail, "乙丙丁戊")

    def test_provider_and_body_validation_are_strict_without_secret_echo(self):
        secret = "validation-secret-must-never-echo"
        unknown_value = "unknown-value-must-never-echo"
        with self._client(authenticated=True) as client:
            invalid_provider = self._put(
                client,
                "not-a-provider-secret-sentinel",
                {"app_id": "merchant-app"},
            )
            uppercase_provider = self._put(
                client,
                Provider.QIANCHUAN.value.upper(),
                {"app_id": "merchant-app"},
            )
            unknown = self._put(
                client,
                Provider.QIANCHUAN.value,
                {
                    "app_id": "merchant-app",
                    "app_secret": secret,
                    "unexpected": unknown_value,
                },
            )
            mutually_exclusive = self._put(
                client,
                Provider.QIANCHUAN.value,
                {
                    "app_id": "merchant-app",
                    "app_secret": secret,
                    "clear_secret": True,
                },
            )

        for response in (
            invalid_provider,
            uppercase_provider,
            unknown,
            mutually_exclusive,
        ):
            self.assertEqual(response.status_code, 422, response.text)
            self.assertNotIn(secret, response.text)
            self.assertNotIn(unknown_value, response.text)
            self.assertNotIn("not-a-provider-secret-sentinel", response.text)
        with self.Session() as session:
            self.assertIsNone(
                session.execute(select(IntegrationAppConfig)).scalar_one_or_none()
            )
            audits = session.execute(
                select(IntegrationSecurityAudit).order_by(
                    IntegrationSecurityAudit.id
                )
            ).scalars().all()
        self.assertEqual(len(audits), 4)
        self.assertTrue(
            all(
                audit.event_type == "integration_mutation_rejected"
                and audit.details
                == {
                    "operation": "update_app_config",
                    "reason": "validation_rejected",
                }
                for audit in audits
            )
        )
        self.assertNotIn(
            "not-a-provider-secret-sentinel",
            repr([audit.target_id for audit in audits]),
        )

    def test_non_boolean_clear_secret_is_422_without_any_mutation(self):
        plaintext = "strict-clear-preserved-secret-8642"
        with self._client(authenticated=True) as client:
            created = self._put(
                client,
                Provider.QIANCHUAN.value,
                {"app_id": "strict-clear-app", "app_secret": plaintext},
            )
            self.assertEqual(created.status_code, 200, created.text)
            with self.Session() as session:
                original = session.execute(
                    select(IntegrationAppConfig)
                ).scalar_one()
                original_state = (
                    original.app_id,
                    original.app_secret_ciphertext,
                    original.app_secret_tail,
                    original.status,
                    original.updated_at,
                )
                original_audits = session.execute(
                    select(IntegrationSecurityAudit)
                ).scalars().all()

            invalid_values = (
                "true",
                "false",
                "clear-string-sentinel",
                1,
                0,
                1.0,
                0.0,
                None,
                ["clear-list-sentinel"],
            )
            responses = [
                self._put(
                    client,
                    Provider.QIANCHUAN.value,
                    {
                        "app_id": "strict-clear-app",
                        "clear_secret": value,
                    },
                )
                for value in invalid_values
            ]

        for response in responses:
            self.assertEqual(response.status_code, 422, response.text)
            self.assertNotIn("clear-string-sentinel", response.text)
            self.assertNotIn("clear-list-sentinel", response.text)
            self.assertNotIn(plaintext, response.text)
        with self.Session() as session:
            current = session.execute(select(IntegrationAppConfig)).scalar_one()
            current_state = (
                current.app_id,
                current.app_secret_ciphertext,
                current.app_secret_tail,
                current.status,
                current.updated_at,
            )
            current_audits = session.execute(
                select(IntegrationSecurityAudit)
            ).scalars().all()
        self.assertEqual(current_state, original_state)
        self.assertEqual(
            len(current_audits),
            len(original_audits) + len(invalid_values),
        )
        validation_audits = current_audits[len(original_audits):]
        self.assertTrue(
            all(
                audit.event_type == "integration_mutation_rejected"
                and audit.details
                == {
                    "operation": "update_app_config",
                    "reason": "validation_rejected",
                }
                for audit in validation_audits
            )
        )
        self.assertNotIn(plaintext, repr(validation_audits))

    def test_incomplete_security_configuration_is_503_with_names_only(self):
        invalid_master_value = "invalid-master-value-must-not-echo"
        incomplete_environment = dict(self.environment)
        incomplete_environment[MASTER_KEY_ENV] = invalid_master_value
        incomplete = load_integration_settings(incomplete_environment)
        self.assertFalse(incomplete.credential_ready)
        with (
            self._client(authenticated=True) as client,
            patch(
                "routers.integrations.load_integration_settings",
                return_value=incomplete,
            ),
        ):
            listed = client.get("/api/integrations/providers")
            updated = self._put(
                client,
                Provider.QIANCHUAN.value,
                {
                    "app_id": "merchant-app",
                    "app_secret": "readiness-secret-value",
                },
            )

        expected = {
            "detail": {
                "code": "security_configuration_incomplete",
                "missing_environment_keys": list(incomplete.errors),
            }
        }
        self.assertEqual(listed.status_code, 503, listed.text)
        self.assertEqual(updated.status_code, 503, updated.text)
        self.assertEqual(listed.json(), expected)
        self.assertEqual(updated.json(), expected)
        rendered = listed.text + updated.text
        self.assertNotIn(self.password_hash, rendered)
        self.assertNotIn(_base64url(SESSION_SECRET), rendered)
        self.assertNotIn(_base64url(MASTER_KEY), rendered)
        self.assertNotIn(invalid_master_value, rendered)
        self.assertNotIn("readiness-secret-value", rendered)
        with self.Session() as session:
            self.assertIsNone(
                session.execute(select(IntegrationAppConfig)).scalar_one_or_none()
            )
            self.assertIsNone(
                session.execute(select(IntegrationSecurityAudit)).scalar_one_or_none()
            )

    def test_provider_list_selects_only_safe_columns(self):
        ciphertext = '{"v":1,"ciphertext":"must-not-be-selected"}'
        with self.Session() as session:
            session.add(
                IntegrationAppConfig(
                    provider=Provider.QIANCHUAN,
                    app_id="safe-select-app",
                    app_secret_ciphertext=ciphertext,
                    app_secret_tail="4321",
                    status="configured",
                )
            )
            session.commit()
        statements: list[str] = []

        def capture_statement(conn, cursor, statement, parameters, context, many):
            del conn, cursor, parameters, context, many
            if "integration_app_configs" in statement.lower():
                statements.append(statement.lower())

        event.listen(self.engine, "before_cursor_execute", capture_statement)
        try:
            with self._client(authenticated=True) as client:
                response = client.get("/api/integrations/providers")
        finally:
            event.remove(self.engine, "before_cursor_execute", capture_statement)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(statements)
        self.assertTrue(
            all("app_secret_ciphertext" not in statement for statement in statements),
            statements,
        )
        self.assertNotIn(ciphertext, response.text)
        qianchuan = response.json()["providers"][0]
        self.assertEqual(qianchuan["app_config"]["secret_mask"], "****4321")

    def test_app_config_and_audit_are_one_transaction(self):
        update = AppConfigUpdate(
            app_id="rollback-app",
            app_secret="rollback-secret-9999",
        )
        with self.Session() as session:
            with (
                patch(
                    "integrations.app_configs.write_security_audit",
                    side_effect=RuntimeError("audit failed"),
                ),
                self.assertRaisesRegex(RuntimeError, "audit failed"),
            ):
                upsert_provider_app_config(
                    session,
                    provider=Provider.QIANCHUAN,
                    update=update,
                    master_key=MASTER_KEY,
                    session_digest="a" * 64,
                )
            session.rollback()

        with self.Session() as session:
            self.assertIsNone(
                session.execute(select(IntegrationAppConfig)).scalar_one_or_none()
            )
            self.assertIsNone(
                session.execute(select(IntegrationSecurityAudit)).scalar_one_or_none()
            )

    def test_upsert_database_error_rolls_back_to_stable_generic_json(self):
        plaintext = "upsert-error-plaintext-sentinel-5566"
        ciphertext = "upsert-error-ciphertext-sentinel-envelope"
        failure = StatementError(
            "provider app configuration write failed",
            "UPDATE integration_app_configs",
            {
                "app_secret": plaintext,
                "app_secret_ciphertext": ciphertext,
            },
            RuntimeError("driver write failure"),
            hide_parameters=self.engine.hide_parameters,
        )
        real_upsert = upsert_provider_app_config

        def stage_then_fail(*args, **kwargs):
            real_upsert(*args, **kwargs)
            raise failure

        real_rollback = SqlAlchemySession.rollback
        rollback_calls: list[SqlAlchemySession] = []

        def record_rollback(session):
            rollback_calls.append(session)
            return real_rollback(session)

        with (
            self._sqlalchemy_logs() as log_stream,
            patch(
                "integrations.app_configs.encrypt_credential",
                return_value=ciphertext,
            ),
            patch(
                "routers.integrations.upsert_provider_app_config",
                side_effect=stage_then_fail,
            ),
            patch.object(SqlAlchemySession, "rollback", record_rollback),
            self._client(authenticated=True) as client,
        ):
            response = self._put(
                client,
                Provider.QIANCHUAN.value,
                {"app_id": "upsert-error-app", "app_secret": plaintext},
            )

        rendered = "\n".join(
            (
                response.text,
                repr(response.headers),
                log_stream.getvalue(),
                str(failure),
                repr(failure),
            )
        )
        self.assertNotIn(plaintext, rendered)
        self.assertNotIn(ciphertext, rendered)
        self.assertEqual(response.status_code, 500, response.text)
        self.assertTrue(
            response.headers.get("content-type", "").startswith(
                "application/json"
            )
        )
        self.assertEqual(
            response.json(),
            {"detail": {"code": "app_config_persistence_failed"}},
        )
        self.assertEqual(len(rollback_calls), 1)
        with self.Session() as session:
            self.assertIsNone(
                session.execute(select(IntegrationAppConfig)).scalar_one_or_none()
            )
            self.assertIsNone(
                session.execute(select(IntegrationSecurityAudit)).scalar_one_or_none()
            )

    def test_commit_database_error_rolls_back_staged_config_and_audit(self):
        plaintext = "commit-error-plaintext-sentinel-1122"
        ciphertext = "commit-error-ciphertext-sentinel-envelope"
        failure = StatementError(
            "provider app configuration commit failed",
            "COMMIT",
            {
                "app_secret": plaintext,
                "app_secret_ciphertext": ciphertext,
            },
            RuntimeError("driver commit failure"),
            hide_parameters=self.engine.hide_parameters,
        )
        real_rollback = SqlAlchemySession.rollback
        rollback_calls: list[SqlAlchemySession] = []

        def fail_commit(session):
            session.flush()
            raise failure

        def record_rollback(session):
            rollback_calls.append(session)
            return real_rollback(session)

        with (
            self._sqlalchemy_logs() as log_stream,
            patch(
                "integrations.app_configs.encrypt_credential",
                return_value=ciphertext,
            ),
            patch.object(SqlAlchemySession, "commit", fail_commit),
            patch.object(SqlAlchemySession, "rollback", record_rollback),
            self._client(authenticated=True) as client,
        ):
            response = self._put(
                client,
                Provider.PDD.value,
                {"app_id": "commit-error-app", "app_secret": plaintext},
            )

        rendered = "\n".join(
            (
                response.text,
                repr(response.headers),
                log_stream.getvalue(),
                str(failure),
                repr(failure),
            )
        )
        self.assertNotIn(plaintext, rendered)
        self.assertNotIn(ciphertext, rendered)
        self.assertEqual(response.status_code, 500, response.text)
        self.assertTrue(
            response.headers.get("content-type", "").startswith(
                "application/json"
            )
        )
        self.assertEqual(
            response.json(),
            {"detail": {"code": "app_config_persistence_failed"}},
        )
        self.assertEqual(len(rollback_calls), 1)
        with self.Session() as session:
            self.assertIsNone(
                session.execute(select(IntegrationAppConfig)).scalar_one_or_none()
            )
            self.assertIsNone(
                session.execute(select(IntegrationSecurityAudit)).scalar_one_or_none()
            )

    def test_app_config_audit_allowlist_rejects_cross_event_targets_and_details(self):
        invalid_calls = (
            {
                "event_type": "login_succeeded",
                "outcome": "success",
                "summary_code": "password_verified",
                "provider": Provider.PDD,
                "target_type": "app_config",
                "target_id": Provider.PDD.value,
                "details": {},
            },
            {
                "event_type": "app_config_changed",
                "outcome": "success",
                "summary_code": "app_config_updated",
                "provider": Provider.PDD,
                "target_type": "arbitrary",
                "target_id": Provider.PDD.value,
                "details": {},
            },
            {
                "event_type": "app_config_changed",
                "outcome": "success",
                "summary_code": "app_config_updated",
                "provider": Provider.PDD,
                "target_type": "app_config",
                "target_id": Provider.PDD.value,
                "details": {"secret": "forbidden"},
            },
            {
                "event_type": "app_config_changed",
                "outcome": "success",
                "summary_code": "app_config_updated",
                "provider": Provider.PDD,
                "target_type": "app_config",
                "target_id": Provider.PDD.value,
                "details": {},
            },
        )
        with self.Session() as session:
            for kwargs in invalid_calls:
                with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                    write_security_audit(session, **kwargs)
                self.assertFalse(session.new)

    def test_concurrent_first_writes_create_one_row_and_one_created_audit(self):
        barrier = Barrier(2)
        writes = (
            ("concurrent-app-one", "concurrent-secret-1111", "1" * 64),
            ("concurrent-app-two", "concurrent-secret-2222", "2" * 64),
        )

        def write(values):
            app_id, secret, digest = values
            barrier.wait(timeout=10)
            with self.Session() as session:
                view = upsert_provider_app_config(
                    session,
                    provider=Provider.QIANCHUAN,
                    update=AppConfigUpdate(
                        app_id=app_id,
                        app_secret=secret,
                    ),
                    master_key=MASTER_KEY,
                    session_digest=digest,
                )
                session.commit()
                return view.app_id

        with ThreadPoolExecutor(max_workers=2) as executor:
            returned = list(executor.map(write, writes))

        self.assertCountEqual(
            returned,
            ["concurrent-app-one", "concurrent-app-two"],
        )
        with self.Session() as session:
            rows = list(session.execute(select(IntegrationAppConfig)).scalars())
            audits = list(
                session.execute(
                    select(IntegrationSecurityAudit).order_by(
                        IntegrationSecurityAudit.id
                    )
                ).scalars()
            )
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(audits), 2)
        self.assertCountEqual(
            [audit.summary_code for audit in audits],
            ["app_config_created", "app_config_updated"],
        )
        final_plaintext = decrypt_credential(
            rows[0].app_secret_ciphertext,
            master_key=MASTER_KEY,
            purpose=CredentialPurpose.APP_SECRET,
        )
        expected_by_app = {
            "concurrent-app-one": "concurrent-secret-1111",
            "concurrent-app-two": "concurrent-secret-2222",
        }
        self.assertEqual(final_plaintext, expected_by_app[rows[0].app_id])


if __name__ == "__main__":
    unittest.main()
