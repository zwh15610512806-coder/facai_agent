import importlib.util
import tempfile
import unittest
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
    def test_healthz_checks_only_process_and_local_database(self):
        with TestClient(app) as client:
            response = client.get("/healthz")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "database": "ok"})


class ManagedServiceTests(unittest.TestCase):
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
