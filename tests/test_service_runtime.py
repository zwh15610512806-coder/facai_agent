import importlib.util
import logging
import os
import runpy
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from main import app

ROOT = Path(__file__).resolve().parents[1]


def _load_watchdog_module():
    path = ROOT / "scripts" / "facai_agent_service.py"
    spec = importlib.util.spec_from_file_location("facai_agent_service_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class HealthEndpointTests(unittest.TestCase):
    def test_healthz_is_process_liveness_only(self):
        with TestClient(app) as client:
            response = client.get("/healthz")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_readyz_reports_database_search_vector_worker_and_disk(self):
        from routers import search_local

        ready_state = dict(search_local._state)
        ready_state.update({
            "is_indexing": False,
            "last_indexed": datetime.now().replace(microsecond=0).isoformat(),
            "total_files": 1,
            "last_error": "",
        })
        with (
            patch.dict(os.environ, {"FACAI_AUTH_ENABLED": "0"}),
            patch.object(search_local, "_loaded", True),
            patch.object(search_local, "_state", ready_state),
            TestClient(app) as client,
        ):
            response = client.get("/readyz")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ready")
        for key in ("database", "search_index", "vector", "worker", "disk"):
            self.assertIn(key, payload["checks"])


class ManagedServiceTests(unittest.TestCase):
    def test_integration_worker_is_disabled_by_default_and_not_in_fastapi_lifespan(self):
        service = _load_watchdog_module()
        main_source = (ROOT / "main.py").read_text(encoding="utf-8-sig")

        self.assertFalse(service.integration_worker_enabled({}))
        self.assertFalse(
            service.integration_worker_enabled(
                {"FACAI_INTEGRATION_WORKER_ENABLED": "0"}
            )
        )
        self.assertNotIn("integration_worker", main_source)

        state = service.WorkerSupervisorState()
        with patch.object(service, "start_integration_worker") as start_worker:
            selected, status = service.supervise_worker_once(
                state,
                enabled=False,
                now=100.0,
            )

        self.assertEqual(status, "disabled")
        self.assertIsNone(selected.process)
        start_worker.assert_not_called()

    def test_integration_worker_starts_as_a_separate_hidden_child(self):
        service = _load_watchdog_module()
        process = Mock(pid=43210)

        with (
            patch.object(service.subprocess, "Popen", return_value=process) as popen,
            patch.object(service, "_record_worker_pid") as record_pid,
        ):
            selected = service.start_integration_worker()

        self.assertIs(selected, process)
        command = popen.call_args.args[0]
        self.assertEqual(Path(command[1]).name, "integration_worker.py")
        self.assertNotIn("facai_server.py", command)
        self.assertEqual(
            popen.call_args.kwargs["creationflags"],
            service.subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        record_pid.assert_called_once_with(43210)

    def test_worker_restart_uses_bounded_backoff_without_touching_server_child(self):
        service = _load_watchdog_module()
        dead_worker = Mock(pid=1234)
        dead_worker.poll.return_value = 1
        server = Mock(pid=9876)
        state = service.WorkerSupervisorState(process=dead_worker)

        with (
            patch.object(service, "start_integration_worker") as start_worker,
            patch.object(service, "stop_managed_process") as stop_server,
        ):
            delayed, status = service.supervise_worker_once(
                state,
                enabled=True,
                now=100.0,
            )
            waiting, waiting_status = service.supervise_worker_once(
                delayed,
                enabled=True,
                now=100.5,
            )
            replacement = Mock(pid=2222)
            start_worker.return_value = replacement
            restarted, restarted_status = service.supervise_worker_once(
                waiting,
                enabled=True,
                now=waiting.next_restart_at,
            )

        self.assertEqual(status, "backoff")
        self.assertEqual(waiting_status, "backoff")
        self.assertEqual(delayed.restart_attempts, 1)
        self.assertGreaterEqual(delayed.next_restart_at, 101.0)
        self.assertLessEqual(delayed.next_restart_at, 160.0)
        self.assertEqual(restarted_status, "started")
        self.assertIs(restarted.process, replacement)
        start_worker.assert_called_once_with()
        stop_server.assert_not_called()
        self.assertIsNotNone(server)

    def test_worker_enablement_defaults_off_and_batch_starts_only_the_supervisor(self):
        env_example = (ROOT / ".env.example").read_text(encoding="utf-8-sig")
        batch_source = (
            ROOT / "scripts" / "start-facai-agent-service.cmd"
        ).read_text(encoding="utf-8-sig")

        self.assertEqual(
            env_example.count("FACAI_INTEGRATION_WORKER_ENABLED=0"),
            1,
        )
        self.assertIn("set \"PYTHONUTF8=1\"", batch_source)
        self.assertIn("facai_agent_service.py", batch_source)
        self.assertNotIn("integration_worker.py", batch_source)

    def test_worker_start_failure_enters_safe_backoff_without_exposing_raw_error(self):
        service = _load_watchdog_module()
        state = service.WorkerSupervisorState()

        with (
            patch.object(
                service,
                "start_integration_worker",
                side_effect=OSError("access_token=test-supervisor-secret"),
            ),
            self.assertLogs("facai.watchdog", level="ERROR") as captured,
        ):
            selected, status = service.supervise_worker_once(
                state,
                enabled=True,
                now=100.0,
            )

        rendered = "\n".join(captured.output)
        self.assertEqual(status, "backoff")
        self.assertIsNone(selected.process)
        self.assertEqual(selected.restart_attempts, 1)
        self.assertGreater(selected.next_restart_at, 100.0)
        self.assertNotIn("test-supervisor-secret", rendered)

    def test_worker_pid_record_failure_terminates_the_unowned_child(self):
        service = _load_watchdog_module()
        process = Mock(pid=43210)

        with (
            patch.object(service.subprocess, "Popen", return_value=process),
            patch.object(
                service,
                "_record_worker_pid",
                side_effect=OSError("pid file unavailable"),
            ),
            self.assertRaises(OSError),
        ):
            service.start_integration_worker()

        process.terminate.assert_called_once_with()
        process.wait.assert_called_once_with(timeout=5)

    def test_invalid_runtime_enablement_stops_an_already_managed_worker(self):
        service = _load_watchdog_module()
        server = Mock(pid=8001)
        worker_process = Mock(pid=9001)

        def supervise_worker(state, *, enabled, now=None):
            if enabled:
                return (
                    service.WorkerSupervisorState(process=worker_process),
                    "started",
                )
            return service.WorkerSupervisorState(), "disabled"

        with (
            patch.object(sys, "argv", ["facai_agent_service.py", "--interval", "1"]),
            patch.object(service, "assert_verified_runtime"),
            patch.object(
                service,
                "supervise_once",
                return_value=(server, "managed-healthy"),
            ),
            patch.object(
                service,
                "integration_worker_enabled",
                side_effect=[True, ValueError("ambiguous")],
            ),
            patch.object(
                service,
                "supervise_worker_once",
                side_effect=supervise_worker,
            ) as supervise_worker_call,
            patch.object(service.time, "sleep", side_effect=[None, KeyboardInterrupt]),
            patch.object(service, "stop_managed_process"),
            patch.object(service, "stop_integration_worker"),
            patch.object(service, "log"),
        ):
            result = service.main()

        self.assertEqual(result, 0)
        self.assertEqual(supervise_worker_call.call_count, 2)
        self.assertTrue(supervise_worker_call.call_args_list[0].kwargs["enabled"])
        self.assertFalse(supervise_worker_call.call_args_list[1].kwargs["enabled"])

    def test_managed_uvicorn_disables_automatic_proxy_header_rewriting(self):
        import scripts.facai_server as server

        with (
            patch.object(server, "configure_runtime_logging"),
            patch.object(server, "assert_verified_runtime"),
            patch.object(server, "assert_startup_security"),
            patch("uvicorn.run") as run,
            patch.object(sys, "argv", ["facai_server.py", "--port", "8765"]),
        ):
            result = server.main()

        self.assertEqual(result, 0)
        self.assertEqual(run.call_args.kwargs["proxy_headers"], False)
        self.assertEqual(run.call_args.kwargs["forwarded_allow_ips"], "")

    def test_direct_main_uvicorn_disables_automatic_proxy_header_rewriting(self):
        with (
            patch("scripts.verify_runtime.assert_verified_runtime"),
            patch("services.security.assert_startup_security"),
            patch("uvicorn.run") as run,
        ):
            runpy.run_path(str(ROOT / "main.py"), run_name="__main__")

        self.assertEqual(run.call_args.kwargs["proxy_headers"], False)
        self.assertEqual(run.call_args.kwargs["forwarded_allow_ips"], "")
    def test_project_environment_is_loaded_before_service_security_checks(self):
        from scripts.runtime_environment import load_project_environment

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".env").write_text(
                "FACAI_AUTH_ENABLED=1\nFACAI_ADMIN_TOKEN=loaded-from-project-env\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=False):
                original_enabled = os.environ.pop("FACAI_AUTH_ENABLED", None)
                original_token = os.environ.pop("FACAI_ADMIN_TOKEN", None)
                try:
                    load_project_environment(root)
                    self.assertEqual(os.environ["FACAI_AUTH_ENABLED"], "1")
                    self.assertEqual(
                        os.environ["FACAI_ADMIN_TOKEN"],
                        "loaded-from-project-env",
                    )
                finally:
                    if original_enabled is None:
                        os.environ.pop("FACAI_AUTH_ENABLED", None)
                    else:
                        os.environ["FACAI_AUTH_ENABLED"] = original_enabled
                    if original_token is None:
                        os.environ.pop("FACAI_ADMIN_TOKEN", None)
                    else:
                        os.environ["FACAI_ADMIN_TOKEN"] = original_token

    def test_unmanaged_occupied_port_is_reported_without_starting_or_killing(self):
        service = _load_watchdog_module()

        with (
            patch.object(service, "healthy", return_value=False),
            patch.object(service, "port_available", return_value=False),
            patch.object(service, "start_server") as start_server,
        ):
            process, state = service.supervise_once(None, 8001)

        self.assertIsNone(process)
        self.assertEqual(state, "port-occupied")
        start_server.assert_not_called()

    def test_watchdog_source_never_force_kills_port_owners(self):
        source = (ROOT / "scripts" / "facai_agent_service.py").read_text(encoding="utf-8-sig")

        self.assertNotIn("Stop-Process", source)
        self.assertNotIn("stop_port_listeners", source)
        self.assertIn("facai-agent-server.pid", source)

    def test_runtime_logging_uses_10mb_with_five_backups(self):
        from services.runtime_logging import build_rotating_handler

        with tempfile.TemporaryDirectory() as temp_dir:
            handler = build_rotating_handler(Path(temp_dir) / "runtime.log")
            try:
                self.assertEqual(handler.maxBytes, 10 * 1024 * 1024)
                self.assertEqual(handler.backupCount, 5)
            finally:
                handler.close()

    def test_runtime_access_logging_redacts_oauth_query_secrets_before_formatting(self):
        from services.runtime_logging import build_rotating_handler

        sentinels = (
            "test-authorization-code",
            "test-state-value",
            "test-access-token",
            "test-refresh-token",
            "test-sign-value",
            "test-signature-value",
            "test-percent-encoded-key-value",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "runtime.log"
            handler = build_rotating_handler(path)
            logger = logging.getLogger("uvicorn.access.task6-test")
            old_handlers = list(logger.handlers)
            old_propagate = logger.propagate
            old_level = logger.level
            logger.handlers[:] = [handler]
            logger.propagate = False
            logger.setLevel(logging.INFO)
            try:
                logger.info(
                    '%s - "%s %s HTTP/%s" %d',
                    "127.0.0.1:12345",
                    "GET",
                    (
                        "/integrations/oauth/callback/doudian?"
                        "code=test-authorization-code&state=test-state-value&"
                        "access_token=test-access-token&refresh_token=test-refresh-token&"
                        "sign=test-sign-value&signature=test-signature-value&request_id=req-visible"
                    ),
                    "1.1",
                    303,
                )
                logger.info(
                    "callback provider=taobao path=/integrations/oauth/callback/taobao?code=test-authorization-code&request_id=req-visible-2"
                )
                logger.info(
                    "callback provider=pdd path=/integrations/oauth/callback/pdd?"
                    "access%5Ftoken=test-percent-encoded-key-value&request_id=req-visible-3"
                )
                handler.flush()
            finally:
                logger.handlers[:] = old_handlers
                logger.propagate = old_propagate
                logger.setLevel(old_level)
                handler.close()

            rendered = path.read_text(encoding="utf-8")

        self.assertIn("[REDACTED]", rendered)
        self.assertIn("/integrations/oauth/callback/doudian", rendered)
        self.assertIn("provider=taobao", rendered)
        self.assertIn("req-visible", rendered)
        self.assertIn("req-visible-2", rendered)
        self.assertIn("req-visible-3", rendered)
        for sentinel in sentinels:
            self.assertNotIn(sentinel, rendered)

    def test_oauth_query_filter_handles_mapping_args_extra_secret_keys_and_is_idempotent(self):
        from services.runtime_logging import OAuthQueryRedactionFilter, build_rotating_handler

        record = logging.LogRecord(
            name="uvicorn.access",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="%(request)s",
            args=(
                {
                    "request": (
                        "/integrations/oauth/callback/taobao?"
                        "app_secret=test-mapping-app-secret&"
                        "client_secret=test-mapping-client-secret&"
                        "authorization_code=test-mapping-authorization-code&"
                        "provider=taobao"
                    )
                },
            ),
            exc_info=None,
        )
        query_filter = OAuthQueryRedactionFilter()

        self.assertTrue(query_filter.filter(record))
        once = record.getMessage()
        self.assertTrue(query_filter.filter(record))
        twice = record.getMessage()

        self.assertEqual(once, twice)
        self.assertEqual(once.count("[REDACTED]"), 3)
        self.assertIn("provider=taobao", once)
        for sentinel in (
            "test-mapping-app-secret",
            "test-mapping-client-secret",
            "test-mapping-authorization-code",
        ):
            self.assertNotIn(sentinel, once)

        with tempfile.TemporaryDirectory() as temp_dir:
            handler = build_rotating_handler(Path(temp_dir) / "runtime.log")
            try:
                handler_filters = [
                    item
                    for item in handler.filters
                    if isinstance(item, OAuthQueryRedactionFilter)
                ]
                self.assertEqual(len(handler_filters), 1)
            finally:
                handler.close()


if __name__ == "__main__":
    unittest.main()
