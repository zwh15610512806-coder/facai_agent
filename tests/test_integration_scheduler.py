import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

from sqlalchemy import func, select, update
from sqlalchemy.orm import sessionmaker

import database
from database import Base
from integration_models import (
    IntegrationAuthorization,
    IntegrationConnection,
    IntegrationJob,
    IntegrationSyncCheckpoint,
)
from integrations.sync.scheduler import (
    CapabilityAssignment,
    CapabilityCatalog,
    ScheduledConnection,
    due_jobs,
    enqueue_scheduled_units,
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

UTC = UTC
SCHEDULER_TABLES = (
    IntegrationAuthorization.__table__,
    IntegrationConnection.__table__,
    IntegrationJob.__table__,
    IntegrationSyncCheckpoint.__table__,
)


def _full_catalog(*, unverified: ResourceType | None = None) -> CapabilityCatalog:
    assignments = []
    for resource in ResourceType:
        if resource is ResourceType.ORDER_ITEMS:
            mode = "emitted_by:orders"
        else:
            mode = "direct"
        assignments.append(
            CapabilityAssignment(
                resource=resource,
                mode=mode,
                verified=resource is not unverified,
            )
        )
    return CapabilityCatalog(tuple(assignments))


class CapabilityCatalogTests(unittest.TestCase):
    def test_every_resource_is_classified_once_and_children_are_not_scheduled(self):
        catalog = _full_catalog()

        self.assertEqual(set(catalog.assignments), set(ResourceType))
        self.assertEqual(
            catalog.assignment(ResourceType.ORDER_ITEMS).mode,
            "emitted_by:orders",
        )
        self.assertNotIn(ResourceType.ORDER_ITEMS, catalog.direct_resources)
        self.assertEqual(
            catalog.direct_resources | catalog.emitted_resources | catalog.unavailable_resources,
            set(ResourceType),
        )

    def test_missing_duplicate_invalid_parent_and_cycle_fail_readiness(self):
        valid = list(_full_catalog().assignments.values())
        cases = (
            valid[:-1],
            [*valid, valid[0]],
            [
                CapabilityAssignment(
                    resource=item.resource,
                    mode=(
                        "emitted_by:not-a-resource"
                        if item.resource is ResourceType.ORDER_ITEMS
                        else item.mode
                    ),
                    verified=item.verified,
                )
                for item in valid
            ],
            [
                CapabilityAssignment(
                    resource=item.resource,
                    mode=(
                        "emitted_by:skus"
                        if item.resource is ResourceType.PRODUCTS
                        else "emitted_by:products"
                        if item.resource is ResourceType.SKUS
                        else item.mode
                    ),
                    verified=item.verified,
                )
                for item in valid
            ],
        )
        for assignments in cases:
            with self.subTest(size=len(assignments)), self.assertRaises(ValueError):
                CapabilityCatalog(tuple(assignments))


class PureScheduleTests(unittest.TestCase):
    def setUp(self):
        self.connection = ScheduledConnection(
            connection_id=11,
            authorization_id=21,
            status=ConnectionStatus.ACTIVE,
        )

    def test_interval_snapshot_and_daily_windows_use_asia_shanghai_boundaries(self):
        now = datetime(2026, 7, 13, 22, 5, tzinfo=UTC)  # 06:05 next local day
        units = due_jobs(now, [self.connection], {11: _full_catalog()})

        orders = [unit for unit in units if unit.resource_type is ResourceType.ORDERS]
        products = [unit for unit in units if unit.resource_type is ResourceType.PRODUCTS]
        daily = [unit for unit in units if unit.resource_type is ResourceType.DAILY_METRICS]
        ad_daily = [unit for unit in units if unit.resource_type is ResourceType.AD_DAILY_METRICS]

        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].window_end, datetime(2026, 7, 13, 22, 0, tzinfo=UTC))
        self.assertEqual(orders[0].window_start, datetime(2026, 7, 13, 21, 30, tzinfo=UTC))
        self.assertIsNotNone(orders[0].api_window)

        self.assertEqual(len(products), 1)
        self.assertEqual(products[0].captured_at, datetime(2026, 7, 13, 22, 0, tzinfo=UTC))
        self.assertIsNone(products[0].api_window)

        self.assertEqual(len(daily), 7)
        self.assertEqual(len(ad_daily), 7)
        self.assertEqual(daily[0].window_start.hour, 16)
        self.assertEqual(daily[0].window_end - daily[0].window_start, timedelta(days=1))
        self.assertEqual(
            {unit.window_start for unit in daily},
            {unit.window_start for unit in ad_daily},
        )

    def test_unverified_disabled_and_degraded_connections_do_not_start_new_work(self):
        now = datetime(2026, 7, 13, 2, 7, tzinfo=UTC)
        unverified = _full_catalog(unverified=ResourceType.ORDERS)
        disabled = ScheduledConnection(12, 22, ConnectionStatus.DISABLED)
        degraded = ScheduledConnection(13, 23, ConnectionStatus.DEGRADED)

        units = due_jobs(
            now,
            [self.connection, disabled, degraded],
            {11: unverified, 12: _full_catalog(), 13: _full_catalog()},
        )

        self.assertFalse(any(unit.resource_type is ResourceType.ORDERS for unit in units))
        self.assertEqual({unit.connection_id for unit in units if unit.connection_id}, {11})

    def test_refresh_is_authorization_scoped_and_deduped_across_connections(self):
        now = datetime(2026, 7, 13, 2, 7, tzinfo=UTC)
        second = ScheduledConnection(
            12,
            21,
            ConnectionStatus.ACTIVE,
            authorization_refresh_due=True,
        )
        first = ScheduledConnection(
            11,
            21,
            ConnectionStatus.ACTIVE,
            authorization_refresh_due=True,
        )

        units = due_jobs(
            now,
            [first, second],
            {11: _full_catalog(), 12: _full_catalog()},
        )
        refreshes = [unit for unit in units if unit.job_type is JobType.REFRESH_AUTHORIZATION]

        self.assertEqual(len(refreshes), 1)
        self.assertEqual(refreshes[0].authorization_id, 21)
        self.assertIsNone(refreshes[0].connection_id)

    def test_initial_backfill_respects_the_later_capability_boundary(self):
        now = datetime(2026, 7, 13, 18, 0, tzinfo=UTC)
        connection = ScheduledConnection(
            11,
            21,
            ConnectionStatus.ACTIVE,
            backfill_from=datetime(2026, 7, 10, 12, 0, tzinfo=UTC),
        )
        catalog = _full_catalog()
        assignments = []
        for assignment in catalog.assignments.values():
            assignments.append(
                CapabilityAssignment(
                    resource=assignment.resource,
                    mode=assignment.mode,
                    verified=assignment.verified,
                    earliest_available_at=(
                        datetime(2026, 7, 12, 4, 0, tzinfo=UTC)
                        if assignment.resource is ResourceType.ORDERS
                        else None
                    ),
                )
            )
        units = due_jobs(now, [connection], {11: CapabilityCatalog(tuple(assignments))})
        order_units = [unit for unit in units if unit.resource_type is ResourceType.ORDERS]

        self.assertGreaterEqual(len(order_units), 2)
        self.assertGreaterEqual(
            min(unit.window_start for unit in order_units),
            datetime(2026, 7, 12, 4, 0, tzinfo=UTC),
        )
        self.assertEqual(max(unit.window_end for unit in order_units), now)

    def test_recurring_windows_never_cross_the_capability_history_boundary(self):
        now = datetime(2026, 7, 13, 22, 5, tzinfo=UTC)
        boundaries = {
            ResourceType.ORDERS: datetime(2026, 7, 13, 21, 50, tzinfo=UTC),
            ResourceType.DAILY_METRICS: datetime(2026, 7, 13, 4, 0, tzinfo=UTC),
        }
        catalog = _full_catalog()
        limited = CapabilityCatalog(
            tuple(
                CapabilityAssignment(
                    resource=assignment.resource,
                    mode=assignment.mode,
                    verified=assignment.verified,
                    earliest_available_at=boundaries.get(assignment.resource),
                )
                for assignment in catalog.assignments.values()
            )
        )

        units = due_jobs(now, [self.connection], {11: limited})

        for resource, boundary in boundaries.items():
            selected = [unit for unit in units if unit.resource_type is resource]
            self.assertTrue(selected)
            self.assertGreaterEqual(
                min(unit.api_window.start_at for unit in selected if unit.api_window),
                boundary,
            )

    def test_interval_overlap_is_split_at_asia_shanghai_midnight(self):
        now = datetime(2026, 7, 13, 16, 20, tzinfo=UTC)  # 00:20 local

        units = due_jobs(now, [self.connection], {11: _full_catalog()})
        orders = [unit for unit in units if unit.resource_type is ResourceType.ORDERS]

        self.assertEqual(
            [(unit.window_start, unit.window_end) for unit in orders],
            [
                (
                    datetime(2026, 7, 13, 15, 45, tzinfo=UTC),
                    datetime(2026, 7, 13, 16, 0, tzinfo=UTC),
                ),
                (
                    datetime(2026, 7, 13, 16, 0, tzinfo=UTC),
                    datetime(2026, 7, 13, 16, 15, tzinfo=UTC),
                ),
            ],
        )


@requires_disposable_postgres
class SchedulerPersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = _require_disposable_postgres_url()
        cls.engine = database.create_database_engine(cls.database_url)
        cls.Session = sessionmaker(bind=cls.engine, expire_on_commit=False)
        cls.addClassCleanup(cls._cleanup)
        cls._reset()

    @classmethod
    def _reset(cls):
        Base.metadata.drop_all(cls.engine, tables=SCHEDULER_TABLES, checkfirst=True)
        Base.metadata.create_all(cls.engine, tables=SCHEDULER_TABLES, checkfirst=False)

    @classmethod
    def _cleanup(cls):
        try:
            Base.metadata.drop_all(cls.engine, tables=SCHEDULER_TABLES, checkfirst=True)
        finally:
            cls.engine.dispose()

    def setUp(self):
        self._reset()
        with self.Session.begin() as db:
            authorization = IntegrationAuthorization(
                provider=Provider.DOUDIAN,
                external_subject_id="subject-scheduler",
                status=AuthorizationStatus.ACTIVE,
                scopes=[],
                access_token_ciphertext="v1:opaque-test-ciphertext",
                access_token_tail="0000",
                last_authorized_at=datetime.now(UTC),
            )
            db.add(authorization)
            db.flush()
            connection = IntegrationConnection(
                authorization_id=authorization.id,
                provider=Provider.DOUDIAN,
                connection_type=ConnectionType.SHOP,
                external_account_id="shop-scheduler",
                display_name="Scheduler Shop",
                status=ConnectionStatus.ACTIVE,
                capability_report={},
            )
            db.add(connection)
            db.flush()
            self.connection_id = connection.id
            self.authorization_id = authorization.id

    def test_duplicate_ticks_create_one_checkpoint_and_one_job(self):
        now = datetime(2026, 7, 13, 2, 7, tzinfo=UTC)
        connection = ScheduledConnection(
            self.connection_id,
            self.authorization_id,
            ConnectionStatus.ACTIVE,
        )
        units = [
            unit
            for unit in due_jobs(now, [connection], {self.connection_id: _full_catalog()})
            if unit.resource_type is ResourceType.ORDERS
        ]

        with self.Session.begin() as db:
            first = enqueue_scheduled_units(db, units)
        with self.Session.begin() as db:
            second = enqueue_scheduled_units(db, units)
        with self.Session() as db:
            checkpoints = db.scalar(select(func.count()).select_from(IntegrationSyncCheckpoint))
            jobs = db.scalar(select(func.count()).select_from(IntegrationJob))

        self.assertEqual(first.sync_units, 1)
        self.assertEqual(second.sync_units, 1)
        self.assertEqual(checkpoints, 1)
        self.assertEqual(jobs, 1)

    def test_concurrent_ticks_create_one_checkpoint_and_one_job(self):
        now = datetime(2026, 7, 13, 2, 7, tzinfo=UTC)
        connection = ScheduledConnection(
            self.connection_id,
            self.authorization_id,
            ConnectionStatus.ACTIVE,
        )
        units = [
            unit
            for unit in due_jobs(
                now,
                [connection],
                {self.connection_id: _full_catalog()},
            )
            if unit.resource_type is ResourceType.ORDERS
        ]
        barrier = Barrier(2)

        def enqueue_from_independent_session(_):
            with self.Session() as db:
                barrier.wait(timeout=5)
                enqueue_scheduled_units(db, units)
                db.commit()

        with ThreadPoolExecutor(max_workers=2) as executor:
            list(executor.map(enqueue_from_independent_session, range(2)))
        with self.Session() as db:
            checkpoints = db.scalar(
                select(func.count()).select_from(IntegrationSyncCheckpoint)
            )
            jobs = db.scalar(select(func.count()).select_from(IntegrationJob))

        self.assertEqual(checkpoints, 1)
        self.assertEqual(jobs, 1)

    def test_archive_cleanup_is_manifest_scoped_and_deduped_without_connections(self):
        now = datetime(2026, 7, 13, 19, 0, tzinfo=UTC)
        units = due_jobs(
            now,
            [],
            {},
            expired_archive_manifest_ids=[91, 91],
        )

        with self.Session.begin() as db:
            first = enqueue_scheduled_units(db, units)
        with self.Session.begin() as db:
            second = enqueue_scheduled_units(db, units)
        with self.Session() as db:
            jobs = db.scalars(select(IntegrationJob)).all()

        self.assertEqual(len(units), 1)
        self.assertEqual(units[0].job_type, JobType.ARCHIVE_CLEANUP)
        self.assertEqual(first.archive_cleanup_units, 1)
        self.assertEqual(second.archive_cleanup_units, 1)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].payload, {"archive_manifest_id": 91})

    def test_next_daily_tick_rereads_all_seven_days_with_new_jobs(self):
        first_now = datetime(2026, 7, 13, 22, 5, tzinfo=UTC)
        connection = ScheduledConnection(
            self.connection_id,
            self.authorization_id,
            ConnectionStatus.ACTIVE,
        )
        first_units = [
            unit
            for unit in due_jobs(
                first_now,
                [connection],
                {self.connection_id: _full_catalog()},
            )
            if unit.resource_type is ResourceType.DAILY_METRICS
        ]
        second_units = [
            unit
            for unit in due_jobs(
                first_now + timedelta(days=1),
                [connection],
                {self.connection_id: _full_catalog()},
            )
            if unit.resource_type is ResourceType.DAILY_METRICS
        ]

        with self.Session.begin() as db:
            enqueue_scheduled_units(db, first_units)
        with self.Session.begin() as db:
            db.execute(
                update(IntegrationJob).values(status=JobStatus.SUCCEEDED)
            )
            db.execute(
                update(IntegrationSyncCheckpoint).values(
                    status=CheckpointStatus.COMPLETE
                )
            )
        with self.Session.begin() as db:
            enqueue_scheduled_units(db, second_units)
        with self.Session() as db:
            jobs = db.scalar(select(func.count()).select_from(IntegrationJob))
            checkpoints = db.scalar(
                select(func.count()).select_from(IntegrationSyncCheckpoint)
            )

        self.assertEqual(len(first_units), 7)
        self.assertEqual(len(second_units), 7)
        self.assertEqual(jobs, 14)
        self.assertEqual(checkpoints, 8)


if __name__ == "__main__":
    unittest.main()
