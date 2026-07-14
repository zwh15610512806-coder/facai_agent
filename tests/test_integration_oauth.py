import base64
import hashlib
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier
from urllib.parse import parse_qs, urlencode, urlsplit
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import inspect, select
from sqlalchemy.orm import sessionmaker

from database import Base, create_database_engine, get_db
from integration_models import (
    IntegrationAppConfig,
    IntegrationAuthorization,
    IntegrationConnection,
    IntegrationOAuthState,
    IntegrationSecurityAudit,
)
from integrations.admin_auth import (
    INTEGRATION_ADMIN_COOKIE,
    hash_admin_password,
    issue_admin_session,
)
from integrations.connectors.registry import ConnectorRegistry, ConnectorUnavailable
from integrations.connections import (
    ConnectionOwnershipConflict,
    ConnectorOutputInvalid,
    persist_oauth_result,
)
from integrations.crypto import CredentialPurpose, decrypt_credential, encrypt_credential
from integrations.db_safety import assert_disposable_postgres
from integrations.oauth import OAuthStateInvalid, consume_oauth_state, create_oauth_state
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
)
from integrations.types import (
    AccountIdentity,
    ConnectionStatus,
    ConnectionType,
    Provider,
    TokenBundle,
    VerifiedEvent,
    EventIdScope,
)
from main import app


UTC = timezone.utc
SESSION_SECRET = b"task-nine-session-secret-material" * 2
MASTER_KEY = b"o" * 32
OAUTH_TABLES = (
    IntegrationSecurityAudit.__table__,
    IntegrationOAuthState.__table__,
    IntegrationConnection.__table__,
    IntegrationAuthorization.__table__,
    IntegrationAppConfig.__table__,
)


def _base64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


class OAuthStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = assert_disposable_postgres(
            url_env="FACAI_TEST_DATABASE_URL",
            acknowledgement_env="FACAI_DESTRUCTIVE_TEST_DATABASE_ACK",
        )
        cls.engine = create_database_engine(cls.database_url)
        cls.Session = sessionmaker(bind=cls.engine, expire_on_commit=False)
        Base.metadata.drop_all(cls.engine, tables=OAUTH_TABLES, checkfirst=True)
        Base.metadata.create_all(cls.engine, tables=OAUTH_TABLES, checkfirst=False)

    @classmethod
    def tearDownClass(cls):
        try:
            Base.metadata.drop_all(cls.engine, tables=OAUTH_TABLES, checkfirst=True)
            remaining = set(inspect(cls.engine).get_table_names()) & {
                table.name for table in OAUTH_TABLES
            }
            if remaining:
                raise AssertionError(
                    f"OAuth test cleanup left tables behind: {sorted(remaining)}"
                )
        finally:
            cls.engine.dispose()

    def setUp(self):
        Base.metadata.drop_all(self.engine, tables=OAUTH_TABLES, checkfirst=True)
        Base.metadata.create_all(self.engine, tables=OAUTH_TABLES, checkfirst=False)

    def test_state_has_256_bits_and_only_hash_is_stored_then_consumed_once(self):
        now = datetime(2026, 7, 13, 10, 0, tzinfo=UTC)
        with self.Session() as session:
            raw_state = create_oauth_state(
                session,
                provider=Provider.QIANCHUAN,
                session_id="admin-session-id",
                return_path="/app/api-connections/accounts",
                now=now,
            )
            session.commit()
            stored = session.execute(select(IntegrationOAuthState)).scalar_one()

        decoded = base64.urlsafe_b64decode(raw_state + "=" * (-len(raw_state) % 4))
        self.assertGreaterEqual(len(decoded), 32)
        self.assertEqual(stored.state_hash, hashlib.sha256(raw_state.encode()).hexdigest())
        self.assertNotEqual(stored.state_hash, raw_state)
        self.assertEqual(
            stored.initiating_session_digest,
            hashlib.sha256(b"admin-session-id").hexdigest(),
        )
        self.assertEqual(stored.expires_at, now + timedelta(minutes=10))

        with self.Session() as session:
            consumed = consume_oauth_state(
                session,
                raw_state=raw_state,
                provider=Provider.QIANCHUAN,
                now=now + timedelta(minutes=1),
            )
            session.commit()
            self.assertEqual(consumed.return_path, "/app/api-connections/accounts")
        with self.Session() as session, self.assertRaises(OAuthStateInvalid):
            consume_oauth_state(
                session,
                raw_state=raw_state,
                provider=Provider.QIANCHUAN,
                now=now + timedelta(minutes=2),
            )

    def test_wrong_provider_and_expiry_do_not_allow_consumption(self):
        now = datetime(2026, 7, 13, 10, 0, tzinfo=UTC)
        with self.Session() as session:
            raw_state = create_oauth_state(
                session,
                provider=Provider.PDD,
                session_id="admin-session-id",
                return_path="/app/api-connections",
                now=now,
            )
            session.commit()
        with self.Session() as session, self.assertRaises(OAuthStateInvalid):
            consume_oauth_state(
                session,
                raw_state=raw_state,
                provider=Provider.TAOBAO,
                now=now + timedelta(minutes=1),
            )
        with self.Session() as session:
            row = session.execute(select(IntegrationOAuthState)).scalar_one()
            self.assertIsNone(row.consumed_at)
        with self.Session() as session, self.assertRaises(OAuthStateInvalid):
            consume_oauth_state(
                session,
                raw_state=raw_state,
                provider=Provider.PDD,
                now=now + timedelta(minutes=10),
            )

    def test_state_rejects_every_unsafe_return_path(self):
        unsafe = (
            "https://attacker.example/app/api-connections",
            "//attacker.example/app/api-connections",
            "/app/api-connections?next=x",
            "/app/api-connections#x",
            "/app/api-connections/",
            "/app/api-connections//accounts",
            "/app/api-connections/../app",
            "/app/api-connections/%2e%2e/app",
            "/app/api-connections\\accounts",
            "/app/api-connections/ account",
            "/app/api-connections/\naccount",
            "/app/other",
        )
        with self.Session() as session:
            for return_path in unsafe:
                with self.subTest(return_path=return_path), self.assertRaises(ValueError):
                    create_oauth_state(
                        session,
                        provider=Provider.DOUDIAN,
                        session_id="sid",
                        return_path=return_path,
                    )

    def test_two_postgres_sessions_can_have_only_one_atomic_state_winner(self):
        now = datetime(2026, 7, 13, 10, 0, tzinfo=UTC)
        with self.Session() as session:
            raw_state = create_oauth_state(
                session,
                provider=Provider.TAOBAO,
                session_id="parallel-session",
                return_path="/app/api-connections",
                now=now,
            )
            session.commit()
        barrier = Barrier(2)

        def consume() -> bool:
            with self.Session() as session:
                barrier.wait(timeout=5)
                try:
                    consume_oauth_state(
                        session,
                        raw_state=raw_state,
                        provider=Provider.TAOBAO,
                        now=now + timedelta(minutes=1),
                    )
                    session.commit()
                    return True
                except OAuthStateInvalid:
                    session.rollback()
                    return False

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: consume(), range(2)))
        self.assertEqual(sorted(results), [False, True])

    def test_concurrent_authorization_and_account_upsert_both_succeed(self):
        barrier = Barrier(2)

        def persist(suffix: str) -> str:
            tokens = TokenBundle(
                access_token=f"parallel-access-{suffix}",
                refresh_token=f"parallel-refresh-{suffix}",
                access_expires_at=datetime.now(UTC) + timedelta(hours=1),
                refresh_expires_at=datetime.now(UTC) + timedelta(days=1),
                scopes=("orders.read",),
                external_subject_id="parallel-subject",
            )
            accounts = [
                AccountIdentity(
                    "parallel-account",
                    ConnectionType.SHOP,
                    "并发店铺",
                )
            ]
            barrier.wait(timeout=5)
            with self.Session() as session:
                persist_oauth_result(
                    session,
                    provider=Provider.DOUDIAN,
                    tokens=tokens,
                    accounts=accounts,
                    master_key=MASTER_KEY,
                )
                session.commit()
            return "success"

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(persist, ("one", "two")))
        self.assertEqual(results, ["success", "success"])
        with self.Session() as session:
            self.assertEqual(
                len(session.execute(select(IntegrationAuthorization)).scalars().all()),
                1,
            )
            self.assertEqual(
                len(session.execute(select(IntegrationConnection)).scalars().all()),
                1,
            )

    def test_new_oauth_tokens_clear_any_stale_refresh_lease(self):
        tokens = TokenBundle(
            access_token="initial-access-token",
            refresh_token="initial-refresh-token",
            access_expires_at=datetime.now(UTC) + timedelta(hours=1),
            refresh_expires_at=datetime.now(UTC) + timedelta(days=1),
            scopes=("orders.read",),
            external_subject_id="lease-subject",
        )
        accounts = [
            AccountIdentity("lease-shop", ConnectionType.SHOP, "租约店铺")
        ]
        with self.Session() as session:
            persist_oauth_result(
                session,
                provider=Provider.PDD,
                tokens=tokens,
                accounts=accounts,
                master_key=MASTER_KEY,
            )
            session.commit()
        with self.Session() as session:
            authorization = session.execute(
                select(IntegrationAuthorization)
            ).scalar_one()
            authorization.refresh_lease_owner = "stale-worker-owner"
            authorization.refresh_lease_expires_at = datetime.now(UTC) + timedelta(minutes=5)
            authorization.last_refreshed_at = datetime.now(UTC)
            session.commit()

        replacement = TokenBundle(
            access_token="replacement-access-token",
            refresh_token="replacement-refresh-token",
            access_expires_at=datetime.now(UTC) + timedelta(hours=2),
            refresh_expires_at=datetime.now(UTC) + timedelta(days=2),
            scopes=("orders.read", "products.read"),
            external_subject_id="lease-subject",
        )
        with self.Session() as session:
            persist_oauth_result(
                session,
                provider=Provider.PDD,
                tokens=replacement,
                accounts=accounts,
                master_key=MASTER_KEY,
            )
            session.commit()
        with self.Session() as session:
            authorization = session.execute(
                select(IntegrationAuthorization)
            ).scalar_one()
            self.assertIsNone(authorization.refresh_lease_owner)
            self.assertIsNone(authorization.refresh_lease_expires_at)
            self.assertIsNone(authorization.last_refreshed_at)


class _FakeConnector:
    provider = Provider.QIANCHUAN

    def __init__(self, transaction_probe):
        self.transaction_probe = transaction_probe
        self.authorization_state = None
        self.redirect_uri = None

    def authorization_url(self, *, state: str, redirect_uri: str) -> str:
        self.authorization_state = state
        self.redirect_uri = redirect_uri
        return "https://fake-provider.invalid/oauth?" + urlencode({"state": state})

    async def exchange_code(self, *, code: str, redirect_uri: str) -> TokenBundle:
        if self.transaction_probe():
            raise AssertionError("exchange_code ran inside a database transaction")
        self.redirect_uri = redirect_uri
        return TokenBundle(
            access_token="access-token-sentinel-1234",
            refresh_token="refresh-token-sentinel-5678",
            access_expires_at=datetime.now(UTC) + timedelta(hours=1),
            refresh_expires_at=datetime.now(UTC) + timedelta(days=30),
            scopes=("orders.read",),
            external_subject_id="subject-001",
        )

    async def discover_accounts(self, tokens: TokenBundle) -> list[AccountIdentity]:
        if self.transaction_probe():
            raise AssertionError("discover_accounts ran inside a database transaction")
        return [
            AccountIdentity("ad-001", ConnectionType.AD_ACCOUNT, "广告账户一"),
            AccountIdentity("ad-002", ConnectionType.AD_ACCOUNT, "广告账户二"),
        ]

    async def refresh_tokens(self, tokens):  # pragma: no cover - contract stub
        raise NotImplementedError

    async def probe_capabilities(self, connection):  # pragma: no cover
        raise NotImplementedError

    async def fetch_page(self, **kwargs):  # pragma: no cover
        raise NotImplementedError

    async def revoke(self, connection):  # pragma: no cover
        raise NotImplementedError


class _ExchangeFailConnector(_FakeConnector):
    async def exchange_code(self, *, code: str, redirect_uri: str) -> TokenBundle:
        if self.transaction_probe():
            raise AssertionError("exchange_code ran inside a database transaction")
        raise RuntimeError("provider-error-token-secret-sentinel-4455")


class _DiscoveryFailConnector(_FakeConnector):
    async def discover_accounts(self, tokens: TokenBundle) -> list[AccountIdentity]:
        if self.transaction_probe():
            raise AssertionError("discover_accounts ran inside a database transaction")
        raise RuntimeError("discovery-error-secret-sentinel-6633")


class _InvalidAuthorizationUrlConnector(_FakeConnector):
    def authorization_url(self, *, state: str, redirect_uri: str) -> str:
        self.authorization_state = state
        return "http://attacker.invalid/oauth#state-secret"


class _AuthorizationUrlRuleConnector(_FakeConnector):
    def __init__(self, transaction_probe, mode: str):
        super().__init__(transaction_probe)
        self.mode = mode

    def authorization_url(self, *, state: str, redirect_uri: str) -> str:
        self.authorization_state = state
        if self.mode == "missing":
            return "https://fake-provider.invalid/oauth"
        if self.mode == "duplicate":
            return f"https://fake-provider.invalid/oauth?state={state}&state={state}"
        if self.mode == "wrong":
            return "https://fake-provider.invalid/oauth?state=wrong-state"
        if self.mode == "control":
            return f"https://fake-provider.invalid/oauth?state={state}\n"
        raise AssertionError("unknown authorization URL mode")


class _EventConnector(_FakeConnector):
    def verify_event(self, headers, body) -> VerifiedEvent:
        return VerifiedEvent(
            provider=self.provider,
            external_event_id="event-1",
            external_subject_id="subject-1",
            event_id_scope=EventIdScope.SUBJECT,
            event_type="order.updated",
            external_entity_id="order-1",
            platform_updated_at=datetime.now(UTC),
            sanitized_payload={"status": "paid"},
        )


class OAuthEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = assert_disposable_postgres(
            url_env="FACAI_TEST_DATABASE_URL",
            acknowledgement_env="FACAI_DESTRUCTIVE_TEST_DATABASE_ACK",
        )
        cls.engine = create_database_engine(cls.database_url)
        cls.Session = sessionmaker(bind=cls.engine, expire_on_commit=False)
        cls.password_hash = hash_admin_password("task-nine-password", salt=b"9" * 16)
        cls.environment = {
            ADMIN_PASSWORD_HASH_ENV: cls.password_hash,
            SESSION_SECRET_ENV: _base64url(SESSION_SECRET),
            MASTER_KEY_ENV: _base64url(MASTER_KEY),
            INTERNAL_BASE_URL_ENV: "https://internal.integration.test",
            PUBLIC_BASE_URL_ENV: "https://public.integration.test",
            ARCHIVE_DIR_ENV: str((Path(__file__).parents[1] / "data" / "task9").resolve()),
            TRUSTED_PROXY_CIDRS_ENV: "",
            WORKER_CONCURRENCY_ENV: "1",
            DATABASE_URL_ENV: cls.database_url,
        }
        Base.metadata.drop_all(cls.engine, tables=OAUTH_TABLES, checkfirst=True)
        Base.metadata.create_all(cls.engine, tables=OAUTH_TABLES, checkfirst=False)

    @classmethod
    def tearDownClass(cls):
        try:
            Base.metadata.drop_all(cls.engine, tables=OAUTH_TABLES, checkfirst=True)
        finally:
            cls.engine.dispose()

    def setUp(self):
        Base.metadata.drop_all(self.engine, tables=OAUTH_TABLES, checkfirst=True)
        Base.metadata.create_all(self.engine, tables=OAUTH_TABLES, checkfirst=False)
        self.environment_patch = patch.dict(os.environ, self.environment, clear=False)
        self.environment_patch.start()
        self.current_session = None

        def override_db():
            session = self.Session()
            self.current_session = session
            try:
                yield session
            finally:
                session.close()
                self.current_session = None

        app.dependency_overrides[get_db] = override_db
        with self.Session() as session:
            session.add(
                IntegrationAppConfig(
                    provider=Provider.QIANCHUAN,
                    app_id="fake-app-id",
                    app_secret_ciphertext=encrypt_credential(
                        "fake-app-secret",
                        master_key=MASTER_KEY,
                        purpose=CredentialPurpose.APP_SECRET,
                    ),
                    app_secret_tail="cret",
                    status="configured",
                )
            )
            session.commit()
        self.registry = ConnectorRegistry()

    def tearDown(self):
        app.dependency_overrides.pop(get_db, None)
        self.environment_patch.stop()

    @contextmanager
    def _client(self, origin: str, *, authenticated: bool = False):
        client = TestClient(app, base_url=origin, raise_server_exceptions=False)
        if authenticated:
            client.cookies.set(
                INTEGRATION_ADMIN_COOKIE,
                issue_admin_session(session_secret=SESSION_SECRET),
            )
        try:
            yield client
        finally:
            client.close()

    def test_missing_connector_is_503_and_does_not_create_state(self):
        with (
            patch("routers.integrations.connector_registry", self.registry),
            self._client(self.environment[INTERNAL_BASE_URL_ENV], authenticated=True) as client,
        ):
            response = client.post(
                "/api/integrations/providers/qianchuan/authorize",
                headers={"Origin": self.environment[INTERNAL_BASE_URL_ENV]},
                json={"return_path": "/app/api-connections"},
            )
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(response.json(), {"detail": {"code": "connector_unavailable"}})
        with self.Session() as session:
            self.assertIsNone(session.execute(select(IntegrationOAuthState)).scalar_one_or_none())

    def test_complete_fake_browser_flow_consumes_state_without_public_cookie(self):
        connector = _FakeConnector(lambda: bool(self.current_session and self.current_session.in_transaction()))
        self.registry.register(connector)
        with (
            patch("routers.integrations.connector_registry", self.registry),
            self._client(self.environment[INTERNAL_BASE_URL_ENV], authenticated=True) as internal,
        ):
            start = internal.post(
                "/api/integrations/providers/qianchuan/authorize",
                headers={"Origin": self.environment[INTERNAL_BASE_URL_ENV]},
                json={"return_path": "/app/api-connections/accounts"},
            )
        self.assertEqual(start.status_code, 200, start.text)
        self.assertEqual(set(start.json()), {"authorization_url"})
        raw_state = connector.authorization_state
        self.assertTrue(raw_state)
        self.assertEqual(
            connector.redirect_uri,
            "https://public.integration.test/integrations/oauth/callback/qianchuan",
        )

        with (
            patch("routers.integrations.connector_registry", self.registry),
            self._client(self.environment[PUBLIC_BASE_URL_ENV], authenticated=False) as public,
        ):
            callback = public.get(
                "/integrations/oauth/callback/qianchuan",
                params={"state": raw_state, "code": "provider-code-sentinel"},
                follow_redirects=False,
            )
        self.assertEqual(callback.status_code, 303, callback.text)
        redirect = urlsplit(callback.headers["location"])
        self.assertEqual(f"{redirect.scheme}://{redirect.netloc}", self.environment[INTERNAL_BASE_URL_ENV])
        self.assertEqual(redirect.path, "/app/api-connections/accounts")
        self.assertEqual(parse_qs(redirect.query), {"provider": ["qianchuan"], "oauth_result": ["success"]})
        rendered = callback.text + repr(callback.headers)
        for sentinel in (raw_state, "provider-code-sentinel", "access-token-sentinel-1234", "refresh-token-sentinel-5678"):
            self.assertNotIn(sentinel, rendered)

        with self.Session() as session:
            state = session.execute(select(IntegrationOAuthState)).scalar_one()
            authorization = session.execute(select(IntegrationAuthorization)).scalar_one()
            connections = session.execute(select(IntegrationConnection).order_by(IntegrationConnection.external_account_id)).scalars().all()
            self.assertIsNotNone(state.consumed_at)
            self.assertEqual(len(connections), 2)
            self.assertTrue(all(item.authorization_id == authorization.id for item in connections))
            self.assertTrue(all(item.status == ConnectionStatus.SETUP_REQUIRED for item in connections))
            self.assertTrue(all(item.capability_report == {} for item in connections))
            self.assertEqual(
                decrypt_credential(authorization.access_token_ciphertext, master_key=MASTER_KEY, purpose=CredentialPurpose.ACCESS_TOKEN),
                "access-token-sentinel-1234",
            )
            self.assertEqual(
                decrypt_credential(authorization.refresh_token_ciphertext, master_key=MASTER_KEY, purpose=CredentialPurpose.REFRESH_TOKEN),
                "refresh-token-sentinel-5678",
            )

    def test_exchange_failure_consumes_state_rolls_back_and_audits_only_safe_code(self):
        connector = _ExchangeFailConnector(
            lambda: bool(self.current_session and self.current_session.in_transaction())
        )
        self.registry.register(connector)
        with (
            patch("routers.integrations.connector_registry", self.registry),
            self._client(self.environment[INTERNAL_BASE_URL_ENV], authenticated=True) as internal,
        ):
            start = internal.post(
                "/api/integrations/providers/qianchuan/authorize",
                headers={"Origin": self.environment[INTERNAL_BASE_URL_ENV]},
                json={"return_path": "/app/api-connections"},
            )
        self.assertEqual(start.status_code, 200, start.text)
        raw_state = connector.authorization_state
        code = "failed-provider-code-sentinel-8899"
        with (
            patch("routers.integrations.connector_registry", self.registry),
            self._client(self.environment[PUBLIC_BASE_URL_ENV]) as public,
        ):
            failed = public.get(
                "/integrations/oauth/callback/qianchuan",
                params={"state": raw_state, "code": code},
                follow_redirects=False,
            )
            replay = public.get(
                "/integrations/oauth/callback/qianchuan",
                params={"state": raw_state, "code": code},
            )
        self.assertEqual(failed.status_code, 303, failed.text)
        self.assertEqual(
            parse_qs(urlsplit(failed.headers["location"]).query),
            {"provider": ["qianchuan"], "oauth_result": ["exchange_failed"]},
        )
        self.assertEqual(replay.status_code, 400, replay.text)
        rendered = failed.text + repr(failed.headers) + replay.text
        for sentinel in (
            raw_state,
            code,
            "provider-error-token-secret-sentinel-4455",
        ):
            self.assertNotIn(sentinel, rendered)
        with self.Session() as session:
            state = session.execute(select(IntegrationOAuthState)).scalar_one()
            audit = session.execute(
                select(IntegrationSecurityAudit).where(
                    IntegrationSecurityAudit.event_type == "oauth_callback_failed"
                )
            ).scalar_one()
            self.assertIsNotNone(state.consumed_at)
            self.assertIsNone(
                session.execute(select(IntegrationAuthorization)).scalar_one_or_none()
            )
            self.assertIsNone(
                session.execute(select(IntegrationConnection)).scalar_one_or_none()
            )
            self.assertEqual(audit.summary_code, "oauth_completion_failed")
            self.assertEqual(audit.details, {"stage": "exchange"})
            self.assertNotIn("sentinel", repr(audit.details))

    def test_invalid_connector_url_and_strict_body_leave_no_oauth_state(self):
        connector = _InvalidAuthorizationUrlConnector(lambda: False)
        self.registry.register(connector)
        body_sentinel = "authorization-extra-sentinel-1010"
        with (
            patch("routers.integrations.connector_registry", self.registry),
            self._client(self.environment[INTERNAL_BASE_URL_ENV], authenticated=True) as client,
        ):
            invalid_body = client.post(
                "/api/integrations/providers/qianchuan/authorize",
                headers={"Origin": self.environment[INTERNAL_BASE_URL_ENV]},
                json={
                    "return_path": "/app/api-connections",
                    "unexpected": body_sentinel,
                },
            )
            invalid_url = client.post(
                "/api/integrations/providers/qianchuan/authorize",
                headers={"Origin": self.environment[INTERNAL_BASE_URL_ENV]},
                json={"return_path": "/app/api-connections"},
            )
        self.assertEqual(invalid_body.status_code, 422, invalid_body.text)
        self.assertNotIn(body_sentinel, invalid_body.text)
        self.assertEqual(invalid_url.status_code, 503, invalid_url.text)
        self.assertEqual(
            invalid_url.json(),
            {"detail": {"code": "connector_authorization_unavailable"}},
        )
        self.assertNotIn("attacker.invalid", invalid_url.text)
        with self.Session() as session:
            self.assertIsNone(
                session.execute(select(IntegrationOAuthState)).scalar_one_or_none()
            )

    def test_discovery_failure_has_no_partial_credentials_and_safe_audit(self):
        connector = _DiscoveryFailConnector(
            lambda: bool(self.current_session and self.current_session.in_transaction())
        )
        self.registry.register(connector)
        with (
            patch("routers.integrations.connector_registry", self.registry),
            self._client(self.environment[INTERNAL_BASE_URL_ENV], authenticated=True) as internal,
        ):
            start = internal.post(
                "/api/integrations/providers/qianchuan/authorize",
                headers={"Origin": self.environment[INTERNAL_BASE_URL_ENV]},
                json={"return_path": "/app/api-connections"},
            )
        with (
            patch("routers.integrations.connector_registry", self.registry),
            self._client(self.environment[PUBLIC_BASE_URL_ENV]) as public,
        ):
            response = public.get(
                "/integrations/oauth/callback/qianchuan",
                params={"state": connector.authorization_state, "code": "discovery-code"},
                follow_redirects=False,
            )
        self.assertEqual(start.status_code, 200, start.text)
        self.assertEqual(response.status_code, 303, response.text)
        self.assertNotIn("discovery-error-secret-sentinel-6633", response.text)
        with self.Session() as session:
            self.assertIsNone(
                session.execute(select(IntegrationAuthorization)).scalar_one_or_none()
            )
            self.assertIsNone(
                session.execute(select(IntegrationConnection)).scalar_one_or_none()
            )
            audit = session.execute(
                select(IntegrationSecurityAudit).where(
                    IntegrationSecurityAudit.event_type == "oauth_callback_failed"
                )
            ).scalar_one()
            self.assertEqual(audit.details, {"stage": "discovery"})

    def test_persistence_failure_rolls_back_credentials_and_uses_separate_audit(self):
        connector = _FakeConnector(
            lambda: bool(self.current_session and self.current_session.in_transaction())
        )
        self.registry.register(connector)
        with (
            patch("routers.integrations.connector_registry", self.registry),
            self._client(self.environment[INTERNAL_BASE_URL_ENV], authenticated=True) as internal,
        ):
            start = internal.post(
                "/api/integrations/providers/qianchuan/authorize",
                headers={"Origin": self.environment[INTERNAL_BASE_URL_ENV]},
                json={"return_path": "/app/api-connections"},
            )
        persistence_sentinel = "persistence-error-secret-sentinel-7744"
        with (
            patch("routers.integrations.connector_registry", self.registry),
            patch(
                "routers.integrations.persist_oauth_result",
                side_effect=RuntimeError(persistence_sentinel),
            ),
            self._client(self.environment[PUBLIC_BASE_URL_ENV]) as public,
        ):
            response = public.get(
                "/integrations/oauth/callback/qianchuan",
                params={"state": connector.authorization_state, "code": "persistence-code"},
                follow_redirects=False,
            )
        self.assertEqual(start.status_code, 200, start.text)
        self.assertEqual(response.status_code, 303, response.text)
        self.assertNotIn(persistence_sentinel, response.text + repr(response.headers))
        with self.Session() as session:
            state = session.execute(select(IntegrationOAuthState)).scalar_one()
            self.assertIsNotNone(state.consumed_at)
            self.assertIsNone(
                session.execute(select(IntegrationAuthorization)).scalar_one_or_none()
            )
            self.assertIsNone(
                session.execute(select(IntegrationConnection)).scalar_one_or_none()
            )
            audit = session.execute(
                select(IntegrationSecurityAudit).where(
                    IntegrationSecurityAudit.event_type == "oauth_callback_failed"
                )
            ).scalar_one()
            self.assertEqual(audit.details, {"stage": "persistence"})

    def test_unknown_state_returns_stable_400_without_echo_or_cookie_influence(self):
        unknown = "unknown-oauth-state-sentinel-2020"
        with self._client(self.environment[PUBLIC_BASE_URL_ENV]) as public:
            public.cookies.set(INTEGRATION_ADMIN_COOKIE, "unrelated-cookie-sentinel")
            response = public.get(
                "/integrations/oauth/callback/pdd",
                params={"state": unknown, "code": "unknown-code-sentinel"},
            )
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(response.json(), {"detail": {"code": "invalid_oauth_callback"}})
        self.assertNotIn(unknown, response.text)
        self.assertNotIn("unknown-code-sentinel", response.text)
        self.assertNotIn("unrelated-cookie-sentinel", response.text)

    def test_https_authorization_url_requires_one_exact_state_and_no_controls(self):
        for mode in ("missing", "duplicate", "wrong", "control"):
            registry = ConnectorRegistry()
            connector = _AuthorizationUrlRuleConnector(lambda: False, mode)
            registry.register(connector)
            with (
                self.subTest(mode=mode),
                patch("routers.integrations.connector_registry", registry),
                self._client(
                    self.environment[INTERNAL_BASE_URL_ENV], authenticated=True
                ) as client,
            ):
                response = client.post(
                    "/api/integrations/providers/qianchuan/authorize",
                    headers={"Origin": self.environment[INTERNAL_BASE_URL_ENV]},
                    json={"return_path": "/app/api-connections"},
                )
            self.assertEqual(response.status_code, 503, response.text)
            self.assertEqual(
                response.json(),
                {"detail": {"code": "connector_authorization_unavailable"}},
            )
            with self.Session() as session:
                self.assertIsNone(
                    session.execute(
                        select(IntegrationOAuthState)
                    ).scalar_one_or_none()
                )

    def test_readiness_failure_before_callback_does_not_consume_state(self):
        connector = _FakeConnector(lambda: False)
        self.registry.register(connector)
        with (
            patch("routers.integrations.connector_registry", self.registry),
            self._client(
                self.environment[INTERNAL_BASE_URL_ENV], authenticated=True
            ) as internal,
        ):
            start = internal.post(
                "/api/integrations/providers/qianchuan/authorize",
                headers={"Origin": self.environment[INTERNAL_BASE_URL_ENV]},
                json={"return_path": "/app/api-connections"},
            )
        self.assertEqual(start.status_code, 200, start.text)
        invalid_environment = dict(self.environment)
        invalid_environment[MASTER_KEY_ENV] = "invalid-master-key"
        with (
            patch.dict(os.environ, invalid_environment, clear=False),
            patch("routers.integrations.connector_registry", self.registry),
            self._client(self.environment[PUBLIC_BASE_URL_ENV]) as public,
        ):
            response = public.get(
                "/integrations/oauth/callback/qianchuan",
                params={"state": connector.authorization_state, "code": "code"},
            )
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(
            response.json(),
            {"detail": {"code": "security_configuration_incomplete"}},
        )
        with self.Session() as session:
            state = session.execute(select(IntegrationOAuthState)).scalar_one()
            self.assertIsNone(state.consumed_at)

    def test_ownership_conflict_consumes_state_without_changing_existing_tokens(self):
        old_tokens = TokenBundle(
            access_token="existing-owner-access-token",
            refresh_token="existing-owner-refresh-token",
            access_expires_at=datetime.now(UTC) + timedelta(hours=1),
            refresh_expires_at=datetime.now(UTC) + timedelta(days=1),
            scopes=("orders.read",),
            external_subject_id="existing-owner-subject",
        )
        with self.Session() as session:
            persist_oauth_result(
                session,
                provider=Provider.QIANCHUAN,
                tokens=old_tokens,
                accounts=[
                    AccountIdentity(
                        "ad-001",
                        ConnectionType.AD_ACCOUNT,
                        "既有账户",
                    )
                ],
                master_key=MASTER_KEY,
            )
            session.commit()
            old_authorization = session.execute(
                select(IntegrationAuthorization)
            ).scalar_one()
            old_ciphertext = old_authorization.access_token_ciphertext
            old_authorization_id = old_authorization.id

        connector = _FakeConnector(
            lambda: bool(
                self.current_session and self.current_session.in_transaction()
            )
        )
        self.registry.register(connector)
        with (
            patch("routers.integrations.connector_registry", self.registry),
            self._client(
                self.environment[INTERNAL_BASE_URL_ENV], authenticated=True
            ) as internal,
        ):
            start = internal.post(
                "/api/integrations/providers/qianchuan/authorize",
                headers={"Origin": self.environment[INTERNAL_BASE_URL_ENV]},
                json={"return_path": "/app/api-connections"},
            )
        with (
            patch("routers.integrations.connector_registry", self.registry),
            self._client(self.environment[PUBLIC_BASE_URL_ENV]) as public,
        ):
            callback = public.get(
                "/integrations/oauth/callback/qianchuan",
                params={"state": connector.authorization_state, "code": "new-code"},
                follow_redirects=False,
            )
        self.assertEqual(start.status_code, 200, start.text)
        self.assertEqual(callback.status_code, 303, callback.text)
        self.assertEqual(
            parse_qs(urlsplit(callback.headers["location"]).query)["oauth_result"],
            ["exchange_failed"],
        )
        with self.Session() as session:
            state = session.execute(select(IntegrationOAuthState)).scalar_one()
            authorizations = session.execute(
                select(IntegrationAuthorization)
            ).scalars().all()
            connections = session.execute(
                select(IntegrationConnection)
            ).scalars().all()
            audit = session.execute(
                select(IntegrationSecurityAudit).where(
                    IntegrationSecurityAudit.event_type == "oauth_callback_failed"
                )
            ).scalar_one()
            self.assertIsNotNone(state.consumed_at)
            self.assertEqual(len(authorizations), 1)
            self.assertEqual(authorizations[0].id, old_authorization_id)
            self.assertEqual(authorizations[0].access_token_ciphertext, old_ciphertext)
            self.assertEqual(len(connections), 1)
            self.assertEqual(connections[0].authorization_id, old_authorization_id)
            self.assertEqual(audit.details, {"stage": "persistence"})

    def test_verified_event_is_not_acknowledged_before_durable_pipeline_exists(self):
        connector = _EventConnector(lambda: False)
        self.registry.register(connector)
        with (
            patch("routers.integrations.connector_registry", self.registry),
            self._client(self.environment[PUBLIC_BASE_URL_ENV]) as public,
        ):
            response = public.post(
                "/integrations/events/qianchuan",
                content=b'{"safe":"payload"}',
                headers={"Content-Type": "application/json"},
            )
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(
            response.json(),
            {"detail": {"code": "event_pipeline_unavailable"}},
        )


class ConnectorRegistryTests(unittest.TestCase):
    def test_production_registry_starts_empty_and_requires_provider_enum(self):
        registry = ConnectorRegistry()
        with self.assertRaises(ConnectorUnavailable):
            registry.get(Provider.PDD)
        with self.assertRaises((TypeError, ValueError)):
            registry.get("pdd")

        class IncompleteConnector:
            provider = Provider.PDD

        with self.assertRaises(TypeError):
            registry.register(IncompleteConnector())

    def test_verified_event_contract_is_frozen_slotted_and_hides_payload(self):
        sentinel = "verified-event-payload-sentinel"
        event = VerifiedEvent(
            provider=Provider.DOUDIAN,
            external_event_id="event-id",
            external_subject_id="subject-id",
            event_id_scope=EventIdScope.SUBJECT,
            event_type="order.updated",
            external_entity_id="order-id",
            platform_updated_at=datetime.now(UTC),
            sanitized_payload={"value": sentinel},
        )
        self.assertFalse(hasattr(event, "__dict__"))
        self.assertNotIn(sentinel, repr(event))
        with self.assertRaises((AttributeError, TypeError)):
            event.event_type = "changed"


class ConnectorOutputValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = assert_disposable_postgres(
            url_env="FACAI_TEST_DATABASE_URL",
            acknowledgement_env="FACAI_DESTRUCTIVE_TEST_DATABASE_ACK",
        )
        cls.engine = create_database_engine(cls.database_url)
        cls.Session = sessionmaker(bind=cls.engine, expire_on_commit=False)
        Base.metadata.drop_all(cls.engine, tables=OAUTH_TABLES, checkfirst=True)
        Base.metadata.create_all(cls.engine, tables=OAUTH_TABLES, checkfirst=False)

    @classmethod
    def tearDownClass(cls):
        try:
            Base.metadata.drop_all(cls.engine, tables=OAUTH_TABLES, checkfirst=True)
        finally:
            cls.engine.dispose()

    def setUp(self):
        Base.metadata.drop_all(self.engine, tables=OAUTH_TABLES, checkfirst=True)
        Base.metadata.create_all(self.engine, tables=OAUTH_TABLES, checkfirst=False)

    def test_invalid_connector_tokens_and_accounts_never_write_rows(self):
        valid_tokens = TokenBundle(
            access_token="safe-access",
            refresh_token="safe-refresh",
            access_expires_at=datetime.now(UTC) + timedelta(hours=1),
            refresh_expires_at=datetime.now(UTC) + timedelta(days=1),
            scopes=("orders.read",),
            external_subject_id="safe-subject",
        )
        invalid_cases = (
            (
                TokenBundle(
                    access_token="safe-access",
                    refresh_token="safe-refresh",
                    access_expires_at=datetime.now(),
                    refresh_expires_at=datetime.now(UTC) + timedelta(days=1),
                    scopes=("orders.read",),
                    external_subject_id="safe-subject",
                ),
                [AccountIdentity("shop-1", ConnectionType.SHOP, "店铺")],
            ),
            (
                TokenBundle(
                    access_token="safe-access",
                    refresh_token="safe-refresh",
                    access_expires_at=datetime.now(UTC) + timedelta(hours=1),
                    refresh_expires_at=datetime.now(UTC) + timedelta(days=1),
                    scopes=("orders.read",),
                    external_subject_id="",
                ),
                [AccountIdentity("shop-1", ConnectionType.SHOP, "店铺")],
            ),
            (
                TokenBundle(
                    access_token="safe-access",
                    refresh_token="safe-refresh",
                    access_expires_at=datetime.now(UTC) + timedelta(hours=1),
                    refresh_expires_at=datetime.now(UTC) + timedelta(days=1),
                    scopes=("orders.read",),
                    external_subject_id="x" * 256,
                ),
                [AccountIdentity("shop-1", ConnectionType.SHOP, "店铺")],
            ),
            (
                valid_tokens,
                [AccountIdentity("", ConnectionType.SHOP, "店铺")],
            ),
            (
                valid_tokens,
                [AccountIdentity("x" * 256, ConnectionType.SHOP, "店铺")],
            ),
            (
                valid_tokens,
                [AccountIdentity("shop-1", ConnectionType.SHOP, "")],
            ),
            (
                valid_tokens,
                [AccountIdentity("shop-1", ConnectionType.SHOP, "店" * 256)],
            ),
            (
                valid_tokens,
                [
                    AccountIdentity("shop-1", ConnectionType.SHOP, "店铺一"),
                    AccountIdentity("shop-1", ConnectionType.SHOP, "店铺二"),
                ],
            ),
        )
        for tokens, accounts in invalid_cases:
            with self.subTest(tokens=tokens.external_subject_id, accounts=len(accounts)):
                with self.Session() as session, self.assertRaises(
                    ConnectorOutputInvalid
                ):
                    persist_oauth_result(
                        session,
                        provider=Provider.TAOBAO,
                        tokens=tokens,
                        accounts=accounts,
                        master_key=MASTER_KEY,
                    )
            with self.Session() as session:
                self.assertIsNone(
                    session.execute(
                        select(IntegrationAuthorization)
                    ).scalar_one_or_none()
                )
                self.assertIsNone(
                    session.execute(
                        select(IntegrationConnection)
                    ).scalar_one_or_none()
                )

    def test_direct_service_rejects_cross_authorization_account_ownership(self):
        def tokens(subject: str, access: str) -> TokenBundle:
            return TokenBundle(
                access_token=access,
                refresh_token="refresh-token",
                access_expires_at=datetime.now(UTC) + timedelta(hours=1),
                refresh_expires_at=datetime.now(UTC) + timedelta(days=1),
                scopes=("orders.read",),
                external_subject_id=subject,
            )

        account = [AccountIdentity("same-shop", ConnectionType.SHOP, "同一店铺")]
        with self.Session() as session:
            first = persist_oauth_result(
                session,
                provider=Provider.TAOBAO,
                tokens=tokens("subject-one", "access-one"),
                accounts=account,
                master_key=MASTER_KEY,
            )
            session.commit()
        with self.Session() as session, self.assertRaises(
            ConnectionOwnershipConflict
        ):
            persist_oauth_result(
                session,
                provider=Provider.TAOBAO,
                tokens=tokens("subject-two", "access-two"),
                accounts=account,
                master_key=MASTER_KEY,
            )
        with self.Session() as session:
            authorizations = session.execute(
                select(IntegrationAuthorization)
            ).scalars().all()
            connection = session.execute(select(IntegrationConnection)).scalar_one()
            self.assertEqual(len(authorizations), 1)
            self.assertEqual(connection.authorization_id, first.authorization_id)


if __name__ == "__main__":
    unittest.main()
