import base64
import hashlib
import hmac
import importlib.util
import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from integrations.crypto import (
    CredentialDecryptionError,
    CredentialPurpose,
    buyer_id_digest,
    decrypt_credential,
    encrypt_credential,
)


ROOT = Path(__file__).resolve().parents[1]
MASTER_KEY = bytes(range(32))


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _tamper_envelope(envelope: str, field: str) -> str:
    payload = json.loads(envelope)
    raw = bytearray(_decode(payload[field]))
    raw[0] ^= 1
    payload[field] = _encode(bytes(raw))
    return json.dumps(payload, separators=(",", ":"))


class IntegrationCredentialCryptoTests(unittest.TestCase):
    def test_credential_purposes_are_fixed(self):
        self.assertEqual(
            [purpose.value for purpose in CredentialPurpose],
            ["app_secret", "access_token", "refresh_token"],
        )

    def test_aes_gcm_round_trip_uses_exact_versioned_envelope(self):
        envelope = encrypt_credential(
            "test-credential-value",
            master_key=MASTER_KEY,
            purpose=CredentialPurpose.ACCESS_TOKEN,
        )
        payload = json.loads(envelope)

        self.assertEqual(
            tuple(payload),
            ("v", "alg", "nonce", "ciphertext", "tag"),
        )
        self.assertEqual(payload["v"], 1)
        self.assertEqual(payload["alg"], "A256GCM")
        self.assertEqual(len(_decode(payload["nonce"])), 12)
        self.assertEqual(len(_decode(payload["tag"])), 16)
        for field in ("nonce", "ciphertext", "tag"):
            self.assertRegex(payload[field], r"^[A-Za-z0-9_-]+$")
            self.assertNotIn("=", payload[field])
        self.assertEqual(
            decrypt_credential(
                envelope,
                master_key=MASTER_KEY,
                purpose=CredentialPurpose.ACCESS_TOKEN,
            ),
            "test-credential-value",
        )

    def test_random_nonce_makes_envelopes_distinct(self):
        first = encrypt_credential(
            "same-value",
            master_key=MASTER_KEY,
            purpose=CredentialPurpose.APP_SECRET,
        )
        second = encrypt_credential(
            "same-value",
            master_key=MASTER_KEY,
            purpose=CredentialPurpose.APP_SECRET,
        )
        self.assertNotEqual(first, second)

    def test_tampered_nonce_ciphertext_or_tag_fails_closed(self):
        envelope = encrypt_credential(
            "test-credential-value",
            master_key=MASTER_KEY,
            purpose=CredentialPurpose.REFRESH_TOKEN,
        )
        for field in ("nonce", "ciphertext", "tag"):
            with self.subTest(field=field):
                with self.assertRaisesRegex(CredentialDecryptionError, "Unable to decrypt credential"):
                    decrypt_credential(
                        _tamper_envelope(envelope, field),
                        master_key=MASTER_KEY,
                        purpose=CredentialPurpose.REFRESH_TOKEN,
                    )

    def test_wrong_purpose_fails_closed(self):
        envelope = encrypt_credential(
            "test-credential-value",
            master_key=MASTER_KEY,
            purpose=CredentialPurpose.ACCESS_TOKEN,
        )
        with self.assertRaisesRegex(CredentialDecryptionError, "Unable to decrypt credential"):
            decrypt_credential(
                envelope,
                master_key=MASTER_KEY,
                purpose=CredentialPurpose.REFRESH_TOKEN,
            )

    def test_unknown_or_non_exact_envelopes_are_rejected(self):
        envelope = encrypt_credential(
            "test-credential-value",
            master_key=MASTER_KEY,
            purpose=CredentialPurpose.ACCESS_TOKEN,
        )
        cases = []
        for key, value in (("v", 2), ("alg", "A128GCM")):
            payload = json.loads(envelope)
            payload[key] = value
            cases.append(json.dumps(payload))
        payload = json.loads(envelope)
        payload["extra"] = "not-allowed"
        cases.append(json.dumps(payload))
        payload = json.loads(envelope)
        del payload["tag"]
        cases.append(json.dumps(payload))
        cases.extend(("not-json", "[]"))

        for candidate in cases:
            with self.subTest(candidate=candidate):
                with self.assertRaisesRegex(CredentialDecryptionError, "Unable to decrypt credential"):
                    decrypt_credential(
                        candidate,
                        master_key=MASTER_KEY,
                        purpose=CredentialPurpose.ACCESS_TOKEN,
                    )

    def test_duplicate_json_keys_are_rejected_before_envelope_validation(self):
        envelope = encrypt_credential(
            "test-credential-value",
            master_key=MASTER_KEY,
            purpose=CredentialPurpose.ACCESS_TOKEN,
        )
        duplicate_version = envelope.replace('{"v":1', '{"v":2,"v":1', 1)
        duplicate_algorithm = envelope.replace(
            '"alg":"A256GCM"',
            '"alg":"A128GCM","alg":"A256GCM"',
            1,
        )

        for candidate in (duplicate_version, duplicate_algorithm):
            with self.subTest(candidate=candidate):
                with self.assertRaises(CredentialDecryptionError) as raised:
                    decrypt_credential(
                        candidate,
                        master_key=MASTER_KEY,
                        purpose=CredentialPurpose.ACCESS_TOKEN,
                    )
                self.assertEqual(str(raised.exception), "Unable to decrypt credential")
                self.assertNotIn("A128GCM", str(raised.exception))

    def test_envelope_rejects_version_type_confusion_noncanonical_base64_and_wrong_lengths(self):
        envelope = encrypt_credential(
            "test-credential-value",
            master_key=MASTER_KEY,
            purpose=CredentialPurpose.ACCESS_TOKEN,
        )
        cases: list[str] = []
        for confused_version in (True, 1.0, "1"):
            payload = json.loads(envelope)
            payload["v"] = confused_version
            cases.append(json.dumps(payload))

        payload = json.loads(envelope)
        canonical_tag = payload["tag"]
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        last_index = alphabet.index(canonical_tag[-1])
        payload["tag"] = canonical_tag[:-1] + alphabet[(last_index & 0b110000) | 1]
        self.assertEqual(_decode(payload["tag"]), _decode(canonical_tag))
        self.assertNotEqual(payload["tag"], canonical_tag)
        cases.append(json.dumps(payload))

        for field, raw in (
            ("nonce", b"n" * 11),
            ("nonce", b"n" * 13),
            ("tag", b"t" * 15),
            ("tag", b"t" * 17),
        ):
            payload = json.loads(envelope)
            payload[field] = _encode(raw)
            cases.append(json.dumps(payload))

        for candidate in cases:
            with self.subTest(candidate=candidate):
                with self.assertRaisesRegex(CredentialDecryptionError, "Unable to decrypt credential"):
                    decrypt_credential(
                        candidate,
                        master_key=MASTER_KEY,
                        purpose=CredentialPurpose.ACCESS_TOKEN,
                    )

    def test_master_key_must_be_exactly_32_bytes(self):
        for key in (b"m" * 31, b"m" * 33):
            with self.subTest(length=len(key)):
                with self.assertRaisesRegex(ValueError, "32 bytes"):
                    encrypt_credential(
                        "value",
                        master_key=key,
                        purpose=CredentialPurpose.APP_SECRET,
                    )

    def test_buyer_digest_is_deterministic_and_uses_hkdf_key_separation(self):
        external_id = "buyer-external-id-123"
        first = buyer_id_digest(external_id, master_key=MASTER_KEY)
        second = buyer_id_digest(external_id, master_key=MASTER_KEY)
        direct_master_key_hmac = hmac.new(
            MASTER_KEY,
            external_id.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        hkdf_extract = hmac.new(b"\x00" * 32, MASTER_KEY, hashlib.sha256).digest()
        independently_derived_key = hmac.new(
            hkdf_extract,
            b"facai-integrations/buyer-id-hmac/v1\x01",
            hashlib.sha256,
        ).digest()
        independent_golden = hmac.new(
            independently_derived_key,
            external_id.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        ciphertext = encrypt_credential(
            external_id,
            master_key=MASTER_KEY,
            purpose=CredentialPurpose.ACCESS_TOKEN,
        )

        self.assertEqual(first, second)
        self.assertEqual(first, independent_golden)
        self.assertRegex(first, r"^[0-9a-f]{64}$")
        self.assertNotEqual(first, direct_master_key_hmac)
        self.assertNotEqual(first, ciphertext)
        self.assertNotEqual(
            first,
            buyer_id_digest(external_id, master_key=b"x" * 32),
        )


class IntegrationSecretGeneratorTests(unittest.TestCase):
    def _load_module(self):
        path = ROOT / "scripts" / "generate_integration_secrets.py"
        spec = importlib.util.spec_from_file_location("generate_integration_secrets_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_generator_outputs_only_generated_env_values_without_password_or_file_writes(self):
        module = self._load_module()
        output = io.StringIO()
        errors = io.StringIO()
        password = "test-password-must-not-appear"
        generated = (b"m" * 32, b"s" * 48, b"z" * 16)

        with (
            patch.object(module.getpass, "getpass", return_value=password),
            patch.object(module.secrets, "token_bytes", side_effect=generated),
            patch("builtins.open", side_effect=AssertionError("generator must not write files")),
            patch("pathlib.Path.open", side_effect=AssertionError("generator must not open files")),
            patch("pathlib.Path.write_text", side_effect=AssertionError("generator must not write files")),
            patch("pathlib.Path.write_bytes", side_effect=AssertionError("generator must not write files")),
            redirect_stdout(output),
            redirect_stderr(errors),
        ):
            module.main()

        rendered = output.getvalue()
        lines = rendered.strip().splitlines()
        self.assertEqual(len(lines), 3)
        self.assertEqual(
            lines[0],
            f"FACAI_INTEGRATIONS_MASTER_KEY={_encode(generated[0])}",
        )
        self.assertEqual(
            lines[1],
            f"FACAI_INTEGRATIONS_SESSION_SECRET={_encode(generated[1])}",
        )
        self.assertRegex(
            lines[2],
            r"^FACAI_INTEGRATIONS_ADMIN_PASSWORD_HASH=\$scrypt\$n=32768,r=8,p=1\$[A-Za-z0-9_-]+\$[A-Za-z0-9_-]+$",
        )
        self.assertNotIn(password, rendered)
        self.assertEqual(errors.getvalue(), "")

        encoded_hash = lines[2].split("=", 1)[1]
        _, algorithm, parameters, salt_encoded, digest_encoded = encoded_hash.split("$")
        self.assertEqual(algorithm, "scrypt")
        self.assertEqual(parameters, "n=32768,r=8,p=1")
        expected_digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_decode(salt_encoded),
            n=32768,
            r=8,
            p=1,
            dklen=64,
            maxmem=134_217_728,
        )
        self.assertEqual(_decode(digest_encoded), expected_digest)


if __name__ == "__main__":
    unittest.main()
