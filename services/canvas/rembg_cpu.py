"""CPU-only mask generation primitives for Product Canvas cutouts."""
from __future__ import annotations

import io
import os
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any, Callable

from PIL import Image
from sqlalchemy import select

from canvas_models import CanvasAsset, CanvasAssetOperation
from config import CANVAS_REMBG_MODEL_DIR


REMBG_MODEL_NAME = "isnet-general-use"
REMBG_PROVIDERS = ("CPUExecutionProvider",)

RembgNewSession = Callable[..., Any]
RembgRemove = Callable[..., Any]
_REMBG_ENV_LOCK = Lock()


class CanvasRembgModelUnavailable(RuntimeError):
    """Stable public failure for a missing or unusable local rembg runtime."""

    code = "rembg_model_unavailable"
    message = "Background removal model is unavailable"
    retryable = True

    def __init__(self) -> None:
        super().__init__(self.message)

    @property
    def safe_error(self) -> dict[str, str | bool]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
        }


class CanvasCutoutClaimLost(RuntimeError):
    """Raised when a worker no longer owns the operation attempt it computed."""


class CanvasCutoutProcessingFailed(RuntimeError):
    code = "cutout_processing_failed"
    message = "Product cutout could not be completed"
    retryable = True

    def __init__(self) -> None:
        super().__init__(self.message)

    @property
    def safe_error(self) -> dict[str, str | bool]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
        }


def _load_rembg_api() -> tuple[RembgNewSession, RembgRemove]:
    from rembg import new_session, remove

    return new_session, remove


def apply_alpha_to_source_rgb(source: Image.Image, mask: Image.Image) -> Image.Image:
    """Combine source-owned RGB channels with one grayscale rembg mask."""

    if not isinstance(source, Image.Image):
        raise TypeError("source must be a Pillow Image")
    if not isinstance(mask, Image.Image):
        raise TypeError("mask must be a Pillow Image")
    if source.mode not in {"RGB", "RGBA"}:
        raise ValueError("source image mode must be RGB or RGBA")
    if mask.mode != "L":
        raise ValueError("mask mode must be L")
    if mask.size != source.size:
        raise ValueError("mask dimensions must match the source image")
    if source.width <= 0 or source.height <= 0:
        raise ValueError("source image dimensions must be positive")

    red, green, blue = source.split()[:3]
    output = Image.merge("RGBA", (red, green, blue, mask.copy()))
    output.load()
    return output


def encode_deterministic_png(image: Image.Image) -> bytes:
    """Encode RGB/RGBA pixels as a metadata-free deterministic PNG."""

    if not isinstance(image, Image.Image):
        raise TypeError("image must be a Pillow Image")
    if image.mode not in {"RGB", "RGBA"}:
        raise ValueError("PNG image mode must be RGB or RGBA")
    canonical = image.copy()
    canonical.info.clear()
    output = io.BytesIO()
    canonical.save(
        output,
        format="PNG",
        optimize=False,
        compress_level=9,
    )
    return output.getvalue()


class RembgMasker:
    """Lazily own one CPU rembg session and its controlled model cache."""

    def __init__(self, *, model_dir: str | os.PathLike[str] | None = None) -> None:
        configured_dir = CANVAS_REMBG_MODEL_DIR if model_dir is None else model_dir
        self._model_dir = Path(configured_dir).expanduser().resolve()
        self._session: Any | None = None
        self._remove: RembgRemove | None = None
        self._session_lock = Lock()

    def get_session(self) -> Any:
        if self._session is not None:
            return self._session
        with self._session_lock:
            if self._session is None:
                try:
                    self._model_dir.mkdir(parents=True, exist_ok=True)
                    with _REMBG_ENV_LOCK:
                        had_model_home = "U2NET_HOME" in os.environ
                        previous_model_home = os.environ.get("U2NET_HOME")
                        os.environ["U2NET_HOME"] = str(self._model_dir)
                        try:
                            new_session, remove = _load_rembg_api()
                            session = new_session(
                                REMBG_MODEL_NAME,
                                providers=list(REMBG_PROVIDERS),
                            )
                        finally:
                            if had_model_home:
                                os.environ["U2NET_HOME"] = previous_model_home or ""
                            else:
                                os.environ.pop("U2NET_HOME", None)
                    if session is None:
                        raise RuntimeError("rembg returned no session")
                except CanvasRembgModelUnavailable:
                    raise
                except Exception as exc:
                    self._remove = None
                    raise CanvasRembgModelUnavailable() from exc
                self._session = session
                self._remove = remove
        return self._session

    def create_mask(self, image: Image.Image) -> Image.Image:
        if not isinstance(image, Image.Image):
            raise TypeError("image must be a Pillow Image")
        if image.mode not in {"RGB", "RGBA"}:
            raise ValueError("rembg source image mode must be RGB or RGBA")
        if image.width <= 0 or image.height <= 0:
            raise ValueError("rembg source image dimensions must be positive")

        session = self.get_session()
        if self._remove is None:
            raise CanvasRembgModelUnavailable()
        try:
            mask = self._remove(
                image.copy(),
                only_mask=True,
                session=session,
            )
        except CanvasRembgModelUnavailable:
            raise
        except Exception as exc:
            raise CanvasRembgModelUnavailable() from exc
        if not isinstance(mask, Image.Image):
            raise ValueError("rembg mask must be a Pillow Image")
        if mask.mode != "L":
            raise ValueError("rembg mask mode must be L")
        if mask.size != image.size:
            raise ValueError("rembg mask dimensions must match the source image")
        copied_mask = mask.copy()
        copied_mask.load()
        return copied_mask


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _claim_input(
    db: Any,
    *,
    operation_id: str,
    worker_id: str | None,
    attempt_count: int | None,
) -> tuple[CanvasAssetOperation, CanvasAsset]:
    operation = db.execute(
        select(CanvasAssetOperation).where(CanvasAssetOperation.id == operation_id)
    ).scalar_one_or_none()
    if operation is None or operation.operation_type != "cutout":
        raise CanvasCutoutClaimLost("cutout operation is unavailable")
    effective_worker = operation.worker_id if worker_id is None else worker_id
    effective_attempt = operation.attempt_count if attempt_count is None else attempt_count
    if (
        operation.status != "running"
        or not effective_worker
        or operation.worker_id != effective_worker
        or operation.attempt_count != effective_attempt
    ):
        raise CanvasCutoutClaimLost("cutout operation claim is no longer current")
    working = db.execute(
        select(CanvasAsset).where(
            CanvasAsset.id == operation.input_asset_id,
            CanvasAsset.project_id == operation.project_id,
            CanvasAsset.asset_type == "working",
            CanvasAsset.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if working is None or working.mime_type != "image/png":
        raise CanvasCutoutProcessingFailed()
    return operation, working


def _persist_failure(
    db_factory: Callable[[], Any],
    *,
    operation_id: str,
    worker_id: str,
    attempt_count: int,
    safe_error: dict[str, Any],
) -> None:
    from services.canvas import operations

    with db_factory() as db:
        try:
            updated = operations.mark_claimed_operation_failed(
                db,
                operation_id=operation_id,
                worker_id=worker_id,
                attempt_count=attempt_count,
                safe_error=safe_error,
                now=_utcnow(),
            )
            if not updated:
                db.rollback()
                raise CanvasCutoutClaimLost(
                    "cutout operation claim was lost before failure persistence"
                )
            db.commit()
        except Exception:
            db.rollback()
            raise


def run_cutout_operation(
    operation_id: str,
    *,
    masker: RembgMasker,
    db_factory: Callable[[], Any] | None = None,
    worker_id: str | None = None,
    attempt_count: int | None = None,
) -> CanvasAsset:
    """Run mask-only CPU work outside DB sessions and atomically publish its pair."""

    if db_factory is None:
        from database import SessionLocal

        db_factory = SessionLocal

    from services.canvas import assets, operations, previews

    effective_worker: str | None = None
    effective_attempt: int | None = None
    try:
        with db_factory() as db:
            operation, working = _claim_input(
                db,
                operation_id=operation_id,
                worker_id=worker_id,
                attempt_count=attempt_count,
            )
            effective_worker = operation.worker_id
            effective_attempt = operation.attempt_count
            project_id = operation.project_id
            working_id = working.id
            working_sha256 = working.sha256
            source_bytes = assets.read_verified_asset_bytes(
                db,
                asset=working,
                project_id=project_id,
            )
    except CanvasCutoutClaimLost:
        raise
    except Exception as exc:
        safe_failure = CanvasCutoutProcessingFailed()
        if effective_worker is not None and effective_attempt is not None:
            _persist_failure(
                db_factory,
                operation_id=operation_id,
                worker_id=effective_worker,
                attempt_count=effective_attempt,
                safe_error=safe_failure.safe_error,
            )
        raise safe_failure from exc

    source: Image.Image | None = None
    mask: Image.Image | None = None
    output: Image.Image | None = None
    try:
        with Image.open(io.BytesIO(source_bytes)) as decoded:
            decoded.load()
            if decoded.format != "PNG" or decoded.mode not in {"RGB", "RGBA"}:
                raise CanvasCutoutProcessingFailed()
            source = decoded.copy()
        mask = masker.create_mask(source)
        output = apply_alpha_to_source_rgb(source, mask)
        cutout_bytes = encode_deterministic_png(output)
    except CanvasRembgModelUnavailable as exc:
        _persist_failure(
            db_factory,
            operation_id=operation_id,
            worker_id=effective_worker,
            attempt_count=effective_attempt,
            safe_error=exc.safe_error,
        )
        raise
    except CanvasCutoutClaimLost:
        raise
    except Exception as exc:
        safe_failure = CanvasCutoutProcessingFailed()
        _persist_failure(
            db_factory,
            operation_id=operation_id,
            worker_id=effective_worker,
            attempt_count=effective_attempt,
            safe_error=safe_failure.safe_error,
        )
        raise safe_failure from exc
    finally:
        if output is not None:
            output.close()
        if mask is not None:
            mask.close()
        if source is not None:
            source.close()

    with db_factory() as db:
        try:
            current, working = _claim_input(
                db,
                operation_id=operation_id,
                worker_id=effective_worker,
                attempt_count=effective_attempt,
            )
            if working.sha256 != working_sha256 or working.id != working_id:
                raise CanvasCutoutClaimLost("cutout input identity changed")
            cutout = assets.persist_derived_image(
                db,
                project_id=project_id,
                asset_type="cutout",
                data=cutout_bytes,
                mime_type="image/png",
                source_asset_id=working_id,
                metadata={
                    "inputAssetId": working_id,
                    "inputSha256": working_sha256,
                    "operationId": operation_id,
                    "processorVersion": operations.AUTOMATIC_CUTOUT_PROCESSOR_VERSION,
                },
                processor_version=operations.AUTOMATIC_CUTOUT_PROCESSOR_VERSION,
            )
            cutout.transparency_status = "transparent"
            preview = previews.create_preview_proxy(
                db,
                project_id=project_id,
                source_asset=cutout,
            )
            completed = operations.mark_claimed_operation_succeeded(
                db,
                operation_id=current.id,
                worker_id=effective_worker,
                attempt_count=effective_attempt,
                output_asset_id=cutout.id,
                now=_utcnow(),
            )
            if completed is None:
                raise CanvasCutoutClaimLost(
                    "cutout operation claim was lost before result persistence"
                )
            db.flush()
            db.expunge(cutout)
            db.commit()
            return cutout
        except CanvasCutoutClaimLost:
            db.rollback()
            raise
        except Exception as exc:
            db.rollback()
            safe_failure = CanvasCutoutProcessingFailed()
            _persist_failure(
                db_factory,
                operation_id=operation_id,
                worker_id=effective_worker,
                attempt_count=effective_attempt,
                safe_error=safe_failure.safe_error,
            )
            raise safe_failure from exc


__all__ = [
    "CanvasRembgModelUnavailable",
    "CanvasCutoutClaimLost",
    "CanvasCutoutProcessingFailed",
    "REMBG_MODEL_NAME",
    "REMBG_PROVIDERS",
    "RembgMasker",
    "apply_alpha_to_source_rgb",
    "encode_deterministic_png",
    "run_cutout_operation",
]
