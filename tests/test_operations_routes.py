import os
import re
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from starlette.requests import Request

from database import get_db
from integrations.types import ConnectionStatus, Provider
from main import app
from services import security


ADMIN_TOKEN = "admin-" + "a" * 48
OPERATOR_TOKEN = "operator-" + "b" * 48
VIEWER_TOKEN = "viewer-" + "c" * 48


@contextmanager
def configured_auth():
    updates = {
        "FACAI_AUTH_ENABLED": "1",
        "FACAI_ADMIN_TOKEN": ADMIN_TOKEN,
        "FACAI_OPERATOR_TOKEN": OPERATOR_TOKEN,
        "FACAI_VIEWER_TOKEN": VIEWER_TOKEN,
    }
    original = {key: os.environ.get(key) for key in updates}
    os.environ.update(updates)
    try:
        yield
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class _Rows:
    def all(self):
        return [
            SimpleNamespace(
                id=17,
                provider=Provider.DOUDIAN,
                display_name="抖店旗舰店",
                status=ConnectionStatus.ACTIVE,
                access_token_ciphertext="must-not-appear",
            )
        ]


class _FilterDatabase:
    def execute(self, _statement):
        return _Rows()


class OperationsPageRouteTests(unittest.TestCase):
    def test_operations_page_requires_system_login_and_normalizes_invalid_tab(self):
        with configured_auth():
            client = TestClient(app)
            anonymous = client.get("/app/operations", follow_redirects=False)
            viewer = client.get(
                "/app/operations?tab=not-a-tab",
                headers=auth_header(VIEWER_TOKEN),
            )

        self.assertEqual(anonymous.status_code, 303)
        self.assertIn("/app/login", anonymous.headers["location"])
        self.assertEqual(viewer.status_code, 200)
        self.assertIn("运营数据中台", viewer.text)
        self.assertIn('data-active-tab="overview"', viewer.text)

    def test_legacy_data_tabs_redirect_to_operations_before_integration_login(self):
        expected = {
            "overview": "overview",
            "orders": "orders",
            "products": "products",
            "refunds": "refunds",
            "ads": "ads",
            "sync-runs": "sync-runs",
        }
        with configured_auth():
            client = TestClient(app)
            for legacy_tab, operations_tab in expected.items():
                with self.subTest(tab=legacy_tab):
                    response = client.get(
                        "/app/api-connections",
                        params={"tab": legacy_tab},
                        headers=auth_header(VIEWER_TOKEN),
                        follow_redirects=False,
                    )
                    self.assertEqual(response.status_code, 303)
                    self.assertEqual(
                        response.headers["location"],
                        f"/app/operations?tab={operations_tab}",
                    )


class OperationsPermissionTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_viewer_reads_operations_but_export_and_links_require_operator(self):
        app.dependency_overrides[get_db] = lambda: object()
        with configured_auth(), patch(
            "routers.integrations.overview",
            return_value={"summary": "ok"},
        ):
            viewer_read = self.client.get(
                "/api/operations/overview",
                headers=auth_header(VIEWER_TOKEN),
            )
            viewer_export = self.client.post(
                "/api/operations/exports",
                headers=auth_header(VIEWER_TOKEN),
                json={},
            )
            operator_export = self.client.post(
                "/api/operations/exports",
                headers=auth_header(OPERATOR_TOKEN),
                json={},
            )
            operator_unlink = self.client.delete(
                "/api/operations/products/1/link",
                headers=auth_header(OPERATOR_TOKEN),
            )

        self.assertEqual(viewer_read.status_code, 200)
        self.assertEqual(viewer_read.json(), {"summary": "ok"})
        self.assertEqual(viewer_export.status_code, 403)
        self.assertEqual(operator_export.status_code, 422)
        self.assertNotIn(operator_unlink.status_code, {401, 403})

    def test_integration_password_remains_authoritative_for_every_system_role(self):
        app.dependency_overrides[get_db] = lambda: object()
        with configured_auth():
            response = self.client.post(
                "/api/integrations/connections/1/sync",
                headers=auth_header(VIEWER_TOKEN),
                json={},
            )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json(),
            {"detail": "Integration administrator session required"},
        )

    def test_filter_options_return_only_platform_and_connection_identity(self):
        app.dependency_overrides[get_db] = lambda: _FilterDatabase()
        with configured_auth():
            response = self.client.get(
                "/api/operations/filter-options",
                headers=auth_header(VIEWER_TOKEN),
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            [item["key"] for item in payload["providers"]],
            ["qianchuan", "doudian", "taobao", "pdd"],
        )
        self.assertEqual(
            payload["connections"],
            [
                {
                    "id": 17,
                    "provider": "doudian",
                    "name": "抖店旗舰店",
                    "status": "active",
                }
            ],
        )
        encoded = repr(payload).lower()
        for forbidden in ("token", "ciphertext", "scope", "expires"):
            self.assertNotIn(forbidden, encoded)

    def test_unpublished_integration_data_and_export_aliases_are_absent(self):
        registered_paths = set()
        for route in app.routes:
            if hasattr(route, "path"):
                registered_paths.add(route.path)
                continue
            original_router = getattr(route, "original_router", None)
            context = getattr(route, "include_context", None)
            if original_router is None or context is None:
                continue
            registered_paths.update(
                f"{context.prefix}{child.path}"
                for child in original_router.routes
                if hasattr(child, "path")
            )
        for path in (
            "/api/integrations/data/overview",
            "/api/integrations/data/orders",
            "/api/integrations/data/products",
            "/api/integrations/data/refunds",
            "/api/integrations/data/ad-entities",
            "/api/integrations/data/ad-metrics",
            "/api/integrations/exports",
            "/api/integrations/exports/{public_id}",
            "/api/integrations/exports/{public_id}/download",
            "/api/integrations/data/products/{commerce_product_id}/link",
        ):
            with self.subTest(path=path):
                self.assertNotIn(path, registered_paths)

    def test_operations_interface_is_complete_and_sync_retry_stays_admin_only(self):
        registered_paths = set()
        for route in app.routes:
            if hasattr(route, "path"):
                registered_paths.add(route.path)
                continue
            original_router = getattr(route, "original_router", None)
            context = getattr(route, "include_context", None)
            if original_router is None or context is None:
                continue
            registered_paths.update(
                f"{context.prefix}{child.path}"
                for child in original_router.routes
                if hasattr(child, "path")
            )

        required = {
            "/api/operations/filter-options",
            "/api/operations/overview",
            "/api/operations/orders",
            "/api/operations/products",
            "/api/operations/refunds",
            "/api/operations/ad-entities",
            "/api/operations/ad-metrics",
            "/api/operations/sync-runs",
            "/api/operations/exports",
            "/api/operations/exports/{public_id}",
            "/api/operations/exports/{public_id}/download",
            "/api/operations/products/{commerce_product_id}/link",
        }
        self.assertTrue(required.issubset(registered_paths))
        self.assertNotIn(
            "/api/operations/sync-runs/{run_id}/retry",
            registered_paths,
        )
        self.assertIn(
            "/api/integrations/sync-runs/{run_id}/retry",
            registered_paths,
        )

    def test_actor_digest_is_stable_irreversible_and_credential_scoped(self):
        digest_request = getattr(security, "request_actor_digest", None)
        self.assertTrue(callable(digest_request))

        def request_for(token: str) -> Request:
            return Request(
                {
                    "type": "http",
                    "method": "GET",
                    "path": "/api/operations/overview",
                    "query_string": b"",
                    "headers": [
                        (b"authorization", f"Bearer {token}".encode("ascii"))
                    ],
                    "scheme": "http",
                    "server": ("testserver", 80),
                    "client": ("127.0.0.1", 50000),
                }
            )

        with configured_auth():
            first = digest_request(request_for(OPERATOR_TOKEN))
            repeated = digest_request(request_for(OPERATOR_TOKEN))
            different = digest_request(request_for(ADMIN_TOKEN))
            operator_session = security.create_session_token(
                security.Principal(
                    name="operator",
                    role="operator",
                    auth_source="token",
                )
            )
            session_request = Request(
                {
                    "type": "http",
                    "method": "GET",
                    "path": "/api/operations/overview",
                    "query_string": b"",
                    "headers": [
                        (
                            b"cookie",
                            (
                                f"{security.AUTH_COOKIE_NAME}="
                                f"{operator_session}"
                            ).encode("ascii"),
                        )
                    ],
                    "scheme": "http",
                    "server": ("testserver", 80),
                    "client": ("127.0.0.1", 50000),
                }
            )
            from_session = digest_request(session_request)

        self.assertRegex(first, r"^[0-9a-f]{64}$")
        self.assertEqual(first, repeated)
        self.assertEqual(first, from_session)
        self.assertNotEqual(first, different)
        self.assertNotIn(OPERATOR_TOKEN, first)

    def test_export_owner_is_bound_to_the_system_login_credential(self):
        class ExportDatabase:
            def commit(self):
                return None

            def rollback(self):
                return None

        database = ExportDatabase()
        app.dependency_overrides[get_db] = lambda: database
        captured: list[str] = []
        job = SimpleNamespace(
            public_id="019f-export-owner",
            requester_session_digest="",
        )

        def create_job(_db, *, requester_session_digest, request, now):
            captured.append(requester_session_digest)
            job.requester_session_digest = requester_session_digest
            return job

        def export_view(selected, *, now):
            return {
                "id": selected.public_id,
                "status": "ready",
                "download_url": (
                    f"/api/integrations/exports/"
                    f"{selected.public_id}/download"
                ),
            }

        payload = {
            "resource_type": "orders",
            "format": "csv",
            "filters": {
                "connection_id": 17,
                "date_from": "2026-07-13",
                "date_to": "2026-07-13",
            },
        }
        with (
            configured_auth(),
            patch("routers.integrations.create_export_job", side_effect=create_job),
            patch("routers.integrations.get_export_job", return_value=job),
            patch("routers.integrations.export_job_view", side_effect=export_view),
        ):
            created = self.client.post(
                "/api/operations/exports",
                headers=auth_header(OPERATOR_TOKEN),
                json=payload,
            )
            owner_poll = self.client.get(
                f"/api/operations/exports/{job.public_id}",
                headers=auth_header(OPERATOR_TOKEN),
            )
            other_poll = self.client.get(
                f"/api/operations/exports/{job.public_id}",
                headers=auth_header(ADMIN_TOKEN),
            )

        self.assertEqual(created.status_code, 202)
        self.assertEqual(owner_poll.status_code, 200)
        self.assertEqual(other_poll.status_code, 404)
        self.assertEqual(
            owner_poll.json()["download_url"],
            f"/api/operations/exports/{job.public_id}/download",
        )
        self.assertEqual(len(captured), 1)
        self.assertRegex(captured[0], r"^[0-9a-f]{64}$")
        self.assertNotIn(OPERATOR_TOKEN, captured[0])

    def test_operator_links_and_unlinks_products_without_integration_session(self):
        commerce_product = SimpleNamespace(id=7, provider=Provider.DOUDIAN)
        internal_product = SimpleNamespace(id=9)

        class LinkDatabase:
            def __init__(self):
                self.scalar_results = [commerce_product, internal_product]
                self.statements = []

            def scalar(self, _statement):
                return self.scalar_results.pop(0)

            def execute(self, statement):
                self.statements.append(statement)

            def commit(self):
                return None

            def rollback(self):
                return None

        class InsertBuilder:
            def __init__(self):
                self.values_payload = None

            def values(self, **payload):
                self.values_payload = payload
                return self

            def on_conflict_do_update(self, **_kwargs):
                return self

        database = LinkDatabase()
        insert_builder = InsertBuilder()
        app.dependency_overrides[get_db] = lambda: database
        with (
            configured_auth(),
            patch("routers.integrations.postgres_insert", return_value=insert_builder),
            patch("routers.integrations.write_security_audit") as integration_audit,
            patch("main.record_request_audit") as global_audit,
        ):
            linked = self.client.put(
                "/api/operations/products/7/link",
                headers=auth_header(OPERATOR_TOKEN),
                json={"product_id": 9},
            )
            database.scalar_results = [commerce_product]
            unlinked = self.client.delete(
                "/api/operations/products/7/link",
                headers=auth_header(OPERATOR_TOKEN),
            )

        self.assertEqual(linked.status_code, 200)
        self.assertEqual(linked.json(), {"commerce_product_id": 7, "product_id": 9, "linked": True})
        self.assertEqual(unlinked.status_code, 200)
        self.assertEqual(unlinked.json(), {"commerce_product_id": 7, "linked": False})
        self.assertRegex(
            insert_builder.values_payload["linked_by_session_digest"],
            r"^[0-9a-f]{64}$",
        )
        integration_audit.assert_not_called()
        audited_paths = [call.kwargs["path"] for call in global_audit.call_args_list]
        self.assertIn("/api/operations/products/7/link", audited_paths)


if __name__ == "__main__":
    unittest.main()
