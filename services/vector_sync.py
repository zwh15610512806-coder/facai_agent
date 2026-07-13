"""Durable SQLite outbox and retry worker for Chroma synchronization."""

from __future__ import annotations

import logging
import os
import threading
from datetime import UTC, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from database import SessionLocal
from models import Product, ReferenceScript, VectorSyncJob, ViralScript


logger = logging.getLogger("vector_sync")

ENTITY_TYPES = {"product", "viral_script", "reference_script"}
OPERATIONS = {"upsert", "delete"}
RETRY_DELAYS_SECONDS = (30, 120, 600, 1800, 7200)
MAX_ATTEMPTS = len(RETRY_DELAYS_SECONDS) + 1
RUNNING_LEASE_SECONDS = max(30, int(os.getenv("VECTOR_SYNC_LEASE_SECONDS", "600")))

_worker_lock = threading.Lock()
_worker_stop = threading.Event()
_worker_thread: threading.Thread | None = None


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def enqueue_vector_sync(
    db: Session,
    entity_type: str,
    entity_id: int,
    operation: str = "upsert",
) -> VectorSyncJob:
    """Register the latest desired index state in the caller's transaction."""

    if entity_type not in ENTITY_TYPES:
        raise ValueError(f"Unsupported vector entity type: {entity_type}")
    if operation not in OPERATIONS:
        raise ValueError(f"Unsupported vector operation: {operation}")

    job = (
        db.query(VectorSyncJob)
        .filter(
            VectorSyncJob.entity_type == entity_type,
            VectorSyncJob.entity_id == int(entity_id),
            VectorSyncJob.status.in_(["pending", "failed"]),
        )
        .order_by(VectorSyncJob.id.desc())
        .first()
    )
    now = _utcnow()
    if job is None:
        job = VectorSyncJob(
            entity_type=entity_type,
            entity_id=int(entity_id),
            operation=operation,
            status="pending",
            attempt_count=0,
            next_attempt_at=now,
        )
        db.add(job)
    else:
        job.operation = operation
        job.status = "pending"
        job.attempt_count = 0
        job.next_attempt_at = now
        job.last_error = None
        job.completed_at = None
    db.flush()
    return job


def _delete_product_vector(entity_id: int) -> None:
    from vector_store.product_store import ProductVectorStore

    ProductVectorStore().delete_embedding(entity_id)


def _delete_script_vector(entity_type: str, entity_id: int) -> None:
    from vector_store.script_store import ScriptVectorStore

    prefix = "viral" if entity_type == "viral_script" else "ref"
    ScriptVectorStore().delete_embedding(f"{prefix}_{entity_id}")


def _execute_vector_operation(job: VectorSyncJob, db: Session) -> None:
    """Apply one desired state. Vector-store methods must raise on failure."""

    if job.operation == "delete":
        if job.entity_type == "product":
            _delete_product_vector(job.entity_id)
        else:
            _delete_script_vector(job.entity_type, job.entity_id)
        return

    if job.entity_type == "product":
        product = db.get(Product, job.entity_id)
        if product is None or product.status != "active":
            _delete_product_vector(job.entity_id)
            return
        from vector_store.product_store import ProductVectorStore

        indexed_ids = ProductVectorStore().index_product(product, db)
        if not indexed_ids:
            raise RuntimeError(f"Product {job.entity_id} produced no vector chunks")
        return

    if job.entity_type == "viral_script":
        entity = db.get(ViralScript, job.entity_id)
        if entity is None:
            _delete_script_vector(job.entity_type, job.entity_id)
            return
        from vector_store.script_store import ScriptVectorStore

        embedding_id = ScriptVectorStore().index_viral_script(entity)
    else:
        entity = db.get(ReferenceScript, job.entity_id)
        if entity is None:
            _delete_script_vector(job.entity_type, job.entity_id)
            return
        from vector_store.script_store import ScriptVectorStore

        embedding_id = ScriptVectorStore().index_reference_script(entity)
    if not embedding_id:
        raise RuntimeError(f"{job.entity_type} {job.entity_id} was not indexed")
    entity.embedding_id = embedding_id


def process_vector_sync_job(job_id: int, *, db: Session | None = None, force: bool = False) -> str:
    """Process one job and persist succeeded/pending/failed state."""

    owns_session = db is None
    session = db or SessionLocal()
    try:
        job = session.get(VectorSyncJob, int(job_id))
        if job is None:
            raise ValueError(f"Vector sync job does not exist: {job_id}")
        now = _utcnow()
        if job.status == "succeeded" and not force:
            return "succeeded"
        if job.status == "failed" and not force:
            return "failed"
        if not force and job.next_attempt_at and job.next_attempt_at > now:
            return job.status

        eligible_statuses = ["pending", "failed"] if force else ["pending"]
        claim_query = session.query(VectorSyncJob).filter(
            VectorSyncJob.id == int(job_id),
            VectorSyncJob.status.in_(eligible_statuses),
        )
        if not force:
            claim_query = claim_query.filter(VectorSyncJob.next_attempt_at <= now)
        claimed = claim_query.update({
            VectorSyncJob.status: "running",
            VectorSyncJob.attempt_count: func.coalesce(VectorSyncJob.attempt_count, 0) + 1,
            VectorSyncJob.last_error: None,
            VectorSyncJob.next_attempt_at: now + timedelta(seconds=RUNNING_LEASE_SECONDS),
        }, synchronize_session=False)
        session.commit()
        session.expire_all()
        job = session.get(VectorSyncJob, int(job_id))
        if not claimed:
            return job.status

        try:
            _execute_vector_operation(job, session)
        except Exception as exc:
            session.rollback()
            job = session.get(VectorSyncJob, int(job_id))
            job.last_error = str(exc)[:4000]
            if job.attempt_count >= MAX_ATTEMPTS:
                job.status = "failed"
                job.next_attempt_at = now
            else:
                delay = RETRY_DELAYS_SECONDS[job.attempt_count - 1]
                job.status = "pending"
                job.next_attempt_at = now + timedelta(seconds=delay)
            session.commit()
            logger.warning(
                "Vector sync pending entity=%s id=%s operation=%s attempt=%s: %s",
                job.entity_type,
                job.entity_id,
                job.operation,
                job.attempt_count,
                exc,
            )
            return job.status

        job.status = "succeeded"
        job.completed_at = _utcnow()
        job.next_attempt_at = job.completed_at
        job.last_error = None
        session.commit()
        return "succeeded"
    finally:
        if owns_session:
            session.close()


def latest_job_for_entity(db: Session, entity_type: str, entity_id: int) -> VectorSyncJob | None:
    return (
        db.query(VectorSyncJob)
        .filter(
            VectorSyncJob.entity_type == entity_type,
            VectorSyncJob.entity_id == int(entity_id),
        )
        .order_by(VectorSyncJob.id.desc())
        .first()
    )


def ensure_and_process_vector_sync(db: Session, entity_type: str, entity_id: int, operation: str) -> str:
    """Compatibility helper for existing write paths while preserving a durable job."""

    job = latest_job_for_entity(db, entity_type, entity_id)
    if job is None or job.status == "succeeded" or job.operation != operation:
        job = enqueue_vector_sync(db, entity_type, entity_id, operation)
        db.commit()
    return process_vector_sync_job(job.id, db=db, force=True)


def vector_sync_status(db: Session) -> dict:
    rows = db.query(VectorSyncJob.status, func.count(VectorSyncJob.id)).group_by(VectorSyncJob.status).all()
    counts = {"pending": 0, "running": 0, "failed": 0, "succeeded": 0}
    for status, count in rows:
        if status in counts:
            counts[status] = int(count)
    recent_error = (
        db.query(VectorSyncJob)
        .filter(VectorSyncJob.last_error.isnot(None))
        .order_by(VectorSyncJob.updated_at.desc(), VectorSyncJob.id.desc())
        .first()
    )
    counts["recent_error"] = None if recent_error is None else {
        "job_id": recent_error.id,
        "entity_type": recent_error.entity_type,
        "entity_id": recent_error.entity_id,
        "operation": recent_error.operation,
        "attempt_count": recent_error.attempt_count,
        "message": recent_error.last_error,
        "updated_at": recent_error.updated_at,
    }
    return counts


def reconcile_product_vector_index(db: Session, *, product_store=None) -> dict:
    """Queue repairs when active product chunk hashes differ from the database."""
    if product_store is None:
        from vector_store.product_store import ProductVectorStore

        product_store = ProductVectorStore()
    from services.product_knowledge_chunks import (
        build_product_knowledge_chunks,
        product_chunk_index_metadata,
    )

    rows = product_store.collection.get(include=["metadatas"])
    metadata_rows = [item for item in (rows.get("metadatas") or []) if isinstance(item, dict)]
    if metadata_rows and not any(str(item.get("content_hash") or "") for item in metadata_rows):
        active_products = db.query(Product).filter(Product.status == "active").count()
        logger.warning(
            "Active product index has no content hashes; incremental reconciliation is skipped until full reindex"
        )
        return {
            "active_products": active_products,
            "missing": 0,
            "stale": 0,
            "orphaned": 0,
            "queued": 0,
            "requires_reindex": True,
        }
    actual_by_product: dict[int, dict[str, str]] = {}
    for chunk_id, metadata in zip(rows.get("ids") or [], rows.get("metadatas") or []):
        if not isinstance(metadata, dict):
            continue
        try:
            product_id = int(metadata.get("product_id"))
        except (TypeError, ValueError):
            continue
        content_hash = str(metadata.get("content_hash") or "")
        actual_by_product.setdefault(product_id, {})[str(chunk_id)] = content_hash

    products = db.query(Product).filter(Product.status == "active").all()
    active_ids = {int(product.id) for product in products}
    missing = 0
    stale = 0
    orphaned = 0
    for product in products:
        expected_chunks = {
            chunk.chunk_id: product_chunk_index_metadata(chunk, product.price)["content_hash"]
            for chunk in build_product_knowledge_chunks(product)
        }
        actual_chunks = actual_by_product.get(int(product.id))
        if actual_chunks is None:
            missing += 1
            enqueue_vector_sync(db, "product", product.id, "upsert")
        elif actual_chunks != expected_chunks:
            stale += 1
            enqueue_vector_sync(db, "product", product.id, "upsert")
    for product_id in actual_by_product:
        if product_id in active_ids:
            continue
        orphaned += 1
        enqueue_vector_sync(db, "product", product_id, "delete")
    db.commit()
    return {
        "active_products": len(products),
        "missing": missing,
        "stale": stale,
        "orphaned": orphaned,
        "queued": missing + stale + orphaned,
        "requires_reindex": False,
    }


def _recover_expired_running_jobs(db: Session, *, now: datetime | None = None) -> int:
    """Return only abandoned jobs whose processing lease has expired to pending."""
    current = now or _utcnow()
    recovered = db.query(VectorSyncJob).filter(
        VectorSyncJob.status == "running",
        VectorSyncJob.next_attempt_at <= current,
    ).update({
        VectorSyncJob.status: "pending",
        VectorSyncJob.next_attempt_at: current,
    }, synchronize_session=False)
    db.commit()
    return int(recovered or 0)


def retry_vector_sync_jobs(db: Session) -> int:
    jobs = db.query(VectorSyncJob).filter(VectorSyncJob.status.in_(["pending", "failed"])).all()
    now = _utcnow()
    for job in jobs:
        job.status = "pending"
        job.attempt_count = 0
        job.next_attempt_at = now
        job.last_error = None
        job.completed_at = None
    db.commit()
    return len(jobs)


def _worker_loop(reconcile_on_startup: bool = True) -> None:
    if reconcile_on_startup:
        reconcile_db = SessionLocal()
        try:
            result = reconcile_product_vector_index(reconcile_db)
            if result["queued"]:
                logger.warning("Queued product vector reconciliation repairs: %s", result)
        except Exception:
            logger.exception("Product vector reconciliation failed")
        finally:
            reconcile_db.close()
    while not _worker_stop.wait(5):
        db = SessionLocal()
        try:
            recovered = _recover_expired_running_jobs(db)
            if recovered:
                logger.warning("Recovered %s expired vector sync job leases", recovered)
            due_ids = [
                row[0]
                for row in (
                    db.query(VectorSyncJob.id)
                    .filter(
                        VectorSyncJob.status == "pending",
                        VectorSyncJob.next_attempt_at <= _utcnow(),
                    )
                    .order_by(VectorSyncJob.id.asc())
                    .limit(20)
                    .all()
                )
            ]
            for job_id in due_ids:
                process_vector_sync_job(job_id, db=db)
        except Exception:
            logger.exception("Vector sync worker iteration failed")
        finally:
            db.close()


def start_vector_sync_worker(*, reconcile_on_startup: bool | None = None) -> None:
    global _worker_thread
    with _worker_lock:
        if _worker_thread and _worker_thread.is_alive():
            return
        db = SessionLocal()
        try:
            _recover_expired_running_jobs(db)
        finally:
            db.close()
        if reconcile_on_startup is None:
            reconcile_on_startup = os.getenv("VECTOR_RECONCILE_ON_STARTUP", "1").strip() != "0"
        _worker_stop.clear()
        _worker_thread = threading.Thread(
            target=_worker_loop,
            args=(bool(reconcile_on_startup),),
            name="vector-sync-worker",
            daemon=True,
        )
        _worker_thread.start()


def stop_vector_sync_worker() -> None:
    _worker_stop.set()
    thread = _worker_thread
    if thread and thread.is_alive():
        thread.join(timeout=2)
