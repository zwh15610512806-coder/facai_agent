import copy
import unittest

from integrations.redaction import (
    PayloadSafetyError,
    assert_payload_safe,
    normalize_payload_key,
    redact_payload,
)


class IntegrationPayloadRedactionTests(unittest.TestCase):
    def test_redaction_removes_sensitive_keys_recursively_without_mutating_input(self):
        payload = {
            "external_order_id": "order-1",
            "province": "Guangdong",
            "city": "Shenzhen",
            "buyer": {
                "buyer_name": "test-buyer-name",
                "Mobile-Phone": "test-mobile-value",
                "external_id": "buyer-external-1",
            },
            "receiver": [
                {
                    "receiverName": "test-receiver-name",
                    "id_card": "test-id-card",
                    "detailed_address": "test-detail-address",
                }
            ],
            "credentials": {
                "access_token": "test-access-token",
                "refreshToken": "test-refresh-token",
                "App Secret": "test-app-secret",
                "authorization_code": "test-authorization-code",
                "Cookie": "test-cookie",
                "token_ciphertext": "test-ciphertext",
            },
        }
        original = copy.deepcopy(payload)

        redacted = redact_payload(payload)

        self.assertEqual(payload, original)
        self.assertEqual(redacted["external_order_id"], "order-1")
        self.assertEqual(redacted["province"], "Guangdong")
        self.assertEqual(redacted["city"], "Shenzhen")
        self.assertEqual(redacted["buyer"], {"external_id": "buyer-external-1"})
        self.assertEqual(redacted["receiver"], [{}])
        self.assertEqual(redacted["credentials"], {})
        rendered = repr(redacted)
        for sentinel in (
            "test-buyer-name",
            "test-mobile-value",
            "test-receiver-name",
            "test-access-token",
            "test-refresh-token",
            "test-app-secret",
            "test-ciphertext",
        ):
            self.assertNotIn(sentinel, rendered)

    def test_key_normalization_is_case_and_punctuation_insensitive(self):
        payload = {
            "ACCESS-TOKEN": "secret-1",
            "Refresh.Token": "secret-2",
            "Receiver Name": "secret-3",
            "ID Card": "secret-4",
            "Set_Cookie": "secret-5",
            "safe_external_id": "safe-1",
        }
        self.assertEqual(redact_payload(payload), {"safe_external_id": "safe-1"})

    def test_key_normalization_uses_nfkc_casefold_and_ascii_alphanumerics(self):
        self.assertEqual(
            normalize_payload_key("ＡＣＣＥＳＳ＿ＴＯＫＥＮ-省份"),
            "accesstoken",
        )
        payload = {
            "ＡＣＣＥＳＳ＿ＴＯＫＥＮ": "secret-fullwidth-token",
            "ｂｕｙｅｒ": {"ＮＡＭＥ": "secret-fullwidth-buyer-name"},
            "receiver": {"ＡＤＤＲＥＳＳ": "secret-fullwidth-address"},
            "product": {"name": "safe-product-name"},
            "province": "Guangdong",
            "city": "Shenzhen",
        }
        self.assertEqual(
            redact_payload(payload),
            {
                "ｂｕｙｅｒ": {},
                "receiver": {},
                "product": {"name": "safe-product-name"},
                "province": "Guangdong",
                "city": "Shenzhen",
            },
        )

    def test_sensitive_key_variants_cannot_evade_redaction_with_prefixes_or_suffixes(self):
        payload = {
            "provider_access_token_value": "secret-1",
            "old_refresh_token_backup": "secret-2",
            "encrypted_app_secret_value": "secret-3",
            "receiver_phone_number": "secret-4",
            "buyer_mobile_no": "secret-5",
            "receiver_id_card_no": "secret-6",
            "receiver_detail_address_text": "secret-7",
            "request_cookie_header": "secret-8",
            "credential_ciphertext_v1": "secret-9",
            "external_order_id": "safe-order-1",
        }

        self.assertEqual(redact_payload(payload), {"external_order_id": "safe-order-1"})

    def test_contextual_buyer_and_receiver_names_and_addresses_are_removed(self):
        payload = {
            "buyer": {
                "name": "secret-buyer-name",
                "external_id": "buyer-1",
                "profile": {"full_name": "secret-nested-buyer-name"},
            },
            "receiver_info": {
                "name": "secret-receiver-name",
                "contact": {"address": "secret-nested-receiver-address"},
            },
            "product": {"name": "safe-product-name"},
        }

        self.assertEqual(
            redact_payload(payload),
            {
                "buyer": {"external_id": "buyer-1", "profile": {}},
                "receiver_info": {"contact": {}},
                "product": {"name": "safe-product-name"},
            },
        )
        with self.assertRaisesRegex(
            PayloadSafetyError,
            r"^Unsafe payload key: \$\.buyer\.name$",
        ):
            assert_payload_safe(payload)

    def test_assert_payload_safe_reports_only_banned_key_path(self):
        sentinel = "test-value-must-never-appear-in-error"
        payload = {
            "orders": [
                {
                    "receiver": {
                        "phone_number": sentinel,
                    }
                }
            ]
        }

        with self.assertRaises(PayloadSafetyError) as raised:
            assert_payload_safe(payload)

        message = str(raised.exception)
        self.assertEqual(message, "Unsafe payload key: $.orders[0].receiver.phone_number")
        self.assertNotIn(sentinel, message)

    def test_assert_payload_safe_accepts_normalized_external_ids_and_coarse_location(self):
        payload = {
            "external_order_id": "order-1",
            "buyer_digest": "digest-1",
            "province": "Guangdong",
            "city": "Shenzhen",
            "items": [{"external_product_id": "product-1"}],
        }
        self.assertIsNone(assert_payload_safe(payload))


if __name__ == "__main__":
    unittest.main()
