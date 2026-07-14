import base64
import hashlib
import hmac
import ipaddress
import json
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import inspect, select
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from database import Base, create_database_engine, get_db
from integrations.admin_auth import (
    InvalidAdminSessionError,
    LoginContextConfigurationError,
    LoginRequestContext,
    authenticate_admin_login,
    derive_login_source_digest,
    hash_admin_password,
    issue_admin_session,
    resolve_login_request_context,
    verify_admin_password,
    verify_admin_session,
)
from integrations.db_safety import assert_disposable_postgres
from integrations.settings import (
    ADMIN_PASSWORD_HASH_ENV,
    SESSION_SECRET_ENV,
    TRUSTED_PROXY_CIDRS_ENV,
    load_integration_settings,
)
from integration_models import IntegrationLoginThrottle, IntegrationSecurityAudit
from main import app


UTC = timezone.utc
SESSION_SECRET = b"session-secret-for-task-seven-tests" * 2
AUTH_TABLES = (
    IntegrationSecurityAudit.__table__,
    IntegrationLoginThrottle.__table__,
)


def _base64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _request(
    *,
    client: tuple[str, int],
    scheme: str,
    headers: tuple[tuple[bytes, bytes], ...] = (),
) -> Request:
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": scheme,
            "path": "/api/integrations/session",
            "raw_path": b"/api/integrations/session",
            "query_string": b"",
            "headers": list(headers),
            "client": client,
            "server": ("admin.example.test", 443),
        }
    )


class AdminPasswordTests(unittest.TestCase):
    def test_fixed_scrypt_encoding_verifies_only_the_approved_password(self):
        salt = bytes(range(16))

        encoded = hash_admin_password("correct horse battery staple", salt=salt)

        self.assertRegex(
            encoded,
            r"^\$scrypt\$n=32768,r=8,p=1\$[A-Za-z0-9_-]{22}"
            r"\$[A-Za-z0-9_-]{86}$",
        )
        self.assertTrue(
            verify_admin_password("correct horse battery staple", encoded)
        )
        self.assertFalse(verify_admin_password("wrong password", encoded))

        digest = hashlib.scrypt(
            b"correct horse battery staple",
            salt=salt,
            n=32768,
            r=8,
            p=1,
            dklen=64,
            maxmem=134_217_728,
        )
        expected_digest = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
        self.assertEqual(encoded.rsplit("$", 1)[1], expected_digest)

    def test_malformed_hash_still_runs_scrypt_and_constant_time_comparison(self):
        real_scrypt = hashlib.scrypt
        real_compare = hmac.compare_digest

        with (
            patch(
                "integrations.admin_auth.hashlib.scrypt",
                wraps=real_scrypt,
            ) as scrypt_call,
            patch(
                "integrations.admin_auth.hmac.compare_digest",
                wraps=real_compare,
            ) as compare_call,
        ):
            verified = verify_admin_password(
                "bounded password",
                "$scrypt$n=1,r=1,p=1$not-canonical$not-a-digest",
            )

        self.assertFalse(verified)
        scrypt_call.assert_called_once()
        compare_call.assert_called_once()
        self.assertEqual(len(compare_call.call_args.args[0]), 64)
        self.assertEqual(len(compare_call.call_args.args[1]), 64)

    def test_utf8_password_limit_is_enforced_before_scrypt(self):
        with patch("integrations.admin_auth.hashlib.scrypt") as scrypt_call:
            with self.assertRaisesRegex(ValueError, "512 UTF-8 bytes"):
                hash_admin_password("界" * 171, salt=b"s" * 16)
            self.assertFalse(
                verify_admin_password(
                    "界" * 171,
                    "$scrypt$n=32768,r=8,p=1$"
                    "c3Nzc3Nzc3Nzc3Nzc3Nzcw$"
                    + "A" * 86,
                )
            )

        scrypt_call.assert_not_called()

    def test_hash_rejects_non_sixteen_byte_salt(self):
        for salt in (b"", b"s" * 15, b"s" * 17):
            with self.subTest(length=len(salt)), self.assertRaises(ValueError):
                hash_admin_password("password", salt=salt)


class AdminSessionTests(unittest.TestCase):
    def test_session_is_canonical_signed_and_expires_after_exactly_eight_hours(self):
        now = datetime(2026, 7, 13, 8, 0, tzinfo=UTC)

        cookie = issue_admin_session(session_secret=SESSION_SECRET, now=now)
        claims = verify_admin_session(
            cookie,
            session_secret=SESSION_SECRET,
            now=now,
        )

        self.assertEqual(claims.iat, now)
        self.assertEqual(claims.exp, now + timedelta(hours=8))
        self.assertEqual(len(_base64url_decode(claims.sid)), 32)
        payload_part, signature_part = cookie.split(".")
        payload = _base64url_decode(payload_part)
        parsed = json.loads(payload)
        self.assertEqual(
            payload,
            json.dumps(
                parsed,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode("ascii"),
        )
        self.assertEqual(set(parsed), {"exp", "iat", "sid", "v"})
        self.assertEqual(parsed["v"], 1)
        self.assertEqual(len(_base64url_decode(signature_part)), 32)

    def test_session_rejects_tampering_expiry_and_future_iat(self):
        now = datetime(2026, 7, 13, 8, 0, tzinfo=UTC)
        cookie = issue_admin_session(session_secret=SESSION_SECRET, now=now)
        payload_part, signature_part = cookie.split(".")
        replacement = "A" if signature_part[-1] != "A" else "B"
        tampered = f"{payload_part}.{signature_part[:-1]}{replacement}"

        with self.assertRaises(ValueError):
            verify_admin_session(
                tampered,
                session_secret=SESSION_SECRET,
                now=now,
            )
        with self.assertRaises(ValueError):
            verify_admin_session(
                cookie,
                session_secret=SESSION_SECRET,
                now=now + timedelta(hours=8),
            )

        future_cookie = issue_admin_session(
            session_secret=SESSION_SECRET,
            now=now + timedelta(seconds=61),
        )
        with self.assertRaises(ValueError):
            verify_admin_session(
                future_cookie,
                session_secret=SESSION_SECRET,
                now=now,
            )

    def test_session_rejects_noncanonical_or_ambiguous_claims(self):
        now = datetime(2026, 7, 13, 8, 0, tzinfo=UTC)
        issued = issue_admin_session(session_secret=SESSION_SECRET, now=now)
        payload_part, _ = issued.split(".")
        parsed = json.loads(_base64url_decode(payload_part))
        ambiguous_payload = (
            '{"v":2,"v":1,"sid":"%s","iat":%d,"exp":%d}'
            % (parsed["sid"], parsed["iat"], parsed["exp"])
        ).encode("ascii")
        ambiguous_part = (
            base64.urlsafe_b64encode(ambiguous_payload).rstrip(b"=").decode("ascii")
        )
        signature = hmac.new(
            SESSION_SECRET,
            ambiguous_part.encode("ascii"),
            hashlib.sha256,
        ).digest()
        signature_part = (
            base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
        )

        with self.assertRaises(ValueError):
            verify_admin_session(
                f"{ambiguous_part}.{signature_part}",
                session_secret=SESSION_SECRET,
                now=now,
            )

    def test_pathological_signed_json_fails_with_the_generic_session_error(self):
        pathological_payload = ("[" * 1100 + "0" + "]" * 1100).encode("ascii")
        payload_part = (
            base64.urlsafe_b64encode(pathological_payload)
            .rstrip(b"=")
            .decode("ascii")
        )
        signature_part = (
            base64.urlsafe_b64encode(
                hmac.new(
                    SESSION_SECRET,
                    payload_part.encode("ascii"),
                    hashlib.sha256,
                ).digest()
            )
            .rstrip(b"=")
            .decode("ascii")
        )

        with self.assertRaises(InvalidAdminSessionError):
            verify_admin_session(
                f"{payload_part}.{signature_part}",
                session_secret=SESSION_SECRET,
            )


class LoginRequestContextTests(unittest.TestCase):
    def setUp(self):
        self.trusted = (ipaddress.ip_network("10.20.0.0/16"),)

    def test_untrusted_peer_ignores_forwarding_headers(self):
        request = _request(
            client=("198.51.100.10", 50000),
            scheme="http",
            headers=(
                (b"x-forwarded-for", b"203.0.113.90"),
                (b"x-forwarded-proto", b"https"),
            ),
        )

        context = resolve_login_request_context(request, self.trusted)

        self.assertEqual(context.client_ip, ipaddress.ip_address("198.51.100.10"))
        self.assertEqual(context.effective_scheme, "http")
        self.assertFalse(context.peer_is_trusted_proxy)

    def test_trusted_proxy_selects_first_untrusted_hop_from_the_right(self):
        request = _request(
            client=("10.20.0.5", 50000),
            scheme="http",
            headers=(
                (
                    b"x-forwarded-for",
                    b"198.51.100.20, 203.0.113.30, 10.20.0.7",
                ),
                (b"x-forwarded-proto", b"https"),
            ),
        )

        context = resolve_login_request_context(request, self.trusted)

        self.assertEqual(context.client_ip, ipaddress.ip_address("203.0.113.30"))
        self.assertEqual(context.effective_scheme, "https")
        self.assertTrue(context.peer_is_trusted_proxy)

    def test_all_trusted_forwarded_hops_use_leftmost_address(self):
        request = _request(
            client=("10.20.0.5", 50000),
            scheme="https",
            headers=((b"x-forwarded-for", b"10.20.0.8, 10.20.0.9"),),
        )

        context = resolve_login_request_context(request, self.trusted)

        self.assertEqual(context.client_ip, ipaddress.ip_address("10.20.0.8"))
        self.assertEqual(context.effective_scheme, "https")

    def test_trusted_proxy_malformed_headers_fail_closed_with_stable_error(self):
        cases = (
            (),
            ((b"x-forwarded-for", b"not-an-ip"), (b"x-forwarded-proto", b"https")),
            ((b"x-forwarded-for", b"198.51.100.2"),),
            (
                (b"x-forwarded-for", b"198.51.100.2"),
                (b"x-forwarded-proto", b"https,http"),
            ),
            (
                (b"x-forwarded-for", b"198.51.100.2"),
                (b"x-forwarded-proto", b"https"),
                (b"x-forwarded-proto", b"https"),
            ),
        )
        for headers in cases:
            with self.subTest(headers=headers):
                request = _request(
                    client=("10.20.0.5", 50000),
                    scheme="http",
                    headers=headers,
                )
                with self.assertRaises(LoginContextConfigurationError) as caught:
                    resolve_login_request_context(request, self.trusted)
                self.assertEqual(
                    str(caught.exception),
                    "Trusted proxy forwarding configuration is invalid",
                )

    def test_distinct_forwarded_clients_have_distinct_hmac_source_digests(self):
        contexts = []
        for address in ("198.51.100.41", "198.51.100.42"):
            request = _request(
                client=("10.20.0.5", 50000),
                scheme="http",
                headers=(
                    (b"x-forwarded-for", address.encode("ascii")),
                    (b"x-forwarded-proto", b"https"),
                ),
            )
            contexts.append(resolve_login_request_context(request, self.trusted))

        digests = [
            derive_login_source_digest(
                session_secret=SESSION_SECRET,
                client_ip=context.client_ip,
            )
            for context in contexts
        ]

        self.assertNotEqual(digests[0], digests[1])
        self.assertTrue(all(len(value) == 64 for value in digests))
        expected = hmac.new(
            SESSION_SECRET,
            b"login-source/v1:" + ipaddress.ip_address("198.51.100.41").packed,
            hashlib.sha256,
        ).hexdigest()
        self.assertEqual(digests[0], expected)


class IntegrationSessionEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = assert_disposable_postgres(
            url_env="FACAI_TEST_DATABASE_URL",
            acknowledgement_env="FACAI_DESTRUCTIVE_TEST_DATABASE_ACK",
        )
        cls.engine = create_database_engine(cls.database_url)
        cls.Session = sessionmaker(bind=cls.engine, expire_on_commit=False)
        cls.password = "task-seven-admin-password"
        cls.password_hash = hash_admin_password(cls.password, salt=b"a" * 16)
        cls.environment = {
            ADMIN_PASSWORD_HASH_ENV: cls.password_hash,
            SESSION_SECRET_ENV: base64.urlsafe_b64encode(SESSION_SECRET)
            .rstrip(b"=")
            .decode("ascii"),
            TRUSTED_PROXY_CIDRS_ENV: "10.20.0.0/16",
        }
        try:
            Base.metadata.drop_all(cls.engine, tables=AUTH_TABLES, checkfirst=True)
            Base.metadata.create_all(cls.engine, tables=AUTH_TABLES, checkfirst=False)
        except Exception:
            Base.metadata.drop_all(cls.engine, tables=AUTH_TABLES, checkfirst=True)
            cls.engine.dispose()
            raise

    @classmethod
    def tearDownClass(cls):
        try:
            Base.metadata.drop_all(cls.engine, tables=AUTH_TABLES, checkfirst=True)
            remaining = set(inspect(cls.engine).get_table_names()) & {
                table.name for table in AUTH_TABLES
            }
            if remaining:
                raise AssertionError(
                    f"Integration auth cleanup left tables behind: {sorted(remaining)}"
                )
        finally:
            cls.engine.dispose()

    def setUp(self):
        Base.metadata.drop_all(self.engine, tables=AUTH_TABLES, checkfirst=True)
        Base.metadata.create_all(self.engine, tables=AUTH_TABLES, checkfirst=False)
        self.environment_patch = patch.dict(os.environ, self.environment, clear=False)
        self.environment_patch.start()

        def override_db():
            session = self.Session()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_db

    def tearDown(self):
        app.dependency_overrides.pop(get_db, None)
        self.environment_patch.stop()

    @contextmanager
    def _client(
        self,
        *,
        scheme: str = "https",
        peer: str = "198.51.100.60",
    ):
        client = TestClient(
            app,
            base_url=f"{scheme}://127.0.0.1:8001",
            client=(peer, 50000),
            raise_server_exceptions=False,
        )
        try:
            yield client
        finally:
            client.close()

    def _login(
        self,
        client: TestClient,
        password: str,
        *,
        headers: dict[str, str] | None = None,
    ):
        return client.post(
            "/api/integrations/session",
            json={"password": password},
            headers=headers,
        )

    def test_public_post_is_strict_and_response_never_discloses_credentials(self):
        oversized_password = "界" * 171
        unknown_sentinel = "unknown-field-must-not-be-echoed"
        with self._client() as client:
            successful = self._login(client, self.password)
            unknown = client.post(
                "/api/integrations/session",
                json={"password": self.password, "unexpected": unknown_sentinel},
            )
            oversized_utf8 = client.post(
                "/api/integrations/session",
                json={"password": oversized_password},
            )

        self.assertEqual(successful.status_code, 200, successful.text)
        self.assertEqual(successful.json()["authenticated"], True)
        self.assertEqual(unknown.status_code, 422)
        self.assertEqual(oversized_utf8.status_code, 422)
        rendered = (
            successful.text
            + str(successful.headers)
            + unknown.text
            + oversized_utf8.text
        )
        self.assertNotIn(self.password, rendered)
        self.assertNotIn(self.password_hash, rendered)
        self.assertNotIn(oversized_password, rendered)
        self.assertNotIn(unknown_sentinel, rendered)
        self.assertNotIn("sid", successful.json())

    def test_protected_probe_and_delete_preserve_the_legacy_no_login_boundary(self):
        with self._client() as client:
            client.cookies.set("legacy_cookie", "keep")
            protected = client.get("/api/integrations/session")
            legacy = client.get("/api/products/categories")
            login = self._login(client, self.password)
            protected_after_login = client.get("/api/integrations/session")
            deleted = client.delete("/api/integrations/session")

            self.assertEqual(protected.status_code, 401)
            self.assertNotIn(legacy.status_code, {401, 503})
            self.assertEqual(login.status_code, 200, login.text)
            self.assertEqual(protected_after_login.status_code, 200)
            self.assertEqual(protected_after_login.json()["authenticated"], True)
            self.assertEqual(deleted.status_code, 200)
            self.assertEqual(client.cookies.get("legacy_cookie"), "keep")
            self.assertIsNone(client.cookies.get("facai_integrations_session"))

        delete_cookie = deleted.headers.get("set-cookie", "")
        self.assertIn("facai_integrations_session=", delete_cookie)
        self.assertNotIn("legacy_cookie", delete_cookie)

    def test_https_and_loopback_http_cookie_flags_are_exact(self):
        with self._client() as https_client:
            https_response = self._login(https_client, self.password)
        with self._client(scheme="http", peer="127.0.0.1") as local_client:
            local_response = self._login(local_client, self.password)

        self.assertEqual(https_response.status_code, 200, https_response.text)
        self.assertEqual(local_response.status_code, 200, local_response.text)
        https_cookie = https_response.headers["set-cookie"].lower()
        local_cookie = local_response.headers["set-cookie"].lower()
        for flag in (
            "facai_integrations_session=",
            "httponly",
            "samesite=lax",
            "path=/",
            "max-age=28800",
        ):
            self.assertIn(flag, https_cookie)
            self.assertIn(flag, local_cookie)
        self.assertIn("secure", https_cookie)
        self.assertNotIn("secure", local_cookie)

    def test_forwarded_https_is_secure_but_untrusted_spoofed_http_is_rejected(self):
        headers = {
            "X-Forwarded-For": "198.51.100.81",
            "X-Forwarded-Proto": "https",
        }
        with self._client(scheme="http", peer="10.20.0.5") as trusted_client:
            trusted = self._login(trusted_client, self.password, headers=headers)
        with self._client(scheme="http", peer="198.51.100.82") as untrusted_client:
            untrusted = self._login(untrusted_client, self.password, headers=headers)

        self.assertEqual(trusted.status_code, 200, trusted.text)
        self.assertIn("secure", trusted.headers["set-cookie"].lower())
        self.assertEqual(untrusted.status_code, 400)
        self.assertEqual(
            untrusted.json(),
            {"detail": "HTTPS is required for integration administrator login"},
        )
        self.assertNotIn("set-cookie", untrusted.headers)

    def test_tls_proxy_matching_https_origin_reaches_login_handler(self):
        with self._client(scheme="http", peer="10.20.0.5") as client:
            response = self._login(
                client,
                self.password,
                headers={
                    "X-Forwarded-For": "198.51.100.83",
                    "X-Forwarded-Proto": "https",
                    "Origin": "https://127.0.0.1:8001",
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("secure", response.headers["set-cookie"].lower())

    def test_invalid_trusted_proxy_setting_fails_before_scrypt(self):
        invalid_settings = load_integration_settings(
            {
                ADMIN_PASSWORD_HASH_ENV: self.password_hash,
                SESSION_SECRET_ENV: self.environment[SESSION_SECRET_ENV],
                TRUSTED_PROXY_CIDRS_ENV: "10.20.0.1/16",
            }
        )
        self.assertIn(TRUSTED_PROXY_CIDRS_ENV, invalid_settings.errors)
        with (
            self._client(scheme="https", peer="10.20.0.5") as client,
            patch(
                "routers.integrations.load_integration_settings",
                return_value=invalid_settings,
            ),
            patch("integrations.admin_auth.verify_admin_password") as verify,
        ):
            response = self._login(
                client,
                self.password,
                headers={"X-Forwarded-For": "198.51.100.84"},
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {"detail": "Integration trusted proxy configuration is invalid"},
        )
        verify.assert_not_called()
        with self.Session() as session:
            audit = session.execute(select(IntegrationSecurityAudit)).scalar_one()
        self.assertEqual(audit.event_type, "login_rejected")
        self.assertEqual(audit.summary_code, "transport_configuration_invalid")
        self.assertIsNone(audit.source_digest)

    def test_malformed_trusted_forwarding_returns_503_before_scrypt(self):
        with (
            self._client(scheme="http", peer="10.20.0.5") as client,
            patch("integrations.admin_auth.verify_admin_password") as verify,
        ):
            response = self._login(
                client,
                self.password,
                headers={"X-Forwarded-For": "not-an-ip"},
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {"detail": "Integration trusted proxy configuration is invalid"},
        )
        verify.assert_not_called()
        with self.Session() as session:
            audit = session.execute(select(IntegrationSecurityAudit)).scalar_one()
        self.assertEqual(audit.event_type, "login_rejected")
        self.assertEqual(audit.details, {"reason": "transport_configuration_invalid"})
        self.assertIsNone(audit.source_digest)
        self.assertNotIn("not-an-ip", json.dumps(audit.details))

    def test_not_configured_login_is_audited_without_password_work(self):
        with (
            self._client() as client,
            patch(
                "routers.integrations.load_integration_settings",
                return_value=load_integration_settings({}),
            ),
            patch("integrations.admin_auth.verify_admin_password") as verify,
        ):
            response = self._login(client, "must-not-be-hashed")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {"detail": "Integration administrator login is not configured"},
        )
        verify.assert_not_called()
        with self.Session() as session:
            audit = session.execute(select(IntegrationSecurityAudit)).scalar_one()
        self.assertEqual(audit.event_type, "login_rejected")
        self.assertEqual(audit.summary_code, "login_not_configured")
        self.assertEqual(audit.details, {"reason": "login_not_configured"})
        self.assertIsNone(audit.source_digest)

    def test_fifth_failure_persists_a_fifteen_minute_lock_and_skips_scrypt_when_locked(self):
        with self._client() as client:
            responses = [
                self._login(client, "wrong-task-seven-password") for _ in range(5)
            ]
            with patch("integrations.admin_auth.verify_admin_password") as verify:
                locked = self._login(client, self.password)

        self.assertEqual([response.status_code for response in responses[:4]], [401] * 4)
        self.assertEqual(responses[4].status_code, 429)
        self.assertEqual(locked.status_code, 429)
        self.assertIsInstance(locked.json()["retry_after_seconds"], int)
        self.assertGreater(locked.json()["retry_after_seconds"], 0)
        self.assertLessEqual(locked.json()["retry_after_seconds"], 900)
        verify.assert_not_called()

        with self.Session() as session:
            throttle = session.execute(select(IntegrationLoginThrottle)).scalar_one()
            audits = session.execute(
                select(IntegrationSecurityAudit).order_by(IntegrationSecurityAudit.id)
            ).scalars().all()
        self.assertEqual(throttle.failure_count, 5)
        self.assertIsNotNone(throttle.locked_until)
        self.assertEqual(len(audits), 6)
        self.assertEqual(audits[-1].event_type, "login_locked")

    def test_success_resets_throttle_and_all_login_outcomes_are_sanitized(self):
        wrong_password = "wrong-password-must-never-be-stored"
        with self._client(peer="198.51.100.90") as client:
            failed = self._login(client, wrong_password)
            succeeded = self._login(client, self.password)

        self.assertEqual(failed.status_code, 401)
        self.assertEqual(succeeded.status_code, 200)
        with self.Session() as session:
            throttle = session.execute(select(IntegrationLoginThrottle)).scalar_one()
            audits = session.execute(
                select(IntegrationSecurityAudit).order_by(IntegrationSecurityAudit.id)
            ).scalars().all()
        self.assertEqual(throttle.failure_count, 0)
        self.assertIsNone(throttle.locked_until)
        self.assertEqual(
            [audit.event_type for audit in audits],
            ["login_failed", "login_succeeded"],
        )
        self.assertIsNotNone(audits[1].session_digest)
        self.assertEqual(len(audits[1].session_digest), 64)
        persisted = json.dumps(
            [
                {
                    "event_type": audit.event_type,
                    "outcome": audit.outcome,
                    "source_digest": audit.source_digest,
                    "session_digest": audit.session_digest,
                    "summary_code": audit.summary_code,
                    "details": audit.details,
                }
                for audit in audits
            ],
            sort_keys=True,
        )
        for sentinel in (
            wrong_password,
            self.password,
            self.password_hash,
            "198.51.100.90",
            succeeded.cookies.get("facai_integrations_session", "missing-cookie"),
        ):
            self.assertNotIn(sentinel, persisted)

    def test_expired_rolling_window_resets_before_counting_a_new_failure(self):
        now = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)
        context = LoginRequestContext(
            client_ip=ipaddress.ip_address("198.51.100.91"),
            effective_scheme="https",
            peer_is_trusted_proxy=False,
        )
        source_digest = derive_login_source_digest(
            session_secret=SESSION_SECRET,
            client_ip=context.client_ip,
        )
        with self.Session() as session:
            session.add(
                IntegrationLoginThrottle(
                    source_digest=source_digest,
                    failure_count=4,
                    window_started_at=now - timedelta(minutes=15, seconds=1),
                    locked_until=None,
                    updated_at=now - timedelta(minutes=15, seconds=1),
                )
            )
            session.commit()

            result = authenticate_admin_login(
                session,
                password="wrong-password",
                encoded_password_hash=self.password_hash,
                session_secret=SESSION_SECRET,
                context=context,
                now=now,
            )
            throttle = session.execute(select(IntegrationLoginThrottle)).scalar_one()
            audit = session.execute(select(IntegrationSecurityAudit)).scalar_one()

        self.assertEqual(result.status_code, 401)
        self.assertEqual(throttle.failure_count, 1)
        self.assertEqual(throttle.window_started_at, now)
        self.assertIsNone(throttle.locked_until)
        self.assertEqual(audit.details, {"attempt_count": 1})

    def test_two_clients_behind_one_proxy_receive_independent_persistent_counters(self):
        with self._client(scheme="http", peer="10.20.0.5") as client:
            for address in ("198.51.100.101", "198.51.100.102"):
                response = self._login(
                    client,
                    "wrong-password",
                    headers={
                        "X-Forwarded-For": address,
                        "X-Forwarded-Proto": "https",
                    },
                )
                self.assertEqual(response.status_code, 401)

        with self.Session() as session:
            throttles = session.execute(
                select(IntegrationLoginThrottle).order_by(
                    IntegrationLoginThrottle.source_digest
                )
            ).scalars().all()
        self.assertEqual(len(throttles), 2)
        self.assertEqual([item.failure_count for item in throttles], [1, 1])
        self.assertNotEqual(throttles[0].source_digest, throttles[1].source_digest)

    def test_concurrent_first_attempts_create_one_row_without_lost_failures(self):
        def attempt() -> int:
            with self._client(peer="198.51.100.111") as client:
                return self._login(client, "wrong-password").status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(executor.map(lambda _index: attempt(), range(2)))

        self.assertEqual(statuses, [401, 401])
        with self.Session() as session:
            throttles = session.execute(select(IntegrationLoginThrottle)).scalars().all()
        self.assertEqual(len(throttles), 1)
        self.assertEqual(throttles[0].failure_count, 2)


if __name__ == "__main__":
    unittest.main()
