"""Configuration contracts for third-party Canvas Provider boundaries."""
from __future__ import annotations

import importlib.util
import os
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.py"
_PROVIDER_ENV_NAMES = (
    "CANVAS_PROVIDER_SECRET_KEY",
    "CANVAS_PROVIDER_ALLOWED_HOSTS",
    "CANVAS_PROVIDER_PRIVATE_ALLOWED_HOSTS",
    "CANVAS_PROVIDER_PRIVATE_ALLOWED_IPS",
    "CANVAS_ALLOW_INSECURE_PROVIDER_HTTP",
    "CANVAS_PROVIDER_CONNECT_TIMEOUT_SECONDS",
    "CANVAS_PROVIDER_TOTAL_TIMEOUT_SECONDS",
    "CANVAS_PROVIDER_MAX_JSON_BYTES",
    "CANVAS_REMOTE_IMAGE_MAX_BYTES",
)


def load_config(**overrides: str) -> object:
    environment = os.environ.copy()
    for name in _PROVIDER_ENV_NAMES:
        environment.pop(name, None)
    environment.update(overrides)
    spec = importlib.util.spec_from_file_location(
        f"_canvas_provider_config_{uuid.uuid4().hex}", CONFIG_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    with patch.dict(os.environ, environment, clear=True), patch(
        "dotenv.load_dotenv", return_value=False
    ):
        spec.loader.exec_module(module)
    return module


class CanvasProviderConfigTests(unittest.TestCase):
    def test_secure_defaults_are_explicit_and_keep_the_existing_remote_limit(self) -> None:
        config = load_config()

        self.assertEqual("", config.CANVAS_PROVIDER_SECRET_KEY)
        self.assertEqual(("ark.cn-beijing.volces.com",), config.CANVAS_PROVIDER_ALLOWED_HOSTS)
        self.assertEqual((), config.CANVAS_PROVIDER_PRIVATE_ALLOWED_HOSTS)
        self.assertEqual((), config.CANVAS_PROVIDER_PRIVATE_ALLOWED_IPS)
        self.assertFalse(config.CANVAS_ALLOW_INSECURE_PROVIDER_HTTP)
        self.assertEqual(10, config.CANVAS_PROVIDER_CONNECT_TIMEOUT_SECONDS)
        self.assertEqual(60, config.CANVAS_PROVIDER_TOTAL_TIMEOUT_SECONDS)
        self.assertEqual(1_048_576, config.CANVAS_PROVIDER_MAX_JSON_BYTES)
        self.assertEqual(26_214_400, config.CANVAS_REMOTE_IMAGE_MAX_BYTES)

    def test_administrator_allowlists_are_normalized_and_not_user_controlled(self) -> None:
        config = load_config(
            CANVAS_PROVIDER_SECRET_KEY="provider-master-key",
            CANVAS_PROVIDER_ALLOWED_HOSTS="API.Vendor.example,ark.cn-beijing.volces.com",
            CANVAS_PROVIDER_PRIVATE_ALLOWED_HOSTS="gateway.internal.example",
            CANVAS_PROVIDER_PRIVATE_ALLOWED_IPS="10.24.0.8,fd00::8",
            CANVAS_ALLOW_INSECURE_PROVIDER_HTTP="1",
            CANVAS_PROVIDER_CONNECT_TIMEOUT_SECONDS="7",
            CANVAS_PROVIDER_TOTAL_TIMEOUT_SECONDS="45",
            CANVAS_PROVIDER_MAX_JSON_BYTES="4096",
        )

        self.assertEqual("provider-master-key", config.CANVAS_PROVIDER_SECRET_KEY)
        self.assertEqual(
            ("api.vendor.example", "ark.cn-beijing.volces.com"),
            config.CANVAS_PROVIDER_ALLOWED_HOSTS,
        )
        self.assertEqual(("gateway.internal.example",), config.CANVAS_PROVIDER_PRIVATE_ALLOWED_HOSTS)
        self.assertEqual(("10.24.0.8", "fd00::8"), config.CANVAS_PROVIDER_PRIVATE_ALLOWED_IPS)
        self.assertTrue(config.CANVAS_ALLOW_INSECURE_PROVIDER_HTTP)
        self.assertEqual(7, config.CANVAS_PROVIDER_CONNECT_TIMEOUT_SECONDS)
        self.assertEqual(45, config.CANVAS_PROVIDER_TOTAL_TIMEOUT_SECONDS)
        self.assertEqual(4096, config.CANVAS_PROVIDER_MAX_JSON_BYTES)

    def test_host_allowlists_reject_wildcards_urls_paths_ports_and_ip_literals(self) -> None:
        for name, value in (
            ("CANVAS_PROVIDER_ALLOWED_HOSTS", "*.vendor.example"),
            ("CANVAS_PROVIDER_ALLOWED_HOSTS", "https://vendor.example"),
            ("CANVAS_PROVIDER_ALLOWED_HOSTS", "vendor.example/api"),
            ("CANVAS_PROVIDER_ALLOWED_HOSTS", "vendor.example:443"),
            ("CANVAS_PROVIDER_ALLOWED_HOSTS", "127.0.0.1"),
            ("CANVAS_PROVIDER_PRIVATE_ALLOWED_HOSTS", "[::1]"),
        ):
            with self.subTest(name=name, value=value):
                with self.assertRaisesRegex(ValueError, name):
                    load_config(**{name: value})

    def test_private_ip_allowlist_accepts_only_exact_ip_addresses(self) -> None:
        for value in ("10.2.0.0/24", "10.2.0.999", "*.internal.example", "https://10.2.0.8"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "CANVAS_PROVIDER_PRIVATE_ALLOWED_IPS"):
                    load_config(CANVAS_PROVIDER_PRIVATE_ALLOWED_IPS=value)

    def test_boolean_and_timeout_values_fail_closed(self) -> None:
        for name, value in (
            ("CANVAS_ALLOW_INSECURE_PROVIDER_HTTP", "true"),
            ("CANVAS_ALLOW_INSECURE_PROVIDER_HTTP", "2"),
            ("CANVAS_PROVIDER_CONNECT_TIMEOUT_SECONDS", "0"),
            ("CANVAS_PROVIDER_CONNECT_TIMEOUT_SECONDS", "10.5"),
            ("CANVAS_PROVIDER_TOTAL_TIMEOUT_SECONDS", "9"),
            ("CANVAS_PROVIDER_MAX_JSON_BYTES", "0"),
        ):
            with self.subTest(name=name, value=value):
                with self.assertRaisesRegex(ValueError, name):
                    load_config(**{name: value})

    def test_total_timeout_must_cover_the_connect_timeout(self) -> None:
        with self.assertRaisesRegex(ValueError, "CANVAS_PROVIDER_TOTAL_TIMEOUT_SECONDS"):
            load_config(
                CANVAS_PROVIDER_CONNECT_TIMEOUT_SECONDS="31",
                CANVAS_PROVIDER_TOTAL_TIMEOUT_SECONDS="30",
            )

    def test_sample_configuration_and_runtime_pins_are_explicit(self) -> None:
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        self.assertEqual(1, requirements.count("cryptography==49.0.0"))
        self.assertEqual(1, requirements.count("httpx==0.27.2"))
        self.assertEqual(1, requirements.count("httpcore==1.0.9"))

        example = (ROOT / ".env.example").read_text(encoding="utf-8")
        for entry in (
            "CANVAS_PROVIDER_SECRET_KEY=\n",
            "CANVAS_PROVIDER_ALLOWED_HOSTS=ark.cn-beijing.volces.com\n",
            "CANVAS_PROVIDER_PRIVATE_ALLOWED_HOSTS=\n",
            "CANVAS_PROVIDER_PRIVATE_ALLOWED_IPS=\n",
            "CANVAS_ALLOW_INSECURE_PROVIDER_HTTP=0\n",
            "CANVAS_PROVIDER_CONNECT_TIMEOUT_SECONDS=10\n",
            "CANVAS_PROVIDER_TOTAL_TIMEOUT_SECONDS=60\n",
            "CANVAS_PROVIDER_MAX_JSON_BYTES=1048576\n",
        ):
            with self.subTest(entry=entry):
                self.assertIn(entry, example)


if __name__ == "__main__":
    unittest.main()
