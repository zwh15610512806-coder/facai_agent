"""Typed Product Canvas runtime factories and the pre-lifespan test seam."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import uuid4

from fastapi import FastAPI
from PIL import Image


_RUNTIME_STATE_ATTRIBUTE = "_product_canvas_runtime_state"
_RUNTIME_HANDLE_ATTRIBUTE = "_product_canvas_runtime_handle"


class CanvasRuntimeConfigurationError(RuntimeError):
    """Raised when runtime factories are changed outside the safe setup window."""


class CanvasRuntimeShutdownError(RuntimeError):
    """Raised when a CPU worker is still active after its shutdown deadline."""


class CanvasMasker(Protocol):
    def create_mask(self, image: Image.Image) -> Image.Image: ...


MaskerFactory = Callable[[], CanvasMasker]
ComposeRunner = Callable[..., Any]
ProviderRegistryFactory = Callable[[], object]
ModelProfileSeedFactory = Callable[[Callable[[], object]], None]


def create_image_provider_runtime(
    adapter_type: str,
    *,
    transport: object | None = None,
):
    """Create a credential-redacted runtime for a registered built-in adapter."""

    from services.canvas.provider_network import PinnedHttpCoreTransport
    from services.canvas.provider_schemas import ProviderRuntime

    if adapter_type != "seedream":
        raise CanvasRuntimeConfigurationError("Image Provider adapter is not configured")
    from services.canvas.providers.seedream import resolve_seedream_api_key

    return ProviderRuntime(
        api_key=resolve_seedream_api_key(),
        transport=transport if transport is not None else PinnedHttpCoreTransport(),
    )


def _production_masker_factory() -> CanvasMasker:
    # Kept lazy so importing the FastAPI app never imports or initializes ONNX/rembg.
    from services.canvas.rembg_cpu import RembgMasker

    return RembgMasker()


def _production_compose_runner(operation_id: str, **kwargs: Any) -> Any:
    from services.canvas.compose_operations import run_compose_operation

    return run_compose_operation(operation_id, **kwargs)


def _production_provider_registry_factory() -> object:
    """Resolve the process-wide production adapter registry only at startup."""

    from services.canvas.providers.registry import provider_registry

    return provider_registry


def _production_model_profile_seed_factory(_: Callable[[], object]) -> None:
    """Production profiles are bootstrapped by the application lifespan."""


@dataclass(frozen=True)
class CanvasRuntimeFactories:
    masker_factory: MaskerFactory
    compose_runner: ComposeRunner
    provider_registry_factory: ProviderRegistryFactory
    model_profile_seed_factory: ModelProfileSeedFactory


@dataclass(frozen=True)
class CanvasRuntimeHandle:
    rembg_worker: object
    local_worker: object
    generation_worker: object


@dataclass
class _CanvasRuntimeState:
    factories: CanvasRuntimeFactories
    has_started: bool = False
    active: bool = False


def _runtime_state(app: FastAPI) -> _CanvasRuntimeState:
    state = getattr(app.state, _RUNTIME_STATE_ATTRIBUTE, None)
    if state is None:
        state = _CanvasRuntimeState(
            factories=CanvasRuntimeFactories(
                masker_factory=_production_masker_factory,
                compose_runner=_production_compose_runner,
                provider_registry_factory=_production_provider_registry_factory,
                model_profile_seed_factory=_production_model_profile_seed_factory,
            )
        )
        setattr(app.state, _RUNTIME_STATE_ATTRIBUTE, state)
    if not isinstance(state, _CanvasRuntimeState):
        raise CanvasRuntimeConfigurationError("Canvas runtime state is invalid")
    return state


def configure_canvas_test_runtime(
    app: FastAPI,
    *,
    masker_factory: MaskerFactory,
    compose_runner: ComposeRunner | None = None,
    provider_registry_factory: ProviderRegistryFactory | None = None,
    model_profile_seed_factory: ModelProfileSeedFactory | None = None,
) -> None:
    """Install test-only factories before the application's first lifespan starts."""

    if not callable(masker_factory):
        raise CanvasRuntimeConfigurationError("masker_factory must be callable")
    if compose_runner is not None and not callable(compose_runner):
        raise CanvasRuntimeConfigurationError("compose_runner must be callable")
    if provider_registry_factory is not None and not callable(provider_registry_factory):
        raise CanvasRuntimeConfigurationError("provider_registry_factory must be callable")
    if model_profile_seed_factory is not None and not callable(model_profile_seed_factory):
        raise CanvasRuntimeConfigurationError("model_profile_seed_factory must be callable")
    state = _runtime_state(app)
    if state.has_started or state.active:
        raise CanvasRuntimeConfigurationError(
            "Canvas test runtime must be configured before lifespan startup"
        )
    state.factories = CanvasRuntimeFactories(
        masker_factory=masker_factory,
        compose_runner=compose_runner or _production_compose_runner,
        provider_registry_factory=(
            provider_registry_factory or _production_provider_registry_factory
        ),
        model_profile_seed_factory=(
            model_profile_seed_factory or _production_model_profile_seed_factory
        ),
    )


def begin_canvas_runtime(app: FastAPI) -> CanvasRuntimeFactories:
    """Seal runtime configuration for this process and mark the lifespan active."""

    state = _runtime_state(app)
    if state.active:
        raise CanvasRuntimeConfigurationError("Canvas runtime is already active")
    state.has_started = True
    state.active = True
    return state.factories


def end_canvas_runtime(app: FastAPI) -> None:
    """Mark runtime shutdown without reopening the test-configuration seam."""

    state = getattr(app.state, _RUNTIME_STATE_ATTRIBUTE, None)
    if state is None:
        return
    if not isinstance(state, _CanvasRuntimeState):
        raise CanvasRuntimeConfigurationError("Canvas runtime state is invalid")
    state.active = False


def cleanup_canvas_temporary_files(db_factory: Callable[[], object]) -> int:
    """Remove only old unreferenced upload temporaries before workers start."""

    from sqlalchemy import select

    from canvas_models import CanvasAsset
    from services.canvas import storage

    with db_factory() as db:
        rows = db.execute(
            select(CanvasAsset.project_id, CanvasAsset.relative_path)
        ).all()
    references = {
        f"{project_id}/{relative_path}"
        for project_id, relative_path in rows
    }
    return storage.cleanup_stale_temporary_files(
        referenced_relative_paths=references,
    )


def start_canvas_runtime(
    app: FastAPI,
    *,
    db_factory: Callable[[], object],
) -> CanvasRuntimeHandle:
    """Start rembg, local composition, and the paid Generation queue."""

    if not callable(db_factory):
        raise CanvasRuntimeConfigurationError("db_factory must be callable")
    factories = begin_canvas_runtime(app)
    try:
        from services.canvas.operation_worker import CanvasOperationWorker
        from services.canvas.rembg_cpu import run_cutout_operation
        from services.canvas.exports import run_export_operation
        from services.canvas.generation.worker import CanvasGenerationWorker

        factories.model_profile_seed_factory(db_factory)
        registry = factories.provider_registry_factory()
        cleanup_canvas_temporary_files(db_factory)
        masker = factories.masker_factory()

        def handle_cutout(claimed: object) -> None:
            run_cutout_operation(
                claimed.id,
                masker=masker,
                db_factory=db_factory,
                worker_id=claimed.worker_id,
                attempt_count=claimed.attempt_count,
            )

        def handle_compose(claimed: object) -> None:
            factories.compose_runner(
                claimed.id,
                db_factory=db_factory,
                worker_id=claimed.worker_id,
                attempt_count=claimed.attempt_count,
            )

        def handle_export(claimed: object) -> None:
            run_export_operation(
                claimed.id,
                db_factory=db_factory,
                worker_id=claimed.worker_id,
                attempt_count=claimed.attempt_count,
            )

        rembg_worker = CanvasOperationWorker(
            db_factory=db_factory,
            lane="rembg",
            worker_id=f"rembg-{uuid4()}",
            handlers={"cutout": handle_cutout},
        )
        local_worker = CanvasOperationWorker(
            db_factory=db_factory,
            lane="local",
            worker_id=f"local-{uuid4()}",
            handlers={"compose": handle_compose, "export": handle_export},
        )
        generation_worker = CanvasGenerationWorker(
            db_factory=db_factory,
            registry=registry,
            worker_id=f"generation-{uuid4()}",
        )
        handle = CanvasRuntimeHandle(
            rembg_worker=rembg_worker,
            local_worker=local_worker,
            generation_worker=generation_worker,
        )
        setattr(app.state, _RUNTIME_HANDLE_ATTRIBUTE, handle)
        rembg_worker.start()
        try:
            local_worker.start()
        except Exception as exc:
            if not rembg_worker.stop():
                raise CanvasRuntimeShutdownError(
                    "Canvas rembg worker is still active after local startup failed"
                ) from exc
            raise
        try:
            generation_worker.start()
        except Exception as exc:
            if not local_worker.stop():
                raise CanvasRuntimeShutdownError(
                    "Canvas local worker is still active after generation startup failed"
                ) from exc
            if not rembg_worker.stop():
                raise CanvasRuntimeShutdownError(
                    "Canvas rembg worker is still active after generation startup failed"
                ) from exc
            raise
        return handle
    except CanvasRuntimeShutdownError:
        # Preserve the handle and active state so stop_canvas_runtime can retry.
        raise
    except Exception:
        if hasattr(app.state, _RUNTIME_HANDLE_ATTRIBUTE):
            delattr(app.state, _RUNTIME_HANDLE_ATTRIBUTE)
        end_canvas_runtime(app)
        raise


def stop_canvas_runtime(app: FastAPI) -> None:
    """Stop every Canvas worker in reverse startup order and seal the test seam."""

    handle = getattr(app.state, _RUNTIME_HANDLE_ATTRIBUTE, None)
    if handle is None:
        end_canvas_runtime(app)
        return
    if not handle.generation_worker.stop():
        raise CanvasRuntimeShutdownError(
            "Canvas generation worker is still active after its shutdown deadline"
        )
    if not handle.local_worker.stop():
        raise CanvasRuntimeShutdownError(
            "Canvas local worker is still active after its shutdown deadline"
        )
    if not handle.rembg_worker.stop():
        raise CanvasRuntimeShutdownError(
            "Canvas CPU worker is still active after its shutdown deadline"
        )
    delattr(app.state, _RUNTIME_HANDLE_ATTRIBUTE)
    end_canvas_runtime(app)


__all__ = [
    "CanvasMasker",
    "ComposeRunner",
    "CanvasRuntimeConfigurationError",
    "CanvasRuntimeShutdownError",
    "CanvasRuntimeFactories",
    "CanvasRuntimeHandle",
    "MaskerFactory",
    "ModelProfileSeedFactory",
    "ProviderRegistryFactory",
    "begin_canvas_runtime",
    "cleanup_canvas_temporary_files",
    "configure_canvas_test_runtime",
    "create_image_provider_runtime",
    "end_canvas_runtime",
    "start_canvas_runtime",
    "stop_canvas_runtime",
]
