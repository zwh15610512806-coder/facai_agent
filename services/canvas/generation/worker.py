"""Short-transaction claims and DB-free Provider execution for Canvas generations."""
from __future__ import annotations

import json
import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Callable
from uuid import uuid4

from sqlalchemy import func, or_, select, text, update
from sqlalchemy.orm import Session

from canvas_models import (
    CanvasGeneration,
    CanvasGenerationAttempt,
    CanvasGenerationItem,
    ImageProviderConnection,
)
from config import CANVAS_GENERATION_CONCURRENCY, CANVAS_GENERATION_LEASE_SECONDS
from services.canvas import storage
from services.canvas.events import append_generation_progress_event
from services.canvas.generation.repository import (
    active_generation_reservations,
    release_generation_reservation,
)
from services.canvas.generation.state import (
    aggregate_generation_status,
    transition_attempt,
    transition_generation,
    transition_item,
)
from services.canvas.provider_schemas import (
    ControlledImageBytes,
    ControlledRemoteImage,
    ModelCapabilities,
    ProviderError,
    ProviderGenerationRequest,
    ProviderPollResult,
    ProviderRuntime,
    ProviderSubmission,
)
from services.canvas.providers.registry import ProviderRegistry
from services.canvas.sqlite_writer import begin_immediate_if_sqlite


logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass(frozen=True)
class ClaimedAttempt:
    attempt_id: str
    item_id: str
    generation_id: str
    project_id: str
    claim_token: str
    lease_expires_at: datetime
    status: str
    provider_result_stage: str
    provider_id: str
    model_profile_id: str
    provider_snapshot: dict[str, Any]
    model_snapshot: dict[str, Any]
    prompt: str
    width: int
    height: int
    upstream_idempotency_key: str
    external_task_id: str | None


@dataclass(frozen=True)
class AttemptExecutionResult:
    kind: str
    image: ControlledRemoteImage | ControlledImageBytes | None = None
    provider_request_id: str | None = None
    external_task_id: str | None = None
    safe_error_code: str | None = None
    safe_error_summary: str | None = None


@dataclass(frozen=True, repr=False)
class ProviderExecutionContext:
    """In-memory adapter, credential runtime, and public result transport."""

    adapter: Any
    runtime: ProviderRuntime
    result_transport: Any

    def __repr__(self) -> str:
        return "ProviderExecutionContext(<redacted>)"


def _lease_deadline(now: datetime) -> datetime:
    return now + timedelta(seconds=CANVAS_GENERATION_LEASE_SECONDS)


def _load_json(value: str, *, label: str) -> dict[str, Any]:
    try:
        document = json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid {label} snapshot") from exc
    if not isinstance(document, dict):
        raise ValueError(f"invalid {label} snapshot")
    return document


def _concurrency_limit(snapshot: dict[str, Any], *, provider: bool) -> int:
    if provider:
        value = snapshot.get("concurrencyLimit", 1)
    else:
        capabilities = snapshot.get("capabilities")
        value = capabilities.get("concurrency_limit", capabilities.get("concurrencyLimit", 1)) if isinstance(capabilities, dict) else 1
    return value if type(value) is int and value > 0 else 1


def _active_lease_count(db: Session, *, now: datetime) -> int:
    return int(
        db.scalar(
            select(func.count()).select_from(CanvasGenerationAttempt).where(
                CanvasGenerationAttempt.lease_expires_at > now,
                CanvasGenerationAttempt.worker_id.is_not(None),
            )
        )
        or 0
    )


def _provider_model_slots_available(
    db: Session,
    *,
    candidate: CanvasGenerationAttempt,
    provider_limit: int,
    model_limit: int,
    now: datetime,
) -> bool:
    active_predicate = or_(
        CanvasGenerationAttempt.lease_expires_at > now,
        (CanvasGenerationAttempt.status == "polling")
        & CanvasGenerationAttempt.external_task_id.is_not(None),
    )
    provider_count = int(
        db.scalar(
            select(func.count()).select_from(CanvasGenerationAttempt).where(
                CanvasGenerationAttempt.id != candidate.id,
                CanvasGenerationAttempt.provider_id == candidate.provider_id,
                active_predicate,
            )
        )
        or 0
    )
    model_count = int(
        db.scalar(
            select(func.count()).select_from(CanvasGenerationAttempt).where(
                CanvasGenerationAttempt.id != candidate.id,
                CanvasGenerationAttempt.model_profile_id == candidate.model_profile_id,
                active_predicate,
            )
        )
        or 0
    )
    return provider_count < provider_limit and model_count < model_limit


def claim_next_attempt(
    db: Session,
    *,
    worker_id: str,
    now: datetime,
) -> ClaimedAttempt | None:
    if not isinstance(worker_id, str) or not worker_id.strip():
        raise ValueError("worker_id is required")
    if db.in_transaction():
        raise RuntimeError("claim_next_attempt requires a fresh Session")
    db.execute(text("BEGIN IMMEDIATE"))
    if _active_lease_count(db, now=now) >= CANVAS_GENERATION_CONCURRENCY:
        return None
    rows = db.execute(
        select(CanvasGenerationAttempt, CanvasGenerationItem, CanvasGeneration)
        .join(CanvasGenerationItem, CanvasGenerationItem.id == CanvasGenerationAttempt.item_id)
        .join(CanvasGeneration, CanvasGeneration.id == CanvasGenerationItem.generation_id)
        .where(
            CanvasGeneration.status.in_(("queued", "running", "interrupted", "cancel_requested")),
            or_(
                (
                    (CanvasGenerationAttempt.status == "queued")
                    & or_(
                        CanvasGenerationAttempt.lease_expires_at.is_(None),
                        CanvasGenerationAttempt.lease_expires_at <= now,
                    )
                ),
                (
                    (CanvasGenerationAttempt.status == "polling")
                    & (CanvasGenerationAttempt.external_task_id.is_not(None))
                    & or_(
                        CanvasGenerationAttempt.next_poll_at.is_(None),
                        CanvasGenerationAttempt.next_poll_at <= now,
                    )
                    & or_(
                        CanvasGenerationAttempt.lease_expires_at.is_(None),
                        CanvasGenerationAttempt.lease_expires_at <= now,
                    )
                ),
                (
                    (CanvasGenerationAttempt.status == "cancel_requested")
                    & (CanvasGenerationAttempt.external_task_id.is_not(None))
                    & or_(
                        CanvasGenerationAttempt.next_poll_at.is_(None),
                        CanvasGenerationAttempt.next_poll_at <= now,
                    )
                    & or_(
                        CanvasGenerationAttempt.lease_expires_at.is_(None),
                        CanvasGenerationAttempt.lease_expires_at <= now,
                    )
                ),
            ),
        )
        .order_by(CanvasGenerationAttempt.created_at, CanvasGenerationAttempt.id)
        .limit(100)
    ).all()
    for attempt, item, generation in rows:
        provider_snapshot = _load_json(
            attempt.provider_config_snapshot_json,
            label="Provider",
        )
        model_snapshot = _load_json(attempt.model_config_snapshot_json, label="model")
        if not _provider_model_slots_available(
            db,
            candidate=attempt,
            provider_limit=_concurrency_limit(provider_snapshot, provider=True),
            model_limit=_concurrency_limit(model_snapshot, provider=False),
            now=now,
        ):
            continue
        project_reserved, total_reserved = active_generation_reservations(
            db,
            project_id=generation.project_id,
        )
        try:
            storage.assert_canvas_capacity(
                project_id=generation.project_id,
                additional_bytes=0,
                reserved_project_bytes=project_reserved,
                reserved_total_bytes=total_reserved,
            )
        except storage.CanvasStorageError as exc:
            generation.safe_storage_block_reason = exc.code
            generation.storage_blocked_at = now
            continue

        token = f"{worker_id.strip()}:{uuid4()}"
        deadline = _lease_deadline(now)
        attempt.worker_id = token
        attempt.heartbeat_at = now
        attempt.lease_expires_at = deadline
        if item.status == "queued":
            transition_item(item.status, "running")
            item.status = "running"
            item.started_at = item.started_at or now
        if generation.status in {"queued", "interrupted"}:
            transition_generation(generation.status, "running")
            generation.status = "running"
            generation.started_at = generation.started_at or now
        generation.safe_storage_block_reason = None
        generation.storage_blocked_at = None
        append_generation_progress_event(
            db,
            generation=generation,
            item=item,
            attempt=attempt,
            event_type="generation.item.running",
        )
        db.flush()
        return ClaimedAttempt(
            attempt_id=attempt.id,
            item_id=item.id,
            generation_id=generation.id,
            project_id=generation.project_id,
            claim_token=token,
            lease_expires_at=deadline,
            status=attempt.status,
            provider_result_stage=attempt.provider_result_stage,
            provider_id=attempt.provider_id,
            model_profile_id=attempt.model_profile_id,
            provider_snapshot=provider_snapshot,
            model_snapshot=model_snapshot,
            prompt=item.prompt,
            width=item.width,
            height=item.height,
            upstream_idempotency_key=attempt.upstream_idempotency_key,
            external_task_id=attempt.external_task_id,
        )
    return None


def heartbeat_claimed_attempt(
    db: Session,
    *,
    claim: ClaimedAttempt,
    now: datetime,
) -> bool:
    result = db.execute(
        update(CanvasGenerationAttempt)
        .where(
            CanvasGenerationAttempt.id == claim.attempt_id,
            CanvasGenerationAttempt.worker_id == claim.claim_token,
            CanvasGenerationAttempt.lease_expires_at >= now,
        )
        .values(heartbeat_at=now, lease_expires_at=_lease_deadline(now))
    )
    return result.rowcount == 1


def prepare_claimed_attempt_for_execution(
    db: Session,
    *,
    claim: ClaimedAttempt,
    now: datetime,
) -> bool:
    """Run the mandatory final capacity check before any paid Provider await."""

    if db.in_transaction():
        raise RuntimeError("prepare_claimed_attempt_for_execution requires a fresh Session")
    db.execute(text("BEGIN IMMEDIATE"))
    row = db.get(CanvasGenerationAttempt, claim.attempt_id)
    item = db.get(CanvasGenerationItem, claim.item_id)
    generation = db.get(CanvasGeneration, claim.generation_id)
    if (
        row is None
        or item is None
        or generation is None
        or row.worker_id != claim.claim_token
        or row.lease_expires_at is None
        or row.lease_expires_at < now
        or row.status not in {"queued", "polling", "cancel_requested"}
    ):
        return False
    project_reserved, total_reserved = active_generation_reservations(
        db,
        project_id=claim.project_id,
    )
    try:
        storage.assert_canvas_capacity(
            project_id=claim.project_id,
            additional_bytes=0,
            reserved_project_bytes=project_reserved,
            reserved_total_bytes=total_reserved,
        )
    except storage.CanvasStorageError as exc:
        row.worker_id = None
        row.lease_expires_at = None
        row.heartbeat_at = None
        generation.safe_storage_block_reason = exc.code
        generation.storage_blocked_at = now
        return False
    if row.status == "queued":
        transition_attempt(row.status, "submitting")
        row.status = "submitting"
        row.submission_started_at = now
        append_generation_progress_event(
            db,
            generation=generation,
            item=item,
            attempt=row,
            event_type="generation.attempt.submitting",
        )
    row.heartbeat_at = now
    row.lease_expires_at = _lease_deadline(now)
    return True


def _runtime_for_adapter(adapter: Any, adapter_type: str) -> ProviderRuntime:
    factory = getattr(adapter, "runtime_factory", None)
    if callable(factory):
        runtime = factory()
        if isinstance(runtime, ProviderRuntime):
            return runtime
    from services.canvas.runtime import create_image_provider_runtime

    return create_image_provider_runtime(adapter_type)


def _adapter_from_claim(
    claim: ClaimedAttempt,
    *,
    registry: ProviderRegistry,
) -> tuple[Any, str, ModelCapabilities]:
    adapter_type = claim.provider_snapshot.get("adapterType")
    if not isinstance(adapter_type, str) or not adapter_type:
        raise ProviderError(
            "provider_configuration_invalid",
            "The saved image Provider configuration is invalid",
        )
    capabilities_data = claim.model_snapshot.get("capabilities")
    model_id = claim.model_snapshot.get("modelId")
    configuration = claim.model_snapshot.get("configuration")
    if not isinstance(capabilities_data, dict) or not isinstance(model_id, str) or not model_id:
        raise ProviderError(
            "provider_configuration_invalid",
            "The saved image model configuration is invalid",
        )
    try:
        capabilities = ModelCapabilities(**capabilities_data)
        adapter = registry.build(
            adapter_type,
            model_id=model_id,
            capabilities=capabilities,
            configuration=configuration,
        )
    except ProviderError:
        raise
    except Exception:
        raise ProviderError(
            "provider_configuration_invalid",
            "The saved image model configuration is invalid",
        ) from None
    return adapter, adapter_type, capabilities


def prepare_provider_execution_context(
    claim: ClaimedAttempt,
    *,
    registry: ProviderRegistry,
    db_factory: Callable[[], Session] | None = None,
    network_policy: Any | None = None,
    resolver: Any | None = None,
    request_transport: Any | None = None,
    result_transport: Any | None = None,
) -> ProviderExecutionContext:
    """Build one credential-safe execution context before any network await.

    Built-in and test adapters retain their sealed runtime factories. Dynamic
    third-party adapters load only the current credential in one short Session;
    the immutable claim continues to supply the model and origin snapshots.
    """

    adapter, adapter_type, _capabilities = _adapter_from_claim(claim, registry=registry)
    runtime_factory = getattr(adapter, "runtime_factory", None)
    if callable(runtime_factory):
        runtime = runtime_factory()
        if not isinstance(runtime, ProviderRuntime):
            raise ProviderError(
                "provider_configuration_invalid",
                "The image Provider runtime configuration is invalid",
            )
        return ProviderExecutionContext(
            adapter=adapter,
            runtime=runtime,
            result_transport=runtime.transport,
        )
    if adapter_type == "seedream":
        runtime = _runtime_for_adapter(adapter, adapter_type)
        return ProviderExecutionContext(
            adapter=adapter,
            runtime=runtime,
            result_transport=runtime.transport,
        )
    if db_factory is None:
        raise ProviderError(
            "provider_configuration_invalid",
            "The third-party image Provider runtime is unavailable",
        )

    provider_id = claim.provider_snapshot.get("id")
    saved_auth_type = claim.provider_snapshot.get("authType")
    saved_base_url = claim.provider_snapshot.get("baseUrl")
    if (
        not isinstance(provider_id, str)
        or provider_id != claim.provider_id
        or not isinstance(saved_auth_type, str)
        or not isinstance(saved_base_url, str)
        or not saved_base_url
    ):
        raise ProviderError(
            "provider_configuration_invalid",
            "The saved image Provider configuration is invalid",
        )

    api_key = ""
    with db_factory() as db:
        try:
            provider = db.get(ImageProviderConnection, provider_id)
            if (
                provider is None
                or not provider.enabled
                or provider.adapter_type != adapter_type
                or provider.auth_type != saved_auth_type
            ):
                raise ProviderError(
                    "provider_unavailable",
                    "The selected image Provider is unavailable",
                )
            if provider.auth_type != "none":
                from services.canvas.credentials import ProviderSecretCodec
                from services.canvas.provider_catalog import load_provider_credential

                credential = load_provider_credential(
                    db,
                    provider_id=provider_id,
                    codec=ProviderSecretCodec.from_env(),
                )
                # load_provider_credential may soft-disable tampered ciphertext.
                db.commit()
                if credential is None or not isinstance(credential.get("apiKey"), str):
                    raise ProviderError(
                        "provider_missing_credential",
                        "Image Provider credential is not configured",
                    )
                api_key = credential["apiKey"]
            else:
                db.rollback()
        except ProviderError:
            if db.in_transaction():
                db.rollback()
            raise
        except Exception:
            if db.in_transaction():
                db.rollback()
            raise ProviderError(
                "provider_configuration_invalid",
                "The image Provider runtime configuration is invalid",
            ) from None

    try:
        from services.canvas.provider_network import (
            PinnedHttpCoreTransport,
            ProviderNetworkPolicy,
            SafeProviderHttpClient,
            validate_provider_base_url,
        )

        policy = network_policy or ProviderNetworkPolicy.from_config()
        origin = validate_provider_base_url(saved_base_url, policy=policy)
        safe_client = SafeProviderHttpClient(
            origin=origin,
            policy=policy,
            resolver=resolver,
            transport=request_transport,
        )
        public_result_transport = result_transport or PinnedHttpCoreTransport()
    except ProviderError:
        raise
    except Exception:
        raise ProviderError(
            "provider_network_policy_invalid",
            "The image Provider network policy rejected this configuration",
        ) from None
    return ProviderExecutionContext(
        adapter=adapter,
        runtime=ProviderRuntime(api_key=api_key, transport=safe_client),
        result_transport=public_result_transport,
    )


async def execute_claimed_attempt(
    claim: ClaimedAttempt,
    *,
    registry: ProviderRegistry,
    context: ProviderExecutionContext | None = None,
) -> AttemptExecutionResult:
    """Call a Provider using only the immutable claim; no Session may cross await."""

    try:
        if context is None:
            context = prepare_provider_execution_context(claim, registry=registry)
        adapter = context.adapter
        runtime = context.runtime
        capabilities_data = claim.model_snapshot.get("capabilities")
        if not isinstance(capabilities_data, dict):
            raise ProviderError(
                "provider_configuration_invalid",
                "The saved image model configuration is invalid",
            )
        capabilities = ModelCapabilities(**capabilities_data)
        request = ProviderGenerationRequest(
            prompt=claim.prompt,
            size=f"{claim.width}x{claim.height}",
            quantity=1,
            upstream_idempotency_key=(
                claim.upstream_idempotency_key
                if capabilities.supports_idempotency
                else None
            ),
        )
        adapter.validate_request(request, capabilities)
        if claim.status == "cancel_requested":
            if not claim.external_task_id:
                return AttemptExecutionResult(
                    kind="unknown",
                    safe_error_code="provider_task_missing",
                    safe_error_summary="The accepted Provider task cannot be cancelled without its task identifier",
                )
            cancelled = await adapter.cancel(
                ProviderSubmission(
                    status="pending",
                    external_task_id=claim.external_task_id,
                ),
                runtime,
            )
            if cancelled.kind == "cancelled":
                return AttemptExecutionResult(
                    kind="cancelled",
                    external_task_id=claim.external_task_id,
                )
            return AttemptExecutionResult(
                kind="pending",
                external_task_id=claim.external_task_id,
                safe_error_code="provider_cancel_unsupported",
                safe_error_summary="The Provider may continue executing and billing this task",
            )
        if claim.status == "polling":
            if not claim.external_task_id:
                return AttemptExecutionResult(
                    kind="unknown",
                    safe_error_code="provider_task_missing",
                    safe_error_summary="The saved Provider task identifier is unavailable",
                )
            polled: ProviderPollResult = await adapter.poll(
                ProviderSubmission(
                    status="pending",
                    external_task_id=claim.external_task_id,
                ),
                runtime,
            )
            if polled.kind == "pending":
                return AttemptExecutionResult(
                    kind="pending",
                    external_task_id=claim.external_task_id,
                )
            if polled.kind == "completed" and polled.image is not None:
                return AttemptExecutionResult(
                    kind="completed",
                    image=polled.image,
                    external_task_id=claim.external_task_id,
                )
            return AttemptExecutionResult(
                kind="failed",
                external_task_id=claim.external_task_id,
                safe_error_code="provider_poll_failed",
                safe_error_summary="The image Provider task did not complete",
            )
        submitted = await adapter.submit(request, runtime)
        if submitted.status == "pending":
            if not submitted.external_task_id:
                return AttemptExecutionResult(
                    kind="unknown",
                    provider_request_id=submitted.request_id,
                    safe_error_code="provider_task_missing",
                    safe_error_summary="The Provider accepted work without a recoverable task id",
                )
            return AttemptExecutionResult(
                kind="pending",
                provider_request_id=submitted.request_id,
                external_task_id=submitted.external_task_id,
            )
        if submitted.image is None:
            return AttemptExecutionResult(
                kind="failed",
                provider_request_id=submitted.request_id,
                safe_error_code="provider_response_invalid",
                safe_error_summary="The image Provider returned no image",
            )
        return AttemptExecutionResult(
            kind="completed",
            image=submitted.image,
            provider_request_id=submitted.request_id,
        )
    except ProviderError as exc:
        # A retryable transport failure after submission began has uncertain
        # upstream acceptance; never automatically submit it again.
        return AttemptExecutionResult(
            kind="unknown" if exc.retryable else "failed",
            safe_error_code=exc.code,
            safe_error_summary=exc.safe_message,
        )
    except Exception:
        return AttemptExecutionResult(
            kind="unknown",
            safe_error_code="provider_execution_unknown",
            safe_error_summary="The image Provider outcome could not be verified",
        )


async def materialize_completed_attempt(
    claim: ClaimedAttempt,
    *,
    result: AttemptExecutionResult,
    registry: ProviderRegistry,
    context: ProviderExecutionContext | None = None,
):
    """Receive a Provider image with no SQLAlchemy Session held open."""

    if result.kind != "completed" or result.image is None:
        raise ValueError("only completed Provider attempts can be materialized")
    transport = None
    if isinstance(result.image, ControlledRemoteImage):
        if context is None:
            context = prepare_provider_execution_context(claim, registry=registry)
        transport = context.result_transport
    from services.canvas.generation.results import materialize_provider_result

    return await materialize_provider_result(
        project_id=claim.project_id,
        attempt_id=claim.attempt_id,
        image=result.image,
        transport=transport,
    )


async def execute_and_materialize_claimed_attempt(
    claim: ClaimedAttempt,
    *,
    registry: ProviderRegistry,
    context: ProviderExecutionContext | None = None,
) -> tuple[AttemptExecutionResult, object | None]:
    """Provider execution and result download; deliberately DB-session-free."""

    result = await execute_claimed_attempt(claim, registry=registry, context=context)
    if result.kind != "completed":
        return result, None
    try:
        return result, await materialize_completed_attempt(
            claim,
            result=result,
            registry=registry,
            context=context,
        )
    except Exception:
        return (
            AttemptExecutionResult(
                kind="unknown",
                provider_request_id=result.provider_request_id,
                external_task_id=result.external_task_id,
                safe_error_code="provider_result_unavailable",
                safe_error_summary="The Provider image result could not be verified",
            ),
            None,
        )


def _aggregate_persisted_generation(
    db: Session,
    generation: CanvasGeneration,
    *,
    now: datetime | None = None,
) -> None:
    db.flush()
    statuses = list(
        db.scalars(
            select(CanvasGenerationItem.status).where(
                CanvasGenerationItem.generation_id == generation.id
            )
        ).all()
    )
    target = aggregate_generation_status(statuses, generation.status)
    if target != generation.status:
        transition_generation(generation.status, target)
        generation.status = target
    generation.succeeded_items = statuses.count("succeeded")
    generation.failed_items = statuses.count("failed")
    generation.cancelled_items = statuses.count("cancelled")
    generation.unknown_items = statuses.count("unknown")
    if target in {"succeeded", "partially_failed", "failed", "cancelled", "unknown"}:
        generation.completed_at = now or _utcnow()
        release_generation_reservation(db, generation_id=generation.id)


def persist_attempt_execution_result(
    db: Session,
    *,
    claim: ClaimedAttempt,
    result: AttemptExecutionResult,
    now: datetime,
) -> bool:
    """Persist only Provider outcome state; image persistence happens separately."""

    attempt = db.get(CanvasGenerationAttempt, claim.attempt_id)
    item = db.get(CanvasGenerationItem, claim.item_id)
    generation = db.get(CanvasGeneration, claim.generation_id)
    if (
        attempt is None
        or item is None
        or generation is None
        or attempt.worker_id != claim.claim_token
    ):
        return False
    attempt.provider_request_id = result.provider_request_id or attempt.provider_request_id
    attempt.external_task_id = result.external_task_id or attempt.external_task_id
    attempt.heartbeat_at = now
    attempt.lease_expires_at = None
    attempt.worker_id = None
    if result.kind == "pending":
        transition_attempt(attempt.status, "polling")
        attempt.status = "polling"
        attempt.next_poll_at = now + timedelta(seconds=2)
        attempt.submitted_at = attempt.submitted_at or now
        attempt.normalized_error_code = result.safe_error_code
        attempt.safe_error_summary = result.safe_error_summary
        append_generation_progress_event(
            db,
            generation=generation,
            item=item,
            attempt=attempt,
            event_type="generation.attempt.polling",
        )
        return True
    if result.kind == "cancelled":
        transition_attempt(attempt.status, "cancelled")
        attempt.status = "cancelled"
        attempt.completed_at = now
        transition_item(item.status, "cancelled")
        item.status = "cancelled"
        item.completed_at = now
        _aggregate_persisted_generation(db, generation, now=now)
        append_generation_progress_event(
            db,
            generation=generation,
            item=item,
            attempt=attempt,
            event_type="generation.item.cancelled",
        )
        return True
    if result.kind == "completed":
        transition_attempt(attempt.status, "succeeded")
        attempt.status = "succeeded"
        attempt.provider_accepted_at = now
        attempt.submitted_at = attempt.submitted_at or now
        attempt.provider_result_stage = "receiving"
        return True
    if result.kind == "failed":
        transition_attempt(attempt.status, "failed")
        attempt.status = "failed"
        attempt.normalized_error_code = result.safe_error_code
        attempt.safe_error_summary = result.safe_error_summary
        transition_item(item.status, "failed")
        item.status = "failed"
        item.safe_current_error_code = result.safe_error_code
        item.safe_current_error_summary = result.safe_error_summary
        item.completed_at = now
        _aggregate_persisted_generation(db, generation, now=now)
        append_generation_progress_event(
            db,
            generation=generation,
            item=item,
            attempt=attempt,
            event_type="generation.item.failed",
        )
        return True
    transition_attempt(attempt.status, "unknown")
    attempt.status = "unknown"
    attempt.normalized_error_code = result.safe_error_code
    attempt.safe_error_summary = result.safe_error_summary
    transition_item(item.status, "unknown")
    item.status = "unknown"
    item.safe_current_error_code = result.safe_error_code
    item.safe_current_error_summary = result.safe_error_summary
    _aggregate_persisted_generation(db, generation, now=now)
    append_generation_progress_event(
        db,
        generation=generation,
        item=item,
        attempt=attempt,
        event_type="generation.item.unknown",
    )
    return True


def recover_expired_generation_claims(db: Session, *, now: datetime) -> int:
    attempts = list(
        db.scalars(
            select(CanvasGenerationAttempt).where(
                CanvasGenerationAttempt.worker_id.is_not(None),
                CanvasGenerationAttempt.lease_expires_at < now,
            )
        ).all()
    )
    recovered = 0
    for attempt in attempts:
        if attempt.status == "submitting":
            transition_attempt(attempt.status, "unknown")
            attempt.status = "unknown"
            item = db.get(CanvasGenerationItem, attempt.item_id)
            if item is not None:
                if item.status not in {"succeeded", "failed", "cancelled", "unknown"}:
                    transition_item(item.status, "unknown")
                    item.status = "unknown"
                generation = db.get(CanvasGeneration, item.generation_id)
                if generation is not None:
                    _aggregate_persisted_generation(db, generation)
        attempt.worker_id = None
        attempt.lease_expires_at = None
        attempt.heartbeat_at = None
        recovered += 1
    return recovered


class CanvasGenerationWorker:
    """One lease-fenced paid-generation dispatcher with no Session across await."""

    def __init__(
        self,
        *,
        db_factory: Callable[[], Any],
        registry: ProviderRegistry,
        worker_id: str,
        poll_interval_seconds: float = 0.25,
        heartbeat_interval_seconds: float = 15.0,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        if not callable(db_factory):
            raise TypeError("db_factory must be callable")
        if not isinstance(worker_id, str) or not worker_id.strip():
            raise ValueError("worker_id must not be empty")
        if poll_interval_seconds <= 0 or heartbeat_interval_seconds <= 0:
            raise ValueError("worker intervals must be positive")
        self._db_factory = db_factory
        self._registry = registry
        self.worker_id = worker_id.strip()
        self._poll_interval_seconds = float(poll_interval_seconds)
        self._heartbeat_interval_seconds = float(heartbeat_interval_seconds)
        self._clock = clock
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._executor: ThreadPoolExecutor | None = None
        self._current_lock = threading.Lock()
        self._current_claim: ClaimedAttempt | None = None

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("Canvas generation worker has already been started")
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="canvas-generation-provider",
        )
        self._thread = threading.Thread(
            target=self._run,
            name="canvas-generation-dispatcher",
            daemon=True,
        )
        self._thread.start()

    def request_stop(self) -> None:
        self._stop_event.set()

    def join(self, *, timeout: float | None = None) -> bool:
        if self._thread is None:
            return True
        self._thread.join(timeout=timeout)
        return not self._thread.is_alive()

    def stop(self, *, graceful_timeout_seconds: float = 30.0) -> bool:
        if graceful_timeout_seconds < 0:
            raise ValueError("graceful_timeout_seconds must not be negative")
        self.request_stop()
        if self.join(timeout=graceful_timeout_seconds):
            return True
        return self.join(timeout=self._heartbeat_interval_seconds + 1.0)

    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _recover(self) -> None:
        with self._db_factory() as db:
            try:
                from services.canvas.generation.recovery import recover_canvas_generation_work

                recover_canvas_generation_work(db, now=self._clock())
                db.commit()
            except Exception:
                db.rollback()
                raise

    def _claim(self) -> ClaimedAttempt | None:
        with self._db_factory() as db:
            try:
                claim = claim_next_attempt(db, worker_id=self.worker_id, now=self._clock())
                db.commit()
                return claim
            except Exception:
                db.rollback()
                raise

    def _heartbeat(self, claim: ClaimedAttempt) -> bool:
        with self._db_factory() as db:
            try:
                current = heartbeat_claimed_attempt(db, claim=claim, now=self._clock())
                db.commit()
                return current
            except Exception:
                db.rollback()
                raise

    def _prepare(self, claim: ClaimedAttempt) -> bool:
        with self._db_factory() as db:
            try:
                ready = prepare_claimed_attempt_for_execution(
                    db,
                    claim=claim,
                    now=self._clock(),
                )
                db.commit()
                return ready
            except Exception:
                db.rollback()
                raise

    def _persist_noncompleted(
        self,
        claim: ClaimedAttempt,
        result: AttemptExecutionResult,
    ) -> None:
        with self._db_factory() as db:
            try:
                persist_attempt_execution_result(
                    db,
                    claim=claim,
                    result=result,
                    now=self._clock(),
                )
                db.commit()
            except Exception:
                db.rollback()
                raise

    def _promote_completed(self, claim: ClaimedAttempt, result: AttemptExecutionResult) -> None:
        with self._db_factory() as db:
            try:
                begin_immediate_if_sqlite(db)
                from services.canvas.generation.results import (
                    promote_materialized_provider_result,
                    remove_verified_temporary_result,
                )

                promote_materialized_provider_result(
                    db,
                    attempt_id=claim.attempt_id,
                    claim_token=claim.claim_token,
                    provider_request_id=result.provider_request_id,
                    external_task_id=result.external_task_id,
                    now=self._clock(),
                )
                db.commit()
            except Exception:
                db.rollback()
                raise
        # Cleanup happens only after the asset/preview/compose chain commits.
        remove_verified_temporary_result(
            project_id=claim.project_id,
            attempt_id=claim.attempt_id,
        )

    def _execute(self, claim: ClaimedAttempt) -> None:
        if not self._prepare(claim):
            return
        try:
            context = prepare_provider_execution_context(
                claim,
                registry=self._registry,
                db_factory=self._db_factory,
            )
        except ProviderError as exc:
            self._persist_noncompleted(
                claim,
                AttemptExecutionResult(
                    kind="failed",
                    safe_error_code=exc.code,
                    safe_error_summary=exc.safe_message,
                ),
            )
            return
        except Exception:
            self._persist_noncompleted(
                claim,
                AttemptExecutionResult(
                    kind="failed",
                    safe_error_code="provider_configuration_invalid",
                    safe_error_summary="The image Provider runtime configuration is invalid",
                ),
            )
            return
        executor = self._executor
        if executor is None:
            raise RuntimeError("Canvas generation executor is unavailable")
        future = executor.submit(
            lambda: asyncio.run(
                execute_and_materialize_claimed_attempt(
                    claim,
                    registry=self._registry,
                    context=context,
                )
            )
        )
        claim_is_current = True
        while True:
            try:
                result, materialized = future.result(timeout=self._heartbeat_interval_seconds)
                break
            except FutureTimeoutError:
                if claim_is_current:
                    try:
                        claim_is_current = self._heartbeat(claim)
                    except Exception:
                        logger.exception("Canvas generation heartbeat failed")
                        claim_is_current = False
        if not claim_is_current:
            return
        if result.kind == "completed" and materialized is not None:
            self._promote_completed(claim, result)
        else:
            self._persist_noncompleted(claim, result)

    def _run(self) -> None:
        try:
            while not self._stop_event.is_set():
                try:
                    self._recover()
                    claim = self._claim()
                except Exception:
                    logger.exception("Canvas generation queue recovery or claim failed")
                    self._stop_event.wait(self._poll_interval_seconds)
                    continue
                if claim is None:
                    self._stop_event.wait(self._poll_interval_seconds)
                    continue
                with self._current_lock:
                    self._current_claim = claim
                try:
                    self._execute(claim)
                except Exception:
                    logger.exception("Canvas generation execution failed")
                finally:
                    with self._current_lock:
                        self._current_claim = None
        finally:
            executor = self._executor
            if executor is not None:
                executor.shutdown(wait=True, cancel_futures=True)


__all__ = [
    "ClaimedAttempt",
    "AttemptExecutionResult",
    "ProviderExecutionContext",
    "CanvasGenerationWorker",
    "claim_next_attempt",
    "execute_claimed_attempt",
    "execute_and_materialize_claimed_attempt",
    "heartbeat_claimed_attempt",
    "materialize_completed_attempt",
    "persist_attempt_execution_result",
    "prepare_provider_execution_context",
    "prepare_claimed_attempt_for_execution",
    "recover_expired_generation_claims",
]
