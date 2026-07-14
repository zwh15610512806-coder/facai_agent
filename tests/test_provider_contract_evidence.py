from __future__ import annotations

import json
import re
import unittest
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_DIR = ROOT / "integrations" / "provider_contracts"
DOC_DIR = ROOT / "docs" / "integrations" / "provider-contracts"
PROVIDERS = ("qianchuan", "doudian", "taobao", "pdd")
VALID_STATUSES = {
    "verification_required",
    "public_docs_verified",
    "approved_app_verified",
}
OPERATION_REQUIRED_FIELDS = {
    "key",
    "official_url",
    "http_method",
    "gateway_or_path",
    "required_scopes",
    "window_limit",
    "pagination",
    "external_ids",
    "rate_limit",
    "verified_at",
    "verification_source",
}
OFFICIAL_CONTRACT_NOT_VERIFIED = "official_contract_not_verified"

_SENSITIVE_KEY_PARTS = {
    "token",
    "secret",
    "access_token",
    "refresh_token",
    "app_secret",
    "client_secret",
    "client_password",
    "password",
    "private_key",
    "credential",
    "authorization",
    "cookie",
}
_SENSITIVE_VALUE_PATTERNS = (
    re.compile(
        r"(?i)(?:access[ _-]?token|refresh[ _-]?token|app[ _-]?secret|"
        r"client[ _-]?secret|password)\s*[:=]"
    ),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{8,}={0,2}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"(?i)\b(?:sk|secret|token)[_-](?:live|prod|test)[_-][A-Za-z0-9]{8,}\b"),
    re.compile(r"https://[^/?#\s:@]+:[^/?#\s@]+@"),
)
_PENDING_COMPLETION_PATTERN = re.compile(
    r"(?i)\b(?:verified|verification|acceptance|review)\b"
    r"[^\r\n]{0,48}\b(?:yes|true|complete|completed|approved|passed)\b"
)


@dataclass(frozen=True, slots=True)
class OperationCapabilityGate:
    reason: str | None
    scheduled: bool
    provider_active: bool


def capability_gate_for_operation(
    contract: Mapping[str, Any], operation_key: str
) -> OperationCapabilityGate:
    """Conservatively gate scheduling and active state on catalog evidence."""
    operation_exists = any(
        operation.get("key") == operation_key
        for operation in contract.get("operations", ())
        if isinstance(operation, Mapping)
    )
    if not operation_exists:
        return OperationCapabilityGate(
            reason=OFFICIAL_CONTRACT_NOT_VERIFIED,
            scheduled=False,
            provider_active=False,
        )
    approved = contract.get("status") == "approved_app_verified"
    return OperationCapabilityGate(
        reason=None if approved else "approved_app_contract_not_verified",
        scheduled=approved,
        provider_active=approved,
    )


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise AssertionError(f"{path} must contain a JSON object")
    return value


def _resolve_local_ref(root_schema: Mapping[str, Any], reference: str) -> Mapping[str, Any]:
    if not reference.startswith("#/"):
        raise AssertionError(f"external schema references are forbidden: {reference}")
    value: Any = root_schema
    for raw_part in reference[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        value = value[part]
    if not isinstance(value, Mapping):
        raise AssertionError(f"schema reference is not an object: {reference}")
    return value


def _schema_error(path: str, message: str) -> AssertionError:
    return AssertionError(f"{path}: {message}")


def validate_json_schema(
    value: Any,
    schema: Mapping[str, Any],
    *,
    root_schema: Mapping[str, Any] | None = None,
    path: str = "$",
) -> None:
    """Validate the deliberately small JSON-Schema subset used by the evidence format."""
    root_schema = root_schema or schema
    if "$ref" in schema:
        validate_json_schema(
            value,
            _resolve_local_ref(root_schema, str(schema["$ref"])),
            root_schema=root_schema,
            path=path,
        )
        return

    expected_type = schema.get("type")
    type_checks = {
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
        "null": lambda item: item is None,
    }
    if expected_type is not None and not type_checks[str(expected_type)](value):
        raise _schema_error(path, f"expected {expected_type}")
    if "enum" in schema and value not in schema["enum"]:
        raise _schema_error(path, f"value is not in enum {schema['enum']!r}")
    if "const" in schema and value != schema["const"]:
        raise _schema_error(path, f"expected constant {schema['const']!r}")

    if isinstance(value, dict):
        required = set(schema.get("required", ()))
        missing = sorted(required.difference(value))
        if missing:
            raise _schema_error(path, f"missing required fields: {missing!r}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extras = sorted(set(value).difference(properties))
            if extras:
                raise _schema_error(path, f"unexpected fields: {extras!r}")
        for key, item in value.items():
            if key in properties:
                validate_json_schema(
                    item,
                    properties[key],
                    root_schema=root_schema,
                    path=f"{path}.{key}",
                )

    if isinstance(value, list):
        if len(value) < int(schema.get("minItems", 0)):
            raise _schema_error(path, "contains too few items")
        if "maxItems" in schema and len(value) > int(schema["maxItems"]):
            raise _schema_error(path, "contains too many items")
        if schema.get("uniqueItems"):
            canonical = [json.dumps(item, sort_keys=True, separators=(",", ":")) for item in value]
            if len(canonical) != len(set(canonical)):
                raise _schema_error(path, "contains duplicate items")
        item_schema = schema.get("items")
        if item_schema:
            for index, item in enumerate(value):
                validate_json_schema(
                    item,
                    item_schema,
                    root_schema=root_schema,
                    path=f"{path}[{index}]",
                )

    if isinstance(value, str):
        if len(value) < int(schema.get("minLength", 0)):
            raise _schema_error(path, "string is too short")
        if "maxLength" in schema and len(value) > int(schema["maxLength"]):
            raise _schema_error(path, "string is too long")
        pattern = schema.get("pattern")
        if pattern and re.fullmatch(str(pattern), value) is None:
            raise _schema_error(path, f"does not match {pattern!r}")
        if schema.get("format") == "date":
            try:
                parsed = date.fromisoformat(value)
            except ValueError as exc:
                raise _schema_error(path, "expected an ISO calendar date") from exc
            if parsed.isoformat() != value:
                raise _schema_error(path, "date is not canonical YYYY-MM-DD")
        if schema.get("format") == "uri":
            parsed_uri = urlsplit(value)
            if not parsed_uri.scheme or not parsed_uri.netloc:
                raise _schema_error(path, "expected an absolute URI")


def sensitive_material_paths(value: Any, *, path: str = "$") -> tuple[str, ...]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")
            compact_key = normalized_key.replace("_", "")
            if any(
                normalized_key == part
                or normalized_key.startswith(f"{part}_")
                or normalized_key.endswith(f"_{part}")
                or part.replace("_", "") in compact_key
                for part in _SENSITIVE_KEY_PARTS
            ):
                findings.append(f"{path}.{key}")
            findings.extend(sensitive_material_paths(item, path=f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            findings.extend(sensitive_material_paths(item, path=f"{path}[{index}]"))
    elif isinstance(value, str):
        if any(pattern.search(value) for pattern in _SENSITIVE_VALUE_PATTERNS):
            findings.append(path)
    return tuple(findings)


def assert_pending_markdown(markdown: str) -> None:
    """Reject conflicting evidence metadata or completion claims in pending docs."""

    statuses = re.findall(r"(?im)^\s*status:\s*(\S+)\s*$", markdown)
    if statuses != ["verification_required"]:
        raise AssertionError("pending evidence contains a completion claim")
    for label in ("Reviewer", "Capture date", "Sanitized artifact SHA-256"):
        values = re.findall(
            rf"(?im)^\s*{re.escape(label)}:\s*(.*?)\s*$",
            markdown,
        )
        if values != ["pending"]:
            raise AssertionError("pending evidence contains a completion claim")
    if _PENDING_COMPLETION_PATTERN.search(markdown):
        raise AssertionError("pending evidence contains a completion claim")
    sensitive_paths = sensitive_material_paths(markdown)
    if sensitive_paths:
        raise AssertionError("pending evidence contains sensitive material")


def validate_contract_evidence(
    contract: Mapping[str, Any], schema: Mapping[str, Any]
) -> None:
    """Apply the structural and no-sensitive-material evidence gates together."""
    sensitive_paths = sensitive_material_paths(contract)
    if sensitive_paths:
        raise AssertionError(
            "sensitive material is forbidden at: " + ", ".join(sensitive_paths)
        )
    validate_json_schema(contract, schema)
    operations = contract["operations"]
    if contract["status"] != "verification_required" and not operations:
        raise AssertionError("verified status requires operation evidence")
    declared_hosts = set(contract["official_hosts"])
    for operation in operations:
        operation_host = urlsplit(operation["official_url"]).hostname
        if operation_host not in declared_hosts:
            raise AssertionError(
                f"operation {operation['key']!r} official_url host is not declared"
            )


def _synthetic_verified_operation() -> dict[str, Any]:
    return {
        "key": "orders_list",
        "official_url": "https://official.example.invalid/v1/orders",
        "http_method": "GET",
        "gateway_or_path": "/v1/orders",
        "required_scopes": ["orders.read"],
        "window_limit": "one calendar day",
        "pagination": {"request": ["cursor"], "response": ["next_cursor"]},
        "external_ids": ["order_id"],
        "rate_limit": "control_panel_only",
        "verified_at": "2026-07-14",
        "verification_source": "approved_app_console",
    }


class ProviderContractEvidenceTests(unittest.TestCase):
    def test_each_provider_document_validates_against_schema(self) -> None:
        schema = _load_json(CONTRACT_DIR / "schema.json")
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        for provider in PROVIDERS:
            with self.subTest(provider=provider):
                contract = _load_json(CONTRACT_DIR / f"{provider}.json")
                validate_contract_evidence(contract, schema)
                self.assertEqual(contract["provider"], provider)
                operation_keys = [item["key"] for item in contract["operations"]]
                self.assertEqual(len(operation_keys), len(set(operation_keys)))

    def test_current_contracts_make_no_unverified_network_or_operation_claims(self) -> None:
        for provider in PROVIDERS:
            with self.subTest(provider=provider):
                contract = _load_json(CONTRACT_DIR / f"{provider}.json")
                self.assertEqual(contract["status"], "verification_required")
                self.assertEqual(contract["official_hosts"], [])
                self.assertEqual(contract["operations"], [])
                self.assertEqual(
                    contract["application_type"],
                    "approved_application_not_available",
                )

    def test_schema_requires_status_and_complete_operation_evidence(self) -> None:
        schema = _load_json(CONTRACT_DIR / "schema.json")
        self.assertEqual(set(schema["properties"]["status"]["enum"]), VALID_STATUSES)
        operation_schema = schema["$defs"]["operation"]
        self.assertEqual(set(operation_schema["required"]), OPERATION_REQUIRED_FIELDS)

        candidate = {
            "provider": "qianchuan",
            "status": "approved_app_verified",
            "official_hosts": ["official.example.invalid"],
            "application_type": "synthetic_test_application",
            "operations": [_synthetic_verified_operation()],
        }
        validate_json_schema(candidate, schema)
        for field in sorted(OPERATION_REQUIRED_FIELDS):
            with self.subTest(missing_operation_field=field):
                invalid = json.loads(json.dumps(candidate))
                del invalid["operations"][0][field]
                with self.assertRaisesRegex(AssertionError, "missing required fields"):
                    validate_json_schema(invalid, schema)

        invalid_status = json.loads(json.dumps(candidate))
        invalid_status["status"] = "active"
        with self.assertRaisesRegex(AssertionError, "not in enum"):
            validate_json_schema(invalid_status, schema)

    def test_verified_status_requires_operations_and_declared_official_hosts(self) -> None:
        schema = _load_json(CONTRACT_DIR / "schema.json")
        for status in ("public_docs_verified", "approved_app_verified"):
            with self.subTest(status=status):
                empty_claim = {
                    "provider": "qianchuan",
                    "status": status,
                    "official_hosts": [],
                    "application_type": "synthetic_test_application",
                    "operations": [],
                }
                with self.assertRaisesRegex(
                    AssertionError, "verified status requires operation evidence"
                ):
                    validate_contract_evidence(empty_claim, schema)

        mismatched_host = {
            "provider": "qianchuan",
            "status": "approved_app_verified",
            "official_hosts": ["different.example.invalid"],
            "application_type": "synthetic_test_application",
            "operations": [_synthetic_verified_operation()],
        }
        with self.assertRaisesRegex(
            AssertionError, "official_url host is not declared"
        ):
            validate_contract_evidence(mismatched_host, schema)

    def test_contracts_and_schema_reject_sensitive_keys_and_values(self) -> None:
        for filename in ("schema.json", *(f"{provider}.json" for provider in PROVIDERS)):
            with self.subTest(filename=filename):
                self.assertEqual(
                    sensitive_material_paths(_load_json(CONTRACT_DIR / filename)),
                    (),
                )

        sensitive_key = {
            "provider": "qianchuan",
            "status": "approved_app_verified",
            "official_hosts": ["official.example.invalid"],
            "application_type": "synthetic_test_application",
            "operations": [{**_synthetic_verified_operation(), "token": "redacted"}],
        }
        self.assertEqual(
            sensitive_material_paths(sensitive_key),
            ("$.operations[0].token",),
        )
        sensitive_value = {
            "provider": "qianchuan",
            "status": "approved_app_verified",
            "official_hosts": ["official.example.invalid"],
            "application_type": "synthetic_test_application",
            "operations": [
                {
                    **_synthetic_verified_operation(),
                    "window_limit": "access_token=not-a-real-token-value",
                }
            ],
        }
        schema = _load_json(CONTRACT_DIR / "schema.json")
        for candidate in (sensitive_key, sensitive_value):
            with self.subTest(candidate=candidate):
                with self.assertRaisesRegex(AssertionError, "sensitive material"):
                    validate_contract_evidence(candidate, schema)

    def test_sensitive_scan_rejects_camel_case_credential_keys(self) -> None:
        for key in (
            "accessToken",
            "refreshToken",
            "appSecret",
            "clientSecret",
            "privateKey",
            "api_token_value",
        ):
            with self.subTest(key=key):
                self.assertEqual(
                    sensitive_material_paths({key: "review-sentinel"}),
                    (f"$.{key}",),
                )

    def test_absent_operation_is_never_scheduled_or_active(self) -> None:
        for provider in PROVIDERS:
            with self.subTest(provider=provider):
                contract = _load_json(CONTRACT_DIR / f"{provider}.json")
                gate = capability_gate_for_operation(contract, "orders_list")
                self.assertEqual(gate.reason, OFFICIAL_CONTRACT_NOT_VERIFIED)
                self.assertFalse(gate.scheduled)
                self.assertFalse(gate.provider_active)

    def test_markdown_records_future_verification_without_claiming_completion(self) -> None:
        for provider in PROVIDERS:
            with self.subTest(provider=provider):
                markdown = (DOC_DIR / f"{provider}.md").read_text(encoding="utf-8")
                assert_pending_markdown(markdown)
                self.assertIn("status: verification_required", markdown)
                self.assertIn("official_hosts: []", markdown)
                self.assertIn("operations: []", markdown)
                self.assertIn("approved application console", markdown.lower())
                self.assertIn("official documentation", markdown.lower())
                self.assertIn("Reviewer: pending", markdown)
                self.assertIn("Capture date: pending", markdown)
                self.assertIn("Sanitized artifact SHA-256: pending", markdown)
                self.assertNotRegex(markdown, r"https?://")
                self.assertNotRegex(markdown, r"\b[a-fA-F0-9]{64}\b")

        with self.assertRaisesRegex(AssertionError, "completion claim"):
            assert_pending_markdown(
                "status: verification_required\nReviewer: pending\nVerified: yes\n"
            )
        current = (DOC_DIR / "qianchuan.md").read_text(encoding="utf-8")
        with self.assertRaisesRegex(AssertionError, "completion claim"):
            assert_pending_markdown(current + "\nLive acceptance completed\n")
        with self.assertRaisesRegex(AssertionError, "completion claim"):
            assert_pending_markdown(
                current
                + "\nstatus: approved_app_verified\n"
                + "Reviewer: Alice\n"
                + "Capture date: 2026-07-14\n"
                + "Live acceptance completed\n"
                + "clientSecret: review-sentinel\n"
            )


if __name__ == "__main__":
    unittest.main()
