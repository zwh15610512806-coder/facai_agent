import hashlib
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

import database
import integrations.sync.queue as integration_queue
from database import Base
from integration_models import (
    IntegrationAuthorization,
    IntegrationConnection,
    IntegrationJob,
    IntegrationSyncCheckpoint,
)
from integrations.sync.queue import (
    JobErrorCode,
    acquire_checkpoint_for_job,
    acquire_checkpoint_lease,
    canonical_logical_request,
    claim_next_job,
    complete_job,
    enqueue_job,
    enqueue_refresh_authorization,
    fail_job,
    heartbeat_checkpoint,
    heartbeat_job,
    make_dedupe_key,
    start_job,
)
from integrations.types import (
    AuthorizationStatus,
    CheckpointStatus,
    ConnectionStatus,
    ConnectionType,
    JobStatus,
    JobType,
    Provider,
    ResourceType,
)
from tests.postgres_test_support import requires_disposable_postgres
from tests.test_integration_models import _require_disposable_postgres_url

QUEUE_TABLES = (
    IntegrationAuthorization.__table__,
    IntegrationConnection.__table__,
    IntegrationJob.__table__,
    IntegrationSyncCheckpoint.__table__,
)


@requires_disposable_postgres
class PersistentIntegrationQueueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = _require_disposable_postgres_url()
        cls.engine = database.create_database_engine(cls.database_url)
        cls.Session = sessionmaker(bind=cls.engine, expire_on_commit=False)
        cls.addClassCleanup(cls._cleanup)
        cls._reset_schema()

    @classmethod
    def _cleanup(cls):
        try:
            Base.metadata.drop_all(cls.engine, tables=QUEUE_TABLES, checkfirst=True)
        finally:
            cls.engine.dispose()

    @classmethod
    def _reset_schema(cls):
        Base.metadata.drop_all(cls.engine, tables=QUEUE_TABLES, checkfirst=True)
        Base.metadata.create_all(cls.engine, tables=QUEUE_TABLES, checkfirst=False)

    def setUp(self):
        self._reset_schema()
        self.now = datetime(2026, 7, 14, 2, 0, tzinfo=UTC)

    def _enqueue(
        self,
        session,
        *,
        target_id="connection-1",
        logical_request=None,
        payload=None,
        available_at=None,
        priority=0,
        job_type=JobType.SYNC_RESOURCE,
        manual=False,
        logical_request_id=None,
        max_attempts=6,
    ):
        return enqueue_job(
            session,
            job_type=job_type,
            target_id=target_id,
            logical_request=(
                logical_request
                if logical_request is not None
                else {"resource": ResourceType.ORDERS.value, "window": "2026-07-13"}
            ),
            payload=(payload if payload is not None else self._sync_payload()),
            available_at=available_at or self.now,
            priority=priority,
            manual=manual,
            logical_request_id=logical_request_id,
            max_attempts=max_attempts,
        )

    def _sync_payload(
        self,
        *,
        connection_id=1,
        resource_type=ResourceType.ORDERS,
        window_start=None,
        window_end=None,
        checkpoint_id=None,
        cursor=None,
    ):
        payload = {
            "connection_id": connection_id,
            "resource_type": resource_type.value,
            "window_start": (window_start or (self.now - timedelta(days=1))).isoformat(),
            "window_end": (window_end or self.now).isoformat(),
        }
        if checkpoint_id is not None:
            payload["checkpoint_id"] = checkpoint_id
        if cursor is not None:
            payload["cursor"] = cursor
        return payload

    def _seed_connection(self):
        session = self.Session()
        try:
            authorization = IntegrationAuthorization(
                provider=Provider.DOUDIAN,
                external_subject_id="queue-subject",
                scopes=["shop.read"],
                access_token_ciphertext="opaque-ciphertext",
                access_token_tail="0000",
                status=AuthorizationStatus.ACTIVE,
                last_authorized_at=self.now,
            )
            session.add(authorization)
            session.flush()
            connection = IntegrationConnection(
                authorization_id=authorization.id,
                provider=Provider.DOUDIAN,
                connection_type=ConnectionType.SHOP,
                external_account_id="queue-shop",
                display_name="Queue test shop",
                status=ConnectionStatus.ACTIVE,
                capability_report={},
            )
            session.add(connection)
            session.commit()
            return authorization.id, connection.id
        finally:
            session.close()

    def test_canonical_request_is_sorted_compact_json_and_hashes_contract_fields(self):
        logical_request = {"z": [3, 2], "a": {"y": True, "x": None}}

        canonical = canonical_logical_request(logical_request)

        self.assertEqual(
            canonical,
            json.dumps(
                logical_request,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ),
        )
        expected = hashlib.sha256(
            (
                f"{JobType.SYNC_RESOURCE.value}\nconnection-7\n{canonical}"
            ).encode()
        ).hexdigest()
        self.assertEqual(
            make_dedupe_key(
                JobType.SYNC_RESOURCE,
                "connection-7",
                logical_request,
            ),
            expected,
        )

    def test_enqueue_same_logical_request_keeps_one_row_and_only_pulls_due_time_earlier(self):
        session = self.Session()
        try:
            later = self.now + timedelta(hours=1)
            first = self._enqueue(
                session,
                available_at=later,
                payload=self._sync_payload(cursor={"marker": "original"}),
                priority=2,
            )
            session.commit()

            second = self._enqueue(
                session,
                available_at=self.now,
                payload=self._sync_payload(cursor={"marker": "replacement"}),
                priority=99,
            )
            session.commit()
            session.refresh(first)

            self.assertEqual(second.id, first.id)
            self.assertEqual(
                session.scalar(select(func.count()).select_from(IntegrationJob)),
                1,
            )
            self.assertEqual(first.available_at, self.now)
            self.assertEqual(first.payload["cursor"]["marker"], "original")
            self.assertEqual(first.priority, 2)
        finally:
            session.close()

    def test_concurrent_enqueue_of_the_same_request_returns_one_postgres_row(self):
        barrier = Barrier(2)

        def enqueue_from_independent_session():
            session = self.Session()
            try:
                barrier.wait(timeout=5)
                job = self._enqueue(session)
                session.commit()
                return job.id
            finally:
                session.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            job_ids = list(executor.map(lambda _: enqueue_from_independent_session(), range(2)))

        session = self.Session()
        try:
            self.assertEqual(job_ids[0], job_ids[1])
            self.assertEqual(
                session.scalar(select(func.count()).select_from(IntegrationJob)),
                1,
            )
        finally:
            session.close()

    def test_enqueue_conflict_never_resurrects_a_completed_job(self):
        session = self.Session()
        try:
            job = self._enqueue(session)
            session.commit()
            claimed = claim_next_job(
                session,
                owner="worker-a",
                now=self.now,
                lease_duration=timedelta(minutes=2),
            )
            self.assertEqual(claimed.id, job.id)
            self.assertTrue(
                start_job(
                    session,
                    job_id=job.id,
                    owner="worker-a",
                    now=self.now,
                )
            )
            self.assertTrue(
                complete_job(
                    session,
                    job_id=job.id,
                    owner="worker-a",
                    now=self.now + timedelta(seconds=5),
                )
            )
            session.commit()

            duplicate = self._enqueue(
                session,
                available_at=self.now - timedelta(days=1),
            )
            session.commit()
            session.refresh(job)

            self.assertEqual(duplicate.id, job.id)
            self.assertEqual(job.status, JobStatus.SUCCEEDED)
            self.assertIsNotNone(job.completed_at)
        finally:
            session.close()

    def test_manual_requests_require_and_dedupe_by_distinct_logical_request_id(self):
        session = self.Session()
        try:
            with self.assertRaisesRegex(ValueError, "logical_request_id"):
                self._enqueue(session, manual=True)

            first = self._enqueue(
                session,
                manual=True,
                logical_request_id="manual-001",
            )
            duplicate = self._enqueue(
                session,
                manual=True,
                logical_request_id="manual-001",
            )
            second = self._enqueue(
                session,
                manual=True,
                logical_request_id="manual-002",
            )
            session.commit()

            self.assertEqual(first.id, duplicate.id)
            self.assertNotEqual(first.id, second.id)
            self.assertEqual(
                session.scalar(select(func.count()).select_from(IntegrationJob)),
                2,
            )
        finally:
            session.close()

    def test_enqueue_uses_the_callers_transaction_without_committing(self):
        writer = self.Session()
        observer = self.Session()
        try:
            self._enqueue(writer)

            self.assertTrue(writer.in_transaction())
            self.assertEqual(
                observer.scalar(select(func.count()).select_from(IntegrationJob)),
                0,
            )
            writer.commit()
            observer.rollback()
            self.assertEqual(
                observer.scalar(select(func.count()).select_from(IntegrationJob)),
                1,
            )
        finally:
            writer.rollback()
            observer.rollback()
            writer.close()
            observer.close()

    def test_refresh_jobs_dedupe_by_authorization_id(self):
        session = self.Session()
        try:
            first = enqueue_refresh_authorization(
                session,
                authorization_id=41,
                payload={"authorization_id": 41},
                available_at=self.now,
                logical_request={"connection_id": 1001},
            )
            same_authorization = enqueue_refresh_authorization(
                session,
                authorization_id=41,
                payload={"authorization_id": 41},
                available_at=self.now,
                logical_request={"connection_id": 1002},
            )
            other_authorization = enqueue_refresh_authorization(
                session,
                authorization_id=42,
                payload={"authorization_id": 42},
                available_at=self.now,
                logical_request={"connection_id": 1001},
            )
            session.commit()

            self.assertEqual(first.id, same_authorization.id)
            self.assertNotEqual(first.id, other_authorization.id)
            self.assertEqual(first.job_type, JobType.REFRESH_AUTHORIZATION)
        finally:
            session.close()

    def test_refresh_enqueue_validates_payload_and_preserves_an_empty_logical_request(self):
        session = self.Session()
        try:
            with self.assertRaisesRegex(ValueError, "payload"):
                enqueue_refresh_authorization(
                    session,
                    authorization_id=41,
                    payload=None,
                    available_at=self.now,
                )

            empty_request = enqueue_refresh_authorization(
                session,
                authorization_id=41,
                payload={"authorization_id": 41},
                logical_request={},
                available_at=self.now,
            )
            default_request = enqueue_refresh_authorization(
                session,
                authorization_id=41,
                payload={"authorization_id": 41},
                available_at=self.now,
            )
            session.commit()

            self.assertEqual(empty_request.id, default_request.id)
        finally:
            session.rollback()
            session.close()

    def test_skip_locked_gives_two_workers_different_due_jobs(self):
        seed = self.Session()
        try:
            first = self._enqueue(
                seed,
                target_id="connection-1",
                logical_request={"resource": "orders"},
                priority=5,
            )
            second = self._enqueue(
                seed,
                target_id="connection-2",
                logical_request={"resource": "products"},
                priority=1,
            )
            seed.commit()
        finally:
            seed.close()

        worker_a = self.Session()
        worker_b = self.Session()
        try:
            claimed_a = claim_next_job(
                worker_a,
                owner="worker-a",
                now=self.now,
                lease_duration=timedelta(minutes=2),
            )
            claimed_b = claim_next_job(
                worker_b,
                owner="worker-b",
                now=self.now,
                lease_duration=timedelta(minutes=2),
            )

            self.assertEqual(claimed_a.id, first.id)
            self.assertEqual(claimed_b.id, second.id)
            self.assertNotEqual(claimed_a.id, claimed_b.id)
        finally:
            worker_a.rollback()
            worker_b.rollback()
            worker_a.close()
            worker_b.close()

    def test_skip_locked_never_leases_the_same_single_job_twice(self):
        seed = self.Session()
        try:
            self._enqueue(seed)
            seed.commit()
        finally:
            seed.close()

        worker_a = self.Session()
        worker_b = self.Session()
        try:
            self.assertIsNotNone(
                claim_next_job(
                    worker_a,
                    owner="worker-a",
                    now=self.now,
                    lease_duration=timedelta(minutes=2),
                )
            )
            self.assertIsNone(
                claim_next_job(
                    worker_b,
                    owner="worker-b",
                    now=self.now,
                    lease_duration=timedelta(minutes=2),
                )
            )
        finally:
            worker_a.rollback()
            worker_b.rollback()
            worker_a.close()
            worker_b.close()

    def test_live_lease_is_not_claimable_but_expired_lease_is_reclaimed(self):
        session = self.Session()
        try:
            job = self._enqueue(session)
            session.commit()
            claim_next_job(
                session,
                owner="worker-a",
                now=self.now,
                lease_duration=timedelta(minutes=2),
            )
            session.commit()
        finally:
            session.close()

        challenger = self.Session()
        try:
            self.assertIsNone(
                claim_next_job(
                    challenger,
                    owner="worker-b",
                    now=self.now + timedelta(minutes=1),
                    lease_duration=timedelta(minutes=2),
                )
            )
            challenger.rollback()

            reclaimed = claim_next_job(
                challenger,
                owner="worker-b",
                now=self.now + timedelta(minutes=3),
                lease_duration=timedelta(minutes=2),
            )
            self.assertEqual(reclaimed.id, job.id)
            self.assertEqual(reclaimed.lease_owner, "worker-b")
        finally:
            challenger.rollback()
            challenger.close()

    def test_heartbeat_only_extends_a_live_lease_for_its_owner(self):
        session = self.Session()
        try:
            job = self._enqueue(session)
            session.commit()
            claim_next_job(
                session,
                owner="worker-a",
                now=self.now,
                lease_duration=timedelta(minutes=2),
            )
            session.commit()

            self.assertFalse(
                heartbeat_job(
                    session,
                    job_id=job.id,
                    owner="worker-b",
                    now=self.now + timedelta(minutes=1),
                    lease_duration=timedelta(minutes=4),
                )
            )
            session.commit()
            session.refresh(job)
            self.assertEqual(
                job.lease_expires_at,
                self.now + timedelta(minutes=2),
            )

            self.assertTrue(
                heartbeat_job(
                    session,
                    job_id=job.id,
                    owner="worker-a",
                    now=self.now + timedelta(minutes=1),
                    lease_duration=timedelta(minutes=4),
                )
            )
            session.commit()
            session.refresh(job)
            self.assertEqual(
                job.lease_expires_at,
                self.now + timedelta(minutes=5),
            )
            self.assertEqual(job.heartbeat_at, self.now + timedelta(minutes=1))
        finally:
            session.close()

    def test_heartbeat_never_shortens_an_existing_job_lease(self):
        session = self.Session()
        try:
            job = self._enqueue(session)
            session.commit()
            claim_next_job(
                session,
                owner="worker-a",
                now=self.now,
                lease_duration=timedelta(minutes=10),
            )
            session.commit()

            self.assertTrue(
                heartbeat_job(
                    session,
                    job_id=job.id,
                    owner="worker-a",
                    now=self.now + timedelta(minutes=1),
                    lease_duration=timedelta(minutes=2),
                )
            )
            session.commit()
            session.refresh(job)
            self.assertEqual(
                job.lease_expires_at,
                self.now + timedelta(minutes=10),
            )
        finally:
            session.close()

    def test_checkpoint_lease_serializes_connection_resource_and_window(self):
        _, connection_id = self._seed_connection()
        window_start = self.now - timedelta(days=1)
        window_end = self.now
        holder = self.Session()
        challenger = self.Session()
        try:
            checkpoint = acquire_checkpoint_lease(
                holder,
                connection_id=connection_id,
                resource_type=ResourceType.ORDERS,
                window_start=window_start,
                window_end=window_end,
                owner="worker-a",
                now=self.now,
                lease_duration=timedelta(minutes=5),
            )
            holder.commit()

            denied = acquire_checkpoint_lease(
                challenger,
                connection_id=connection_id,
                resource_type=ResourceType.ORDERS,
                window_start=window_start,
                window_end=window_end,
                owner="worker-b",
                now=self.now + timedelta(minutes=1),
                lease_duration=timedelta(minutes=5),
            )
            self.assertIsNone(denied)
            challenger.rollback()

            reclaimed = acquire_checkpoint_lease(
                challenger,
                connection_id=connection_id,
                resource_type=ResourceType.ORDERS,
                window_start=window_start,
                window_end=window_end,
                owner="worker-b",
                now=self.now + timedelta(minutes=6),
                lease_duration=timedelta(minutes=5),
            )
            self.assertEqual(reclaimed.id, checkpoint.id)
            self.assertEqual(reclaimed.lease_owner, "worker-b")
            self.assertEqual(reclaimed.status, CheckpointStatus.RUNNING)
        finally:
            holder.rollback()
            challenger.rollback()
            holder.close()
            challenger.close()

    def test_checkpoint_heartbeat_only_extends_for_the_current_owner(self):
        _, connection_id = self._seed_connection()
        session = self.Session()
        try:
            checkpoint = acquire_checkpoint_lease(
                session,
                connection_id=connection_id,
                resource_type=ResourceType.PRODUCTS,
                window_start=self.now - timedelta(days=1),
                window_end=self.now,
                owner="worker-a",
                now=self.now,
                lease_duration=timedelta(minutes=2),
            )
            session.commit()

            self.assertFalse(
                heartbeat_checkpoint(
                    session,
                    checkpoint_id=checkpoint.id,
                    owner="worker-b",
                    now=self.now + timedelta(minutes=1),
                    lease_duration=timedelta(minutes=4),
                )
            )
            self.assertTrue(
                heartbeat_checkpoint(
                    session,
                    checkpoint_id=checkpoint.id,
                    owner="worker-a",
                    now=self.now + timedelta(minutes=1),
                    lease_duration=timedelta(minutes=4),
                )
            )
            session.commit()
            session.refresh(checkpoint)
            self.assertEqual(
                checkpoint.lease_expires_at,
                self.now + timedelta(minutes=5),
            )

            same_owner = acquire_checkpoint_lease(
                session,
                connection_id=connection_id,
                resource_type=ResourceType.PRODUCTS,
                window_start=self.now - timedelta(days=1),
                window_end=self.now,
                owner="worker-a",
                now=self.now + timedelta(minutes=2),
                lease_duration=timedelta(minutes=1),
            )
            session.commit()
            session.refresh(same_owner)
            self.assertEqual(
                same_owner.lease_expires_at,
                self.now + timedelta(minutes=5),
            )

            self.assertTrue(
                heartbeat_checkpoint(
                    session,
                    checkpoint_id=checkpoint.id,
                    owner="worker-a",
                    now=self.now + timedelta(minutes=2),
                    lease_duration=timedelta(minutes=1),
                )
            )
            session.commit()
            session.refresh(checkpoint)
            self.assertEqual(
                checkpoint.lease_expires_at,
                self.now + timedelta(minutes=5),
            )
        finally:
            session.close()

    def test_acquiring_checkpoint_for_job_starts_it_and_consumes_one_attempt(self):
        _, connection_id = self._seed_connection()
        session = self.Session()
        try:
            job = self._enqueue(session, target_id=connection_id)
            session.commit()
            claim_next_job(
                session,
                owner="worker-a",
                now=self.now,
                lease_duration=timedelta(minutes=2),
            )

            checkpoint = acquire_checkpoint_for_job(
                session,
                job_id=job.id,
                connection_id=connection_id,
                resource_type=ResourceType.ORDERS,
                window_start=self.now - timedelta(days=1),
                window_end=self.now,
                owner="worker-a",
                now=self.now + timedelta(seconds=1),
                lease_duration=timedelta(minutes=5),
                jitter_seconds=3,
            )
            session.commit()
            session.refresh(job)

            self.assertIsNotNone(checkpoint)
            self.assertEqual(job.status, JobStatus.RUNNING)
            self.assertEqual(job.attempts, 1)
            self.assertEqual(job.lease_owner, "worker-a")
        finally:
            session.close()

    def test_resource_lease_contention_requeues_without_consuming_an_attempt(self):
        _, connection_id = self._seed_connection()
        window_start = self.now - timedelta(days=1)
        window_end = self.now
        holder = self.Session()
        try:
            acquire_checkpoint_lease(
                holder,
                connection_id=connection_id,
                resource_type=ResourceType.ORDERS,
                window_start=window_start,
                window_end=window_end,
                owner="worker-a",
                now=self.now,
                lease_duration=timedelta(minutes=5),
            )
            holder.commit()
        finally:
            holder.close()

        worker = self.Session()
        try:
            job = self._enqueue(worker, target_id=connection_id)
            worker.commit()
            claim_next_job(
                worker,
                owner="worker-b",
                now=self.now,
                lease_duration=timedelta(minutes=2),
            )

            checkpoint = acquire_checkpoint_for_job(
                worker,
                job_id=job.id,
                connection_id=connection_id,
                resource_type=ResourceType.ORDERS,
                window_start=window_start,
                window_end=window_end,
                owner="worker-b",
                now=self.now + timedelta(minutes=1),
                lease_duration=timedelta(minutes=5),
                jitter_seconds=3,
            )
            worker.commit()
            worker.refresh(job)

            self.assertIsNone(checkpoint)
            self.assertEqual(job.status, JobStatus.QUEUED)
            self.assertEqual(job.attempts, 0)
            self.assertEqual(job.available_at, self.now + timedelta(minutes=1, seconds=3))
            self.assertIsNone(job.lease_owner)
            self.assertIsNone(job.lease_expires_at)
            self.assertIsNone(job.heartbeat_at)
        finally:
            worker.close()

    def test_start_complete_and_fail_require_owner_and_clear_lease_fields(self):
        session = self.Session()
        try:
            succeeded = self._enqueue(session, target_id="success")
            failed = self._enqueue(session, target_id="failure")
            session.commit()

            claim_next_job(
                session,
                owner="worker-a",
                now=self.now,
                lease_duration=timedelta(minutes=2),
            )
            self.assertFalse(
                start_job(
                    session,
                    job_id=succeeded.id,
                    owner="worker-b",
                    now=self.now,
                )
            )
            self.assertTrue(
                start_job(
                    session,
                    job_id=succeeded.id,
                    owner="worker-a",
                    now=self.now,
                )
            )
            self.assertEqual(succeeded.attempts, 1)
            self.assertFalse(
                complete_job(
                    session,
                    job_id=succeeded.id,
                    owner="worker-b",
                    now=self.now + timedelta(seconds=5),
                )
            )
            self.assertTrue(
                complete_job(
                    session,
                    job_id=succeeded.id,
                    owner="worker-a",
                    now=self.now + timedelta(seconds=5),
                )
            )
            session.commit()
            session.refresh(succeeded)
            self.assertEqual(succeeded.status, JobStatus.SUCCEEDED)
            self.assertIsNone(succeeded.lease_owner)
            self.assertIsNone(succeeded.lease_expires_at)
            self.assertIsNone(succeeded.heartbeat_at)

            claim_next_job(
                session,
                owner="worker-c",
                now=self.now + timedelta(seconds=10),
                lease_duration=timedelta(minutes=2),
            )
            self.assertTrue(
                start_job(
                    session,
                    job_id=failed.id,
                    owner="worker-c",
                    now=self.now + timedelta(seconds=10),
                )
            )
            self.assertTrue(
                fail_job(
                    session,
                    job_id=failed.id,
                    owner="worker-c",
                    error_code=JobErrorCode.PROVIDER_RATE_LIMITED,
                    error_summary=integration_queue.JobErrorSummary.PROVIDER_THROTTLED,
                    retryable=False,
                    now=self.now + timedelta(seconds=15),
                )
            )
            session.commit()
            session.refresh(failed)

            self.assertEqual(failed.status, JobStatus.FAILED)
            self.assertEqual(
                failed.last_error_code,
                JobErrorCode.PROVIDER_RATE_LIMITED.value,
            )
            self.assertEqual(
                failed.last_error_summary,
                integration_queue.JobErrorSummary.PROVIDER_THROTTLED.value,
            )
            self.assertIsNone(failed.lease_owner)
            self.assertIsNone(failed.lease_expires_at)
            self.assertIsNone(failed.heartbeat_at)
            self.assertIsNotNone(failed.completed_at)
        finally:
            session.close()

    def test_fail_rejects_free_form_error_codes(self):
        session = self.Session()
        try:
            job = self._enqueue(session)
            session.commit()
            claim_next_job(
                session,
                owner="worker-a",
                now=self.now,
                lease_duration=timedelta(minutes=2),
            )
            start_job(
                session,
                job_id=job.id,
                owner="worker-a",
                now=self.now,
            )

            with self.assertRaisesRegex(ValueError, "JobErrorCode"):
                fail_job(
                    session,
                    job_id=job.id,
                    owner="worker-a",
                    error_code="provider dumped a secret",
                    error_summary=integration_queue.JobErrorSummary.INTERNAL_WORKER_FAILURE,
                    retryable=False,
                    now=self.now + timedelta(seconds=1),
                )
        finally:
            session.rollback()
            session.close()

    def test_expired_owner_cannot_complete_or_fail_a_job(self):
        session = self.Session()
        try:
            complete_candidate = self._enqueue(session, target_id="expired-complete")
            fail_candidate = self._enqueue(session, target_id="expired-fail")
            session.commit()

            claim_next_job(
                session,
                owner="worker-a",
                now=self.now,
                lease_duration=timedelta(minutes=1),
            )
            start_job(
                session,
                job_id=complete_candidate.id,
                owner="worker-a",
                now=self.now,
            )
            session.commit()
            self.assertFalse(
                complete_job(
                    session,
                    job_id=complete_candidate.id,
                    owner="worker-a",
                    now=self.now + timedelta(minutes=2),
                )
            )

            claim_next_job(
                session,
                owner="worker-b",
                now=self.now,
                lease_duration=timedelta(minutes=1),
            )
            start_job(
                session,
                job_id=fail_candidate.id,
                owner="worker-b",
                now=self.now,
            )
            session.commit()
            self.assertFalse(
                fail_job(
                    session,
                    job_id=fail_candidate.id,
                    owner="worker-b",
                    error_code=JobErrorCode.INTERNAL_ERROR,
                    error_summary=integration_queue.JobErrorSummary.INTERNAL_WORKER_FAILURE,
                    retryable=False,
                    now=self.now + timedelta(minutes=2),
                )
            )
        finally:
            session.rollback()
            session.close()

    def test_retryable_failure_clears_lease_and_becomes_due_without_completing(self):
        session = self.Session()
        try:
            job = self._enqueue(session)
            session.commit()
            claim_next_job(
                session,
                owner="worker-a",
                now=self.now,
                lease_duration=timedelta(minutes=2),
            )
            start_job(
                session,
                job_id=job.id,
                owner="worker-a",
                now=self.now,
            )
            self.assertTrue(
                fail_job(
                    session,
                    job_id=job.id,
                    owner="worker-a",
                    error_code=JobErrorCode.TRANSIENT_PROVIDER_ERROR,
                    error_summary=integration_queue.JobErrorSummary.TRANSIENT_PROVIDER_FAILURE,
                    retryable=True,
                    now=self.now + timedelta(seconds=10),
                    retry_delay=timedelta(seconds=30),
                )
            )
            session.commit()
            session.refresh(job)

            self.assertEqual(job.status, JobStatus.RETRY_WAIT)
            self.assertEqual(job.available_at, self.now + timedelta(seconds=40))
            self.assertIsNone(job.completed_at)
            self.assertIsNone(job.lease_owner)
        finally:
            session.close()

    def test_every_job_type_accepts_only_its_strict_identifier_payload(self):
        cases = (
            (JobType.SYNC_RESOURCE, self._sync_payload()),
            (JobType.REFRESH_AUTHORIZATION, {"authorization_id": 11}),
            (
                JobType.PROCESS_EVENT,
                {"event_inbox_id": 12, "connection_id": 1},
            ),
            (JobType.ARCHIVE_CLEANUP, {"archive_manifest_id": 13}),
            (JobType.EXPORT, {"export_job_id": 14}),
            (JobType.PURGE_CONNECTION, {"connection_id": 15}),
        )
        session = self.Session()
        try:
            for index, (job_type, payload) in enumerate(cases, start=1):
                with self.subTest(job_type=job_type):
                    enqueue_job(
                        session,
                        job_type=job_type,
                        target_id=index,
                        logical_request={"slot": index},
                        payload=payload,
                        available_at=self.now,
                    )
            session.commit()
            self.assertEqual(
                session.scalar(select(func.count()).select_from(IntegrationJob)),
                len(cases),
            )
        finally:
            session.close()

    def test_job_payloads_reject_unknown_fields_invalid_ids_enums_and_windows(self):
        invalid_cases = (
            (
                JobType.PURGE_CONNECTION,
                {"connection_id": 1, "operator_note": "delete it"},
            ),
            (JobType.EXPORT, {"export_job_id": "14"}),
            (
                JobType.PROCESS_EVENT,
                {"event_inbox_id": 12, "connection_id": 0},
            ),
            (
                JobType.SYNC_RESOURCE,
                {
                    **self._sync_payload(),
                    "resource_type": "not_a_resource",
                },
            ),
            (
                JobType.SYNC_RESOURCE,
                {
                    **self._sync_payload(),
                    "window_start": "2026-07-13T02:00:00",
                },
            ),
            (
                JobType.SYNC_RESOURCE,
                self._sync_payload(
                    window_start=self.now,
                    window_end=self.now - timedelta(seconds=1),
                ),
            ),
        )
        session = self.Session()
        try:
            for index, (job_type, payload) in enumerate(invalid_cases, start=1):
                with self.subTest(job_type=job_type, payload=payload):
                    with self.assertRaises(ValueError):
                        enqueue_job(
                            session,
                            job_type=job_type,
                            target_id=index,
                            logical_request={"slot": index},
                            payload=payload,
                            available_at=self.now,
                        )
        finally:
            session.rollback()
            session.close()

    def test_cursor_metadata_rejects_embedded_json_query_header_and_camelcase_secrets(self):
        unsafe_values = (
            '{"accessToken":"json-secret"}',
            'Authorization: Bearer "quoted multi word secret"',
            "https://provider.invalid/page?client_secret=query-secret&cursor=1",
            "X-Api-Key: header-secret",
            "refreshToken=camel-secret",
            "%7B%22appSecret%22%3A%22encoded-secret%22%7D",
            "%25257B%252522appSecret%252522%25253A%252522encoded-secret%252522%25257D",
            "buyer@example.com",
            "13800138000",
            "440524188001010014",
        )
        session = self.Session()
        try:
            for index, unsafe_value in enumerate(unsafe_values, start=1):
                with self.subTest(unsafe_value=unsafe_value):
                    with self.assertRaises(ValueError):
                        self._enqueue(
                            session,
                            target_id=f"unsafe-{index}",
                            logical_request={"slot": index},
                            payload=self._sync_payload(
                                cursor={"page": index, "continuation": unsafe_value}
                            ),
                        )
        finally:
            session.rollback()
            session.close()

    def test_cursor_metadata_rejects_direct_authorization_and_api_key_fields(self):
        unsafe_cursors = (
            {"Authorization": "Basic opaque-credential"},
            {"apiKey": "opaque-credential"},
            {"nested": {"proxyAuthorization": "Basic opaque-credential"}},
        )
        session = self.Session()
        try:
            for index, cursor in enumerate(unsafe_cursors, start=1):
                with self.subTest(cursor=cursor):
                    with self.assertRaises(ValueError):
                        self._enqueue(
                            session,
                            target_id=f"unsafe-key-{index}",
                            logical_request={"slot": index},
                            payload=self._sync_payload(cursor=cursor),
                        )
        finally:
            session.rollback()
            session.close()

    def test_raw_error_summaries_are_always_rejected_and_never_persisted(self):
        raw_summaries = (
            '{"accessToken":"json-secret"}',
            'Authorization: Bearer "quoted multi word secret"',
            "https://provider.invalid/error?client_secret=query-secret",
            "X-Api-Key: header-secret",
            "refreshToken=camel-secret",
            "ordinary upstream exception text",
        )
        session = self.Session()
        try:
            job = self._enqueue(session)
            session.commit()
            claim_next_job(
                session,
                owner="worker-a",
                now=self.now,
                lease_duration=timedelta(minutes=5),
            )
            start_job(
                session,
                job_id=job.id,
                owner="worker-a",
                now=self.now,
            )
            for raw_summary in raw_summaries:
                with self.subTest(raw_summary=raw_summary):
                    with self.assertRaisesRegex(ValueError, "JobErrorSummary"):
                        fail_job(
                            session,
                            job_id=job.id,
                            owner="worker-a",
                            error_code=JobErrorCode.INTERNAL_ERROR,
                            error_summary=raw_summary,
                            retryable=False,
                            now=self.now + timedelta(seconds=1),
                        )
            session.flush()
            session.refresh(job)
            self.assertEqual(job.status, JobStatus.RUNNING)
            self.assertIsNone(job.last_error_summary)
        finally:
            session.rollback()
            session.close()

    def test_typed_error_code_and_summary_must_be_an_allowlisted_pair(self):
        session = self.Session()
        try:
            job = self._enqueue(session)
            session.commit()
            claim_next_job(
                session,
                owner="worker-a",
                now=self.now,
                lease_duration=timedelta(minutes=5),
            )
            start_job(
                session,
                job_id=job.id,
                owner="worker-a",
                now=self.now,
            )
            with self.assertRaises(ValueError):
                fail_job(
                    session,
                    job_id=job.id,
                    owner="worker-a",
                    error_code=JobErrorCode.PROVIDER_RATE_LIMITED,
                    error_summary=integration_queue.JobErrorSummary.INTERNAL_WORKER_FAILURE,
                    retryable=False,
                    now=self.now + timedelta(seconds=1),
                )
        finally:
            session.rollback()
            session.close()

    def test_connection_resource_lease_is_global_across_checkpoint_windows(self):
        _, connection_id = self._seed_connection()
        holder = self.Session()
        challenger = self.Session()
        try:
            first = acquire_checkpoint_lease(
                holder,
                connection_id=connection_id,
                resource_type=ResourceType.ORDERS,
                window_start=self.now - timedelta(days=2),
                window_end=self.now - timedelta(days=1),
                owner="worker-a",
                now=self.now,
                lease_duration=timedelta(minutes=5),
            )
            holder.commit()

            second_window = acquire_checkpoint_lease(
                challenger,
                connection_id=connection_id,
                resource_type=ResourceType.ORDERS,
                window_start=self.now - timedelta(days=1),
                window_end=self.now,
                owner="worker-b",
                now=self.now + timedelta(minutes=1),
                lease_duration=timedelta(minutes=5),
            )
            self.assertIsNotNone(first)
            self.assertIsNone(second_window)
        finally:
            holder.rollback()
            challenger.rollback()
            holder.close()
            challenger.close()

    def test_concurrent_different_windows_yield_one_global_resource_lease(self):
        _, connection_id = self._seed_connection()
        barrier = Barrier(2)

        def acquire_from_independent_session(index):
            session = self.Session()
            try:
                barrier.wait(timeout=5)
                checkpoint = acquire_checkpoint_lease(
                    session,
                    connection_id=connection_id,
                    resource_type=ResourceType.ORDERS,
                    window_start=self.now - timedelta(days=index + 1),
                    window_end=self.now - timedelta(days=index),
                    owner=f"worker-{index}",
                    now=self.now,
                    lease_duration=timedelta(minutes=5),
                )
                session.commit()
                return checkpoint.id if checkpoint is not None else None
            finally:
                session.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            checkpoint_ids = list(executor.map(acquire_from_independent_session, (0, 1)))

        self.assertEqual(sum(identifier is not None for identifier in checkpoint_ids), 1)

    def test_expired_final_attempt_running_and_leased_jobs_are_failed_and_released(self):
        session = self.Session()
        try:
            running = self._enqueue(session, target_id="final-running", max_attempts=1)
            leased = self._enqueue(session, target_id="final-leased", max_attempts=1)
            session.commit()

            claim_next_job(
                session,
                owner="worker-a",
                now=self.now,
                lease_duration=timedelta(minutes=1),
            )
            start_job(
                session,
                job_id=running.id,
                owner="worker-a",
                now=self.now,
            )
            claim_next_job(
                session,
                owner="worker-b",
                now=self.now,
                lease_duration=timedelta(minutes=1),
            )
            leased.attempts = leased.max_attempts
            session.commit()

            self.assertIsNone(
                claim_next_job(
                    session,
                    owner="worker-c",
                    now=self.now + timedelta(minutes=2),
                    lease_duration=timedelta(minutes=1),
                )
            )
            session.commit()
            session.refresh(running)
            session.refresh(leased)
            for job in (running, leased):
                with self.subTest(job_id=job.id):
                    self.assertEqual(job.status, JobStatus.FAILED)
                    self.assertIsNone(job.lease_owner)
                    self.assertIsNone(job.lease_expires_at)
                    self.assertIsNone(job.heartbeat_at)
                    self.assertEqual(
                        job.last_error_code,
                        integration_queue.JobErrorCode.MAX_ATTEMPTS_EXHAUSTED.value,
                    )
                    self.assertEqual(
                        job.last_error_summary,
                        integration_queue.JobErrorSummary.FINAL_ATTEMPT_LEASE_EXPIRED.value,
                    )
                    self.assertIsNotNone(job.completed_at)
        finally:
            session.close()

    def test_expired_running_job_reclaims_through_retry_without_losing_attempt_count(self):
        session = self.Session()
        try:
            job = self._enqueue(session, max_attempts=3)
            session.commit()
            claim_next_job(
                session,
                owner="worker-a",
                now=self.now,
                lease_duration=timedelta(minutes=1),
            )
            start_job(
                session,
                job_id=job.id,
                owner="worker-a",
                now=self.now,
            )
            session.commit()

            reclaimed = claim_next_job(
                session,
                owner="worker-b",
                now=self.now + timedelta(minutes=2),
                lease_duration=timedelta(minutes=1),
            )
            session.commit()
            session.refresh(job)
            self.assertEqual(reclaimed.id, job.id)
            self.assertEqual(job.status, JobStatus.LEASED)
            self.assertEqual(job.attempts, 1)
            self.assertEqual(
                job.last_error_code,
                integration_queue.JobErrorCode.LEASE_EXPIRED.value,
            )
        finally:
            session.close()

    def test_retry_wait_checkpoint_is_not_acquired_early_and_clears_due_time(self):
        _, connection_id = self._seed_connection()
        session = self.Session()
        try:
            checkpoint = acquire_checkpoint_lease(
                session,
                connection_id=connection_id,
                resource_type=ResourceType.REFUNDS,
                window_start=self.now - timedelta(days=1),
                window_end=self.now,
                owner="worker-a",
                now=self.now,
                lease_duration=timedelta(minutes=1),
            )
            checkpoint.status = CheckpointStatus.RETRY_WAIT
            checkpoint.next_retry_at = self.now + timedelta(minutes=10)
            checkpoint.lease_owner = None
            checkpoint.lease_expires_at = None
            checkpoint.heartbeat_at = None
            session.commit()

            early = acquire_checkpoint_lease(
                session,
                connection_id=connection_id,
                resource_type=ResourceType.REFUNDS,
                window_start=self.now - timedelta(days=1),
                window_end=self.now,
                owner="worker-b",
                now=self.now + timedelta(minutes=5),
                lease_duration=timedelta(minutes=1),
            )
            self.assertIsNone(early)
            session.rollback()

            due = acquire_checkpoint_lease(
                session,
                connection_id=connection_id,
                resource_type=ResourceType.REFUNDS,
                window_start=self.now - timedelta(days=1),
                window_end=self.now,
                owner="worker-b",
                now=self.now + timedelta(minutes=11),
                lease_duration=timedelta(minutes=1),
            )
            session.commit()
            session.refresh(due)
            self.assertIsNotNone(due)
            self.assertIsNone(due.next_retry_at)
        finally:
            session.close()

    def test_manual_request_id_dominates_body_and_payload_but_has_separate_namespace(self):
        session = self.Session()
        try:
            first = self._enqueue(
                session,
                target_id="manual-target",
                logical_request={"window": "first"},
                payload=self._sync_payload(cursor={"page": 1}),
                manual=True,
                logical_request_id="request-001",
            )
            same_id_changed_body = self._enqueue(
                session,
                target_id="manual-target",
                logical_request={"window": "second"},
                payload=self._sync_payload(cursor={"page": 2}),
                manual=True,
                logical_request_id="request-001",
            )
            automatic_collision_shape = self._enqueue(
                session,
                target_id="manual-target",
                logical_request={
                    "logical_request": {"window": "first"},
                    "logical_request_id": "request-001",
                },
                payload=self._sync_payload(cursor={"page": 3}),
            )
            session.commit()
            session.refresh(first)

            self.assertEqual(first.id, same_id_changed_body.id)
            self.assertEqual(first.payload["cursor"]["page"], 1)
            self.assertNotEqual(first.id, automatic_collision_shape.id)
            self.assertEqual(
                session.scalar(select(func.count()).select_from(IntegrationJob)),
                2,
            )
        finally:
            session.close()

    def test_stale_job_and_checkpoint_heartbeats_cannot_move_timestamps_backward(self):
        _, connection_id = self._seed_connection()
        session = self.Session()
        try:
            job = self._enqueue(session)
            session.commit()
            claim_next_job(
                session,
                owner="worker-a",
                now=self.now,
                lease_duration=timedelta(minutes=10),
            )
            heartbeat_job(
                session,
                job_id=job.id,
                owner="worker-a",
                now=self.now + timedelta(minutes=2),
                lease_duration=timedelta(minutes=10),
            )
            checkpoint = acquire_checkpoint_lease(
                session,
                connection_id=connection_id,
                resource_type=ResourceType.PRODUCTS,
                window_start=self.now - timedelta(days=1),
                window_end=self.now,
                owner="worker-a",
                now=self.now,
                lease_duration=timedelta(minutes=10),
            )
            heartbeat_checkpoint(
                session,
                checkpoint_id=checkpoint.id,
                owner="worker-a",
                now=self.now + timedelta(minutes=2),
                lease_duration=timedelta(minutes=10),
            )
            session.commit()
            session.refresh(job)
            session.refresh(checkpoint)
            job_updated_at = job.updated_at
            checkpoint_updated_at = checkpoint.updated_at

            self.assertFalse(
                heartbeat_job(
                    session,
                    job_id=job.id,
                    owner="worker-a",
                    now=self.now + timedelta(minutes=1),
                    lease_duration=timedelta(minutes=20),
                )
            )
            self.assertFalse(
                heartbeat_checkpoint(
                    session,
                    checkpoint_id=checkpoint.id,
                    owner="worker-a",
                    now=self.now + timedelta(minutes=1),
                    lease_duration=timedelta(minutes=20),
                )
            )
            session.commit()
            session.refresh(job)
            session.refresh(checkpoint)
            self.assertEqual(job.heartbeat_at, self.now + timedelta(minutes=2))
            self.assertEqual(checkpoint.heartbeat_at, self.now + timedelta(minutes=2))
            self.assertEqual(job.updated_at, job_updated_at)
            self.assertEqual(checkpoint.updated_at, checkpoint_updated_at)
        finally:
            session.close()

    def test_naive_timestamps_and_invalid_owners_are_rejected(self):
        session = self.Session()
        try:
            with self.assertRaisesRegex(ValueError, "timezone-aware"):
                self._enqueue(
                    session,
                    available_at=datetime(2026, 7, 14, 2, 0),
                )
            with self.assertRaisesRegex(ValueError, "owner"):
                claim_next_job(
                    session,
                    owner=" ",
                    now=self.now,
                    lease_duration=timedelta(minutes=1),
                )
        finally:
            session.rollback()
            session.close()


if __name__ == "__main__":
    unittest.main()
