import importlib.util
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
