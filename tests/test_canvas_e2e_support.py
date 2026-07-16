from __future__ import annotations

import importlib
import importlib.util
import subprocess
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROVIDER_KEY_ENV_ALIASES = (
    "DEEPSEEK_API_KEY",
    "ARK_API_KEY",
    "DOUBAO_API_KEY",
    "MINIMAX_API_KEY",
    "GLM_API_KEY",
    "ZAI_API_KEY",
    "QWEN_API_KEY",
    "DASHSCOPE_API_KEY",
    "EMBEDDING_API_KEY",
)


def _load_canvas_processors():
    spec = importlib.util.find_spec("tests.fakes.canvas_processors")
    if spec is None:
        raise AssertionError("tests.fakes.canvas_processors must exist")
    return importlib.import_module("tests.fakes.canvas_processors")


def _opaque_product(*, sentinel: tuple[int, int, int] | None = None) -> Image.Image:
    image = Image.new("RGB", (6, 6), sentinel or (255, 255, 255))
    for y in range(1, 5):
        for x in range(1, 5):
            image.putpixel((x, y), (24 + x, 80 + y, 160))
    return image


class CanvasProcessorFakeTests(unittest.TestCase):
    def test_masker_is_deterministic_and_audits_calls_by_input_digest(self):
        processors = _load_canvas_processors()
        masker = processors.FakeMasker()
        image = _opaque_product()

        first = masker.create_mask(image)
        second = masker.create_mask(image.copy())
        digest = masker.input_digest(image)

        self.assertEqual("L", first.mode)
        self.assertEqual(first.tobytes(), second.tobytes())
        self.assertEqual(
            {
                "totalCalls": 2,
                "callsByDigest": {digest: 2},
            },
            masker.audit_snapshot(),
        )

    def test_fail_once_sentinel_retries_successfully_for_the_same_digest(self):
        processors = _load_canvas_processors()
        masker = processors.FakeMasker()
        image = _opaque_product(sentinel=processors.FAIL_ONCE_SENTINEL_RGB)
        digest = masker.input_digest(image)

        with self.assertRaises(processors.FakeMaskerFirstAttemptError):
            masker.create_mask(image)
        mask = masker.create_mask(image)

        self.assertEqual(image.size, mask.size)
        self.assertEqual(
            {"totalCalls": 2, "callsByDigest": {digest: 2}},
            masker.audit_snapshot(),
        )

    def test_masker_call_accounting_is_thread_safe(self):
        processors = _load_canvas_processors()
        masker = processors.FakeMasker()
        image = _opaque_product()
        digest = masker.input_digest(image)

        with ThreadPoolExecutor(max_workers=8) as pool:
            masks = list(pool.map(lambda _: masker.create_mask(image), range(32)))

        self.assertEqual(1, len({mask.tobytes() for mask in masks}))
        self.assertEqual(
            {"totalCalls": 32, "callsByDigest": {digest: 32}},
            masker.audit_snapshot(),
        )


class CanvasProviderFakeTests(unittest.IsolatedAsyncioTestCase):
    async def test_fake_provider_returns_deterministic_local_bytes_and_audits_submits(self):
        from services.canvas.provider_schemas import ProviderGenerationRequest
        from tests.fakes.canvas_provider import FakeCanvasProvider

        provider = FakeCanvasProvider()
        request = ProviderGenerationRequest(
            prompt="clean product background",
            size="96x64",
            upstream_idempotency_key="canvas:test:item:1",
        )
        runtime = provider.runtime_factory()

        first = await provider.submit(request, runtime)
        second = await provider.submit(request, runtime)

        self.assertEqual("completed", first.status)
        self.assertEqual(first, second)
        self.assertIsNotNone(first.image)
        self.assertEqual(
            {
                "submitCount": 1,
                "pollCount": 0,
                "cancelCount": 0,
                "submitsByIdempotencyKey": {"canvas:test:item:1": 1},
            },
            provider.audit_snapshot(),
        )

    async def test_fake_provider_only_fails_or_marks_unknown_once_per_prompt(self):
        from services.canvas.provider_schemas import ProviderError, ProviderGenerationRequest
        from tests.fakes.canvas_provider import FakeCanvasProvider

        provider = FakeCanvasProvider()
        runtime = provider.runtime_factory()
        fail_once = ProviderGenerationRequest(
            prompt="first item [e2e:fail-once]",
            size="96x64",
            upstream_idempotency_key="canvas:test:fail-once:1",
        )
        with self.assertRaisesRegex(ProviderError, "forced this item to fail"):
            await provider.submit(fail_once, runtime)
        recovered = await provider.submit(
            replace(fail_once, upstream_idempotency_key="canvas:test:fail-once:2"),
            runtime,
        )
        self.assertEqual("completed", recovered.status)

        uncertain_once = ProviderGenerationRequest(
            prompt="first item [e2e:uncertain-once]",
            size="96x64",
            upstream_idempotency_key="canvas:test:uncertain-once:1",
        )
        with self.assertRaises(ProviderError) as caught:
            await provider.submit(uncertain_once, runtime)
        self.assertTrue(caught.exception.retryable)
        recovered_unknown = await provider.submit(
            replace(uncertain_once, upstream_idempotency_key="canvas:test:uncertain-once:2"),
            runtime,
        )
        self.assertEqual("completed", recovered_unknown.status)


class CanvasE2EServerContractTests(unittest.TestCase):
    def test_all_effective_provider_key_aliases_are_cleared_before_application_import(self):
        source = (PROJECT_ROOT / "scripts" / "e2e_server.py").read_text(encoding="utf-8")
        isolated_bootstrap = source[: source.index("import main as application")]

        for alias in PROVIDER_KEY_ENV_ALIASES:
            with self.subTest(alias=alias):
                self.assertIn(f'"{alias}": ""', isolated_bootstrap)

    def test_isolated_server_disables_the_display_only_lan_ip_probe_before_import(self):
        server_source = (PROJECT_ROOT / "scripts" / "e2e_server.py").read_text(
            encoding="utf-8"
        )
        isolated_bootstrap = server_source[: server_source.index("import main as application")]
        application_source = (PROJECT_ROOT / "main.py").read_text(encoding="utf-8")

        self.assertIn('"FACAI_SKIP_LAN_IP_PROBE": "1"', isolated_bootstrap)
        self.assertIn('os.environ.get("FACAI_SKIP_LAN_IP_PROBE") != "1"', application_source)

    def test_isolated_server_inerts_only_unrelated_vector_sync_before_application_import(self):
        server_source = (PROJECT_ROOT / "scripts" / "e2e_server.py").read_text(
            encoding="utf-8"
        )
        isolated_bootstrap = server_source[: server_source.index("import main as application")]
        application_source = (PROJECT_ROOT / "main.py").read_text(encoding="utf-8")

        self.assertIn("from services import vector_sync as isolated_vector_sync", isolated_bootstrap)
        self.assertIn("def _e2e_noop_vector_sync", isolated_bootstrap)
        self.assertIn(
            "isolated_vector_sync.start_vector_sync_worker = _e2e_noop_vector_sync",
            isolated_bootstrap,
        )
        self.assertIn(
            "isolated_vector_sync.stop_vector_sync_worker = _e2e_noop_vector_sync",
            isolated_bootstrap,
        )
        self.assertNotIn("_e2e_noop_vector_sync", application_source)
        self.assertIn("start_canvas_runtime(app, db_factory=SessionLocal)", application_source)

    def test_outbound_guard_and_runtime_audit_are_installed_before_application_import(self):
        source = (PROJECT_ROOT / "scripts" / "e2e_server.py").read_text(encoding="utf-8")
        application_index = source.index("import main as application")

        self.assertLess(source.index("\n_install_outbound_guard()\n"), application_index)
        for required in (
            '"effectiveProviderKeys"',
            '"rembgImported"',
            '"onnxruntimeImported"',
            '"modelFileCount"',
            '"modelFiles"',
            '"lifetimeExternalAttemptCount"',
            '"lifetimeExternalAttemptTargets"',
            '"scenarioExternalAttemptCount"',
            '"scenarioExternalAttemptTargets"',
        ):
            self.assertIn(required, source)

    def test_runtime_reset_preserves_lifetime_outbound_evidence(self):
        source = (PROJECT_ROOT / "scripts" / "e2e_server.py").read_text(encoding="utf-8")
        record_start = source.index("def _record_blocked_outbound")
        record_end = source.index("\ndef _install_outbound_guard", record_start)
        record_source = source[record_start:record_end]
        reset_start = source.index("def reset_runtime_audit")
        reset_end = source.index("\n\n@application.app", reset_start)
        reset_source = source[reset_start:reset_end]

        self.assertIn("_LIFETIME_OUTBOUND_ATTEMPTS.append", record_source)
        self.assertIn("_SCENARIO_OUTBOUND_ATTEMPTS.append", record_source)
        self.assertIn("_SCENARIO_OUTBOUND_ATTEMPTS.clear()", reset_source)
        self.assertNotIn("_LIFETIME_OUTBOUND_ATTEMPTS.clear()", reset_source)

    def test_real_nonloopback_connect_is_blocked_and_lifetime_evidence_survives_reset(self):
        probe = subprocess.run(
            [
                sys.executable,
                "-c",
                """
import socket
import scripts.e2e_server as server

lifetime_before = len(server._LIFETIME_OUTBOUND_ATTEMPTS)
scenario_before = len(server._SCENARIO_OUTBOUND_ATTEMPTS)
try:
    with socket.socket() as connection:
        connection.connect(("203.0.113.10", 443))
except OSError as exc:
    assert "isolated E2E blocked outbound connect" in str(exc), str(exc)
else:
    raise AssertionError("non-loopback connection was not blocked")

assert len(server._LIFETIME_OUTBOUND_ATTEMPTS) == lifetime_before + 1
assert len(server._SCENARIO_OUTBOUND_ATTEMPTS) == scenario_before + 1
assert server._LIFETIME_OUTBOUND_ATTEMPTS[-1]["target"] == "203.0.113.10:443"
assert server._SCENARIO_OUTBOUND_ATTEMPTS[-1]["target"] == "203.0.113.10:443"

class Client:
    host = "127.0.0.1"

class LoopbackRequest:
    client = Client()

server.reset_runtime_audit(LoopbackRequest())
audit = server.runtime_audit(LoopbackRequest())
assert audit["network"]["lifetimeExternalAttemptCount"] == lifetime_before + 1
assert audit["network"]["lifetimeExternalAttemptTargets"][-1] == "203.0.113.10:443"
assert audit["network"]["scenarioExternalAttemptCount"] == 0
assert audit["network"]["scenarioExternalAttemptTargets"] == []
""",
            ],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )

        self.assertEqual(
            0,
            probe.returncode,
            msg=f"stdout:\n{probe.stdout}\nstderr:\n{probe.stderr}",
        )

    def test_server_imports_application_after_isolation_and_runs_exact_app_object(self):
        source = (PROJECT_ROOT / "scripts" / "e2e_server.py").read_text(encoding="utf-8")

        for required in (
            "import main as application",
            "configure_canvas_test_runtime(",
            "uvicorn.run(application.app",
        ):
            self.assertIn(required, source)
        environment_index = source.index('"CANVAS_DATA_DIR"')
        application_index = source.index("import main as application")
        configuration_index = source.index("configure_canvas_test_runtime(")
        uvicorn_index = source.index("uvicorn.run(application.app")

        self.assertLess(environment_index, application_index)
        self.assertLess(application_index, configuration_index)
        self.assertLess(configuration_index, uvicorn_index)
        self.assertNotIn('uvicorn.run("main:app"', source)
        self.assertIn("masker_factory=", source)
        self.assertIn("compose_runner=", source)

    def test_control_plane_is_e2e_only_and_contains_required_routes(self):
        source = (PROJECT_ROOT / "scripts" / "e2e_server.py").read_text(encoding="utf-8")
        production_sources = "\n".join(
            path.read_text(encoding="utf-8")
            for path in [
                PROJECT_ROOT / "main.py",
                *(PROJECT_ROOT / "routers" / "canvas").glob("*.py"),
            ]
        )

        self.assertIn("/_e2e/runtime-audit", source)
        self.assertIn("/_e2e/projects/{project_id}/events/prune-through", source)
        self.assertIn("/_e2e/projects/{project_id}/events/disconnect", source)
        self.assertIn("/_e2e/projects/{project_id}/seed-background", source)
        self.assertIn("/_e2e/runtime/capacity", source)
        self.assertIn("127.0.0.1", source)
        self.assertNotIn("/_e2e/", production_sources)

    def test_project_deletion_retries_only_windows_sharing_violations(self):
        source = (PROJECT_ROOT / "scripts" / "e2e_server.py").read_text(encoding="utf-8")

        for required in (
            "_retrying_finalize_deleting_project",
            "isinstance(cause, PermissionError)",
            'getattr(cause, "winerror", None) == 32',
            "raise",
            "canvas_projects.finalize_deleting_project =",
        ):
            self.assertIn(required, source)


if __name__ == "__main__":
    unittest.main()
