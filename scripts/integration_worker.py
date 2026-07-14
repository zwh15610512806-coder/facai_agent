"""CLI entry point for the independent ecommerce integration worker."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

import database
from integrations.settings import load_integration_settings
from integrations.sync.worker import (
    IntegrationWorker,
    WorkerConfig,
    WorkerReadinessError,
    build_default_job_handler,
    expire_export_maintenance,
    parse_worker_enabled,
    scan_orphan_maintenance,
    tick_scheduler_maintenance,
    validate_worker_readiness,
)
from services.runtime_logging import configure_runtime_logging


LOGGER = logging.getLogger("facai.integration.worker")


def install_signal_handlers(worker: IntegrationWorker) -> None:
    """Convert SIGTERM/SIGINT into a graceful stop request."""

    def request_stop(_signum, _frame) -> None:
        worker.request_stop()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)

    configure_runtime_logging(ROOT / "logs" / "facai-integration-worker.log")
    try:
        enabled = parse_worker_enabled()
    except ValueError:
        LOGGER.error("integration_worker_disabled code=invalid_enabled_setting")
        return 2
    if not enabled:
        LOGGER.info("integration_worker_disabled code=not_enabled")
        return 0

    settings = load_integration_settings()
    try:
        validate_worker_readiness(database.engine, settings)
    except WorkerReadinessError:
        LOGGER.error("integration_worker_not_ready code=readiness_failed")
        return 2
    assert settings.archive_dir is not None

    async def scheduler_tick() -> None:
        await asyncio.to_thread(
            tick_scheduler_maintenance,
            database.SessionLocal,
        )
        await asyncio.to_thread(
            expire_export_maintenance,
            database.SessionLocal,
            archive_dir=settings.archive_dir,
        )

    async def orphan_cleanup() -> None:
        await asyncio.to_thread(
            scan_orphan_maintenance,
            database.SessionLocal,
            archive_dir=settings.archive_dir,
        )

    worker = IntegrationWorker(
        session_factory=database.SessionLocal,
        config=WorkerConfig(
            enabled=True,
            concurrency=settings.worker_concurrency,
        ),
        job_handler=build_default_job_handler(
            database.SessionLocal,
            archive_dir=settings.archive_dir,
        ),
        scheduler_tick=scheduler_tick,
        orphan_cleanup=orphan_cleanup,
    )
    install_signal_handlers(worker)
    try:
        result = asyncio.run(worker.run(once=args.once))
    except Exception:
        LOGGER.error("integration_worker_failed code=internal_error")
        return 1
    LOGGER.info(
        "integration_worker_stopped claimed=%d succeeded=%d failed=%d maintenance_errors=%d",
        result.claimed_jobs,
        result.succeeded_jobs,
        result.failed_jobs,
        result.maintenance_errors,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
