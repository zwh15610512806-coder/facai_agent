import gzip
import hashlib
import json
import os
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from integration_models import IntegrationArchiveManifest
from integrations.sync.archive import (
    ARCHIVE_ENVELOPE_PREFIX,
    ArchiveAuditCode,
    ArchiveCleanupErrorCode,
    ArchiveDecryptionError,
    ArchivePage,
    ArchiveWriteError,
    archive_expires_at,
    cleanup_expired_archives,
    create_archive_page,
    decrypt_archive_bytes,
    scan_orphan_archives,
)
from integrations.crypto import derive_archive_page_key
from integrations.redaction import PayloadSafetyError
from integrations.types import NormalizedRecord, Provider, ResourceType
import integrations.sync.archive as archive_module


class IntegrationArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.archive_dir = Path(self.temp_dir.name) / "archives"
        self.master_key = bytes(range(32))
        self.now = datetime(2026, 7, 14, 2, 30, tzinfo=timezone.utc)
        self.record = NormalizedRecord(
            resource=ResourceType.ORDERS,
            external_id="order-1",
            platform_updated_at=self.now,
            payload={
                "external_order_id": "order-1",
                "normalized_internal_only": "normalized-private-sentinel",
            },
            sanitized_source_payload={
                "z": "safe",
                "a": {"b": 2, "a": 1},
            },
        )

    def _create(self, **overrides):
        values = {
            "archive_dir": self.archive_dir,
            "master_key": self.master_key,
            "provider": Provider.DOUDIAN,
            "connection_id": 7,
            "resource": ResourceType.ORDERS,
            "run_id": 42,
            "page_number": 3,
            "created_at": self.now,
            "records": (self.record,),
        }
        values.update(overrides)
        return create_archive_page(**values)

    def _path(self, relative_path: str) -> Path:
        return self.archive_dir.joinpath(*relative_path.split("/"))

    def test_archive_key_uses_the_exact_archive_hkdf_context(self):
        expected = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"facai-integrations/archive-page/v1",
        ).derive(self.master_key)

        actual = derive_archive_page_key(self.master_key)

        self.assertEqual(actual, expected)
        self.assertNotEqual(actual, self.master_key)
        self.assertEqual(actual, derive_archive_page_key(self.master_key))

    def test_sorted_compact_jsonl_and_zero_mtime_gzip_are_deterministic(self):
        first = self._create()
        first_envelope = self._path(first.relative_path).read_bytes()
        second = self._create()
        second_envelope = self._path(second.relative_path).read_bytes()

        first_plaintext = decrypt_archive_bytes(
            first_envelope,
            master_key=self.master_key,
            relative_path=first.relative_path,
        )
        second_plaintext = decrypt_archive_bytes(
            second_envelope,
            master_key=self.master_key,
            relative_path=second.relative_path,
        )
        prefix_length = len(ARCHIVE_ENVELOPE_PREFIX)
        first_compressed = AESGCM(derive_archive_page_key(self.master_key)).decrypt(
            first_envelope[prefix_length : prefix_length + 12],
            first_envelope[prefix_length + 12 :],
            first.relative_path.encode("utf-8"),
        )
        second_compressed = AESGCM(derive_archive_page_key(self.master_key)).decrypt(
            second_envelope[prefix_length : prefix_length + 12],
            second_envelope[prefix_length + 12 :],
            second.relative_path.encode("utf-8"),
        )

        self.assertEqual(first_plaintext, b'{"a":{"a":1,"b":2},"z":"safe"}\n')
        self.assertEqual(first_plaintext, second_plaintext)
        self.assertEqual(first_compressed, second_compressed)
        self.assertEqual(first_compressed[4:8], b"\x00\x00\x00\x00")
        self.assertEqual(gzip.decompress(first_compressed), first_plaintext)
        self.assertNotEqual(first_envelope, second_envelope)
        self.assertEqual(first_envelope[: len(ARCHIVE_ENVELOPE_PREFIX)], ARCHIVE_ENVELOPE_PREFIX)

    def test_jsonl_has_stable_encodings_for_decimal_date_and_aware_datetime(self):
        record = NormalizedRecord(
            resource=ResourceType.DAILY_METRICS,
            external_id="metric-1",
            platform_updated_at=self.now,
            payload={"external_metric_id": "metric-1"},
            sanitized_source_payload={
                "amount": Decimal("12.30"),
                "day": date(2026, 7, 13),
                "observed_at": datetime(
                    2026,
                    7,
                    13,
                    10,
                    5,
                    tzinfo=timezone(timedelta(hours=8)),
                ),
            },
        )

        artifact = self._create(
            resource=ResourceType.DAILY_METRICS,
            records=(record,),
        )
        plaintext = decrypt_archive_bytes(
            self._path(artifact.relative_path).read_bytes(),
            master_key=self.master_key,
            relative_path=artifact.relative_path,
        )

        self.assertEqual(
            json.loads(plaintext),
            {
                "amount": "12.30",
                "day": "2026-07-13",
                "observed_at": "2026-07-13T02:05:00Z",
            },
        )

    def test_random_nonce_and_canonical_relative_path_bind_the_aad(self):
        first = self._create()
        first_envelope = self._path(first.relative_path).read_bytes()
        second = self._create()
        second_envelope = self._path(second.relative_path).read_bytes()

        self.assertEqual(
            first.relative_path,
            "doudian/7/orders/2026/07/42-000003.jsonl.gz.aes",
        )
        prefix_length = len(ARCHIVE_ENVELOPE_PREFIX)
        self.assertEqual(len(first_envelope[prefix_length : prefix_length + 12]), 12)
        self.assertNotEqual(
            first_envelope[prefix_length : prefix_length + 12],
            second_envelope[prefix_length : prefix_length + 12],
        )
        with self.assertRaises(ArchiveDecryptionError):
            decrypt_archive_bytes(
                first_envelope,
                master_key=self.master_key,
                relative_path=first.relative_path.replace("orders", "refunds"),
            )

    def test_magic_nonce_ciphertext_and_tag_tampering_fail_closed(self):
        artifact = self._create()
        envelope = self._path(artifact.relative_path).read_bytes()
        indexes = (0, len(ARCHIVE_ENVELOPE_PREFIX), len(envelope) - 17, len(envelope) - 1)

        for index in indexes:
            tampered = bytearray(envelope)
            tampered[index] ^= 1
            with self.subTest(index=index), self.assertRaises(ArchiveDecryptionError) as caught:
                decrypt_archive_bytes(
                    bytes(tampered),
                    master_key=self.master_key,
                    relative_path=artifact.relative_path,
                )
            self.assertEqual(str(caught.exception), "Unable to decrypt archive page")

    def test_only_sanitized_source_payload_is_archived(self):
        artifact = self._create()
        plaintext = decrypt_archive_bytes(
            self._path(artifact.relative_path).read_bytes(),
            master_key=self.master_key,
            relative_path=artifact.relative_path,
        )

        self.assertNotIn(b"normalized-private-sentinel", plaintext)
        self.assertNotIn(b"external_order_id", plaintext)
        self.assertEqual(json.loads(plaintext), {"a": {"a": 1, "b": 2}, "z": "safe"})

    def test_archive_reasserts_payload_safety_without_leaking_rejected_values(self):
        secret = "raw-secret-sentinel-13800138000"
        object.__setattr__(
            self.record,
            "sanitized_source_payload",
            MappingProxyType({"access_token": secret}),
        )

        with self.assertRaises(PayloadSafetyError) as caught:
            self._create()

        self.assertNotIn(secret, str(caught.exception))
        self.assertEqual(list(self.archive_dir.rglob("*.aes")), [])

    def test_archive_rejects_pii_and_secrets_hidden_in_safe_named_values(self):
        unsafe_values = (
            "Bearer raw-secret-sentinel",
            "buyer-sentinel@example.com",
            "13800138000",
            "11010519491231002X",
            "https://api.example.test/path?access_token=raw-secret-sentinel",
            '{"refresh_token":"raw-secret-sentinel"}',
        )
        for index, unsafe_value in enumerate(unsafe_values):
            record = NormalizedRecord(
                resource=ResourceType.ORDERS,
                external_id=f"unsafe-{index}",
                platform_updated_at=self.now,
                payload={"external_order_id": f"unsafe-{index}"},
                sanitized_source_payload={"note": unsafe_value},
            )
            with self.subTest(index=index):
                with self.assertRaises(PayloadSafetyError) as caught:
                    self._create(records=(record,), page_number=100 + index)
                self.assertNotIn(unsafe_value, str(caught.exception))
        self.assertEqual(list(self.archive_dir.rglob("*.aes")), [])

    def test_external_ids_that_resemble_phone_or_id_card_are_not_false_positives(self):
        record = NormalizedRecord(
            resource=ResourceType.ORDERS,
            external_id="13800138000",
            platform_updated_at=self.now,
            payload={"external_order_id": "13800138000"},
            sanitized_source_payload={
                "external_order_id": "13800138000",
                "external_subject_id": "11010519491231002X",
            },
        )

        artifact = self._create(records=(record,), page_number=106)
        plaintext = decrypt_archive_bytes(
            self._path(artifact.relative_path).read_bytes(),
            master_key=self.master_key,
            relative_path=artifact.relative_path,
        )

        self.assertEqual(
            json.loads(plaintext),
            {
                "external_order_id": "13800138000",
                "external_subject_id": "11010519491231002X",
            },
        )

    def test_components_are_strict_and_resolved_under_archive_root(self):
        invalid = (
            {"provider": "doudian"},
            {"resource": "orders"},
            {"connection_id": True},
            {"connection_id": 0},
            {"run_id": 0},
            {"page_number": -1},
            {"page_number": 1_000_000},
            {"created_at": self.now.replace(tzinfo=None)},
            {"resource": ResourceType.REFUNDS},
            {"records": ({"sanitized_source_payload": {}},)},
        )
        for values in invalid:
            with self.subTest(values=values), self.assertRaises((TypeError, ValueError)):
                self._create(**values)

        outside = Path(self.temp_dir.name) / "outside.jsonl.gz.aes"
        outside.write_bytes(b"outside-sentinel")
        engine, db = self._manifest_session()
        self.addCleanup(engine.dispose)
        self.addCleanup(db.close)
        manifest = self._add_manifest(
            db,
            relative_path="../../outside.jsonl.gz.aes",
            expires_at=self.now - timedelta(seconds=1),
        )
        retries = []

        result = cleanup_expired_archives(
            db,
            archive_dir=self.archive_dir,
            now=self.now,
            audit_missing=lambda *_: self.fail("invalid paths are not missing files"),
            enqueue_retry=lambda manifest_id, code: retries.append((manifest_id, code)),
        )

        self.assertEqual(outside.read_bytes(), b"outside-sentinel")
        self.assertIsNone(manifest.deleted_at)
        self.assertEqual(retries, [(manifest.id, ArchiveCleanupErrorCode.INVALID_PATH)])
        self.assertEqual(result.retry_count, 1)

    def test_atomic_write_uses_random_sibling_temp_fsync_and_replace(self):
        real_replace = os.replace
        real_fsync = os.fsync
        observed_sources = []
        fsync_happened = []

        def observed_fsync(fd):
            fsync_happened.append(fd)
            return real_fsync(fd)

        def observed_replace(source, destination):
            source_path = Path(source)
            destination_path = Path(destination)
            self.assertTrue(fsync_happened)
            self.assertTrue(source_path.exists())
            self.assertFalse(destination_path.exists())
            self.assertEqual(source_path.parent, destination_path.parent)
            self.assertTrue(source_path.name.endswith(".tmp"))
            observed_sources.append(source_path.name)
            return real_replace(source, destination)

        with patch.object(archive_module.os, "fsync", side_effect=observed_fsync), patch.object(
            archive_module.os,
            "replace",
            side_effect=observed_replace,
        ):
            first = self._create(page_number=1)
            second = self._create(page_number=2)

        self.assertNotEqual(observed_sources[0], observed_sources[1])
        self.assertTrue(self._path(first.relative_path).is_file())
        self.assertTrue(self._path(second.relative_path).is_file())
        self.assertEqual(list(self.archive_dir.rglob("*.tmp")), [])

    def test_write_failure_is_safe_and_removes_the_random_temp_file(self):
        raw_error = "raw-secret-sentinel-13800138000"
        with patch.object(
            archive_module.os,
            "replace",
            side_effect=PermissionError(raw_error),
        ), self.assertRaises(ArchiveWriteError) as caught:
            self._create()

        self.assertEqual(str(caught.exception), "Unable to write archive page")
        self.assertNotIn(raw_error, repr(caught.exception))
        self.assertEqual(list(self.archive_dir.rglob("*.tmp")), [])
        self.assertEqual(list(self.archive_dir.rglob("*.aes")), [])

    def test_artifact_reports_manifest_hash_and_record_count(self):
        second_record = NormalizedRecord(
            resource=ResourceType.ORDERS,
            external_id="order-2",
            platform_updated_at=self.now,
            payload={"external_order_id": "order-2"},
            sanitized_source_payload={"id": "order-2"},
        )
        artifact = self._create(records=(self.record, second_record))
        encrypted = self._path(artifact.relative_path).read_bytes()

        self.assertEqual(artifact.sha256, hashlib.sha256(encrypted).hexdigest())
        self.assertEqual(artifact.record_count, 2)

    def test_archive_page_deletes_until_database_commit_is_retained(self):
        failed = ArchivePage(
            archive_dir=self.archive_dir,
            master_key=self.master_key,
            provider=Provider.DOUDIAN,
            connection_id=7,
            resource=ResourceType.ORDERS,
            run_id=42,
            page_number=10,
            created_at=self.now,
            records=(self.record,),
        )
        with self.assertRaisesRegex(RuntimeError, "database failed"):
            with failed as page:
                failed_path = self._path(page.relative_path)
                self.assertTrue(failed_path.exists())
                raise RuntimeError("database failed")
        self.assertFalse(failed_path.exists())

        unretained = ArchivePage(
            archive_dir=self.archive_dir,
            master_key=self.master_key,
            provider=Provider.DOUDIAN,
            connection_id=7,
            resource=ResourceType.ORDERS,
            run_id=42,
            page_number=11,
            created_at=self.now,
            records=(self.record,),
        )
        with unretained as page:
            unretained_path = self._path(page.relative_path)
        self.assertFalse(unretained_path.exists())

        retained = ArchivePage(
            archive_dir=self.archive_dir,
            master_key=self.master_key,
            provider=Provider.DOUDIAN,
            connection_id=7,
            resource=ResourceType.ORDERS,
            run_id=42,
            page_number=12,
            created_at=self.now,
            records=(self.record,),
        )
        with retained as page:
            retained_path = self._path(page.relative_path)
            page.retain()
        self.assertTrue(retained_path.exists())

        committed = ArchivePage(
            archive_dir=self.archive_dir,
            master_key=self.master_key,
            provider=Provider.DOUDIAN,
            connection_id=7,
            resource=ResourceType.ORDERS,
            run_id=42,
            page_number=13,
            created_at=self.now,
            records=(self.record,),
        )
        with self.assertRaisesRegex(RuntimeError, "post-commit failure"):
            with committed as page:
                committed_path = self._path(page.relative_path)
                page.retain()
                raise RuntimeError("post-commit failure")
        self.assertTrue(committed_path.exists())

    def test_orphan_scan_deletes_only_unmanifested_files_older_than_one_hour(self):
        manifested = self._create(page_number=20)
        orphan = self._create(page_number=21)
        young = self._create(page_number=22)
        old_timestamp = (self.now - timedelta(hours=2)).timestamp()
        young_timestamp = (self.now - timedelta(minutes=30)).timestamp()
        os.utime(self._path(manifested.relative_path), (old_timestamp, old_timestamp))
        os.utime(self._path(orphan.relative_path), (old_timestamp, old_timestamp))
        os.utime(self._path(young.relative_path), (young_timestamp, young_timestamp))

        result = scan_orphan_archives(
            archive_dir=self.archive_dir,
            manifest_relative_paths={manifested.relative_path},
            now=self.now,
        )

        self.assertEqual(result.deleted_paths, (orphan.relative_path,))
        self.assertEqual(result.failure_codes, ())
        self.assertTrue(self._path(manifested.relative_path).exists())
        self.assertFalse(self._path(orphan.relative_path).exists())
        self.assertTrue(self._path(young.relative_path).exists())

    def test_retention_expiry_is_exactly_ninety_days(self):
        self.assertEqual(archive_expires_at(self.now), self.now + timedelta(days=90))
        with self.assertRaises(ValueError):
            archive_expires_at(self.now.replace(tzinfo=None))

    def test_retention_deletes_file_before_marking_and_audits_missing_files(self):
        engine, db = self._manifest_session()
        self.addCleanup(engine.dispose)
        self.addCleanup(db.close)
        existing_artifact = self._create(page_number=30)
        existing = self._add_manifest(
            db,
            relative_path=existing_artifact.relative_path,
            expires_at=self.now - timedelta(seconds=1),
            sha256=existing_artifact.sha256,
        )
        missing = self._add_manifest(
            db,
            relative_path=self._create(page_number=31).relative_path,
            expires_at=self.now - timedelta(seconds=1),
        )
        self._path(missing.relative_path).unlink()
        future = self._add_manifest(
            db,
            relative_path=self._create(page_number=32).relative_path,
            expires_at=self.now + timedelta(seconds=1),
        )
        db.flush()
        audit_events = []
        real_unlink = Path.unlink

        def observed_unlink(path, *args, **kwargs):
            if path == self._path(existing.relative_path):
                self.assertIsNone(existing.deleted_at)
            return real_unlink(path, *args, **kwargs)

        with patch.object(Path, "unlink", autospec=True, side_effect=observed_unlink):
            result = cleanup_expired_archives(
                db,
                archive_dir=self.archive_dir,
                now=self.now,
                audit_missing=lambda manifest_id, code: audit_events.append(
                    (manifest_id, code)
                ),
                enqueue_retry=lambda *_: self.fail("no retry expected"),
            )

        self.assertFalse(self._path(existing.relative_path).exists())
        self.assertEqual(existing.deleted_at, self.now)
        self.assertEqual(missing.deleted_at, self.now)
        self.assertIsNone(future.deleted_at)
        self.assertTrue(self._path(future.relative_path).exists())
        self.assertEqual(audit_events, [(missing.id, ArchiveAuditCode.FILE_MISSING)])
        self.assertEqual(result.deleted_count, 1)
        self.assertEqual(result.missing_count, 1)
        self.assertEqual(result.retry_count, 0)

    def test_retention_io_failure_preserves_manifest_and_queues_only_typed_error(self):
        engine, db = self._manifest_session()
        self.addCleanup(engine.dispose)
        self.addCleanup(db.close)
        artifact = self._create(page_number=40)
        manifest = self._add_manifest(
            db,
            relative_path=artifact.relative_path,
            expires_at=self.now - timedelta(seconds=1),
            sha256=artifact.sha256,
        )
        db.flush()
        raw_error = "raw-secret-sentinel-13800138000"
        retries = []

        with patch.object(Path, "unlink", side_effect=PermissionError(raw_error)):
            result = cleanup_expired_archives(
                db,
                archive_dir=self.archive_dir,
                now=self.now,
                audit_missing=lambda *_: self.fail("file exists"),
                enqueue_retry=lambda manifest_id, code: retries.append(
                    (manifest_id, code)
                ),
            )

        self.assertTrue(self._path(manifest.relative_path).exists())
        self.assertIsNone(manifest.deleted_at)
        self.assertEqual(
            retries,
            [(manifest.id, ArchiveCleanupErrorCode.DELETE_IO_FAILED)],
        )
        self.assertNotIn(raw_error, repr(retries))
        self.assertEqual(result.deleted_count, 0)
        self.assertEqual(result.missing_count, 0)
        self.assertEqual(result.retry_count, 1)

    def _manifest_session(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(
            engine,
            tables=[IntegrationArchiveManifest.__table__],
        )
        return engine, sessionmaker(bind=engine, expire_on_commit=False)()

    def _add_manifest(
        self,
        db,
        *,
        relative_path: str,
        expires_at: datetime,
        sha256: str = "a" * 64,
    ) -> IntegrationArchiveManifest:
        manifest = IntegrationArchiveManifest(
            run_id=42,
            page_number=len(db.new) + 1,
            provider=Provider.DOUDIAN,
            connection_id=7,
            resource_type=ResourceType.ORDERS,
            window_start=self.now - timedelta(hours=1),
            window_end=self.now,
            relative_path=relative_path,
            sha256=sha256,
            record_count=1,
            created_at=self.now - timedelta(days=91),
            expires_at=expires_at,
        )
        db.add(manifest)
        return manifest


if __name__ == "__main__":
    unittest.main()
