"""Deterministic, offline-only image Provider used by the isolated Canvas E2E server."""
from __future__ import annotations

import hashlib
import io
import json
from collections import Counter
from dataclasses import asdict
from threading import Lock

from PIL import Image

from canvas_models import ImageModelProfile, ImageProviderConnection
from services.canvas.provider_schemas import (
    ControlledImageBytes,
    ModelCapabilities,
    ProviderCancelResult,
    ProviderError,
    ProviderGenerationRequest,
    ProviderPollResult,
    ProviderRecoveryFoundCompleted,
    ProviderRecoveryFoundPending,
    ProviderRecoveryNotFound,
    ProviderRuntime,
    ProviderSubmission,
)
from services.canvas.providers.registry import ProviderRegistry


E2E_FAKE_PROVIDER_ID = "e2e-fake-provider"
E2E_FAKE_SYNC_MODEL_PROFILE_ID = "e2e-fake-sync"
E2E_FAKE_ASYNC_MODEL_PROFILE_ID = "e2e-fake-async"
E2E_FAKE_ADAPTER_TYPE = "canvas_e2e_fake"


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))


SYNC_CAPABILITIES = ModelCapabilities(
    text_to_image=True,
    image_to_image=True,
    mask_edit=False,
    allowed_ratios=(),
    allowed_sizes=(),
    min_width=1,
    max_width=2_048,
    min_height=1,
    max_height=2_048,
    max_quantity=1,
    max_reference_images=1,
    reference_transfer="bytes",
    protocol="sync",
    supports_cancel=False,
    supports_idempotency=True,
    supports_idempotency_lookup=True,
    concurrency_limit=2,
    price_metadata={"amount": 0, "currency": "E2E"},
)

ASYNC_CAPABILITIES = ModelCapabilities(
    text_to_image=True,
    image_to_image=True,
    mask_edit=True,
    allowed_ratios=(),
    allowed_sizes=(),
    min_width=1,
    max_width=2_048,
    min_height=1,
    max_height=2_048,
    max_quantity=1,
    max_reference_images=1,
    reference_transfer="bytes",
    protocol="async",
    supports_cancel=True,
    supports_idempotency=True,
    supports_idempotency_lookup=True,
    concurrency_limit=1,
    price_metadata={"amount": 0, "currency": "E2E"},
)


class _OfflineTransport:
    async def request(self, **_: object):
        raise AssertionError("the deterministic E2E Provider must not use network transport")


class FakeCanvasProvider:
    """A keyed local Provider with opt-in prompt scenarios for browser recovery tests."""

    adapter_type = E2E_FAKE_ADAPTER_TYPE
    capabilities = ASYNC_CAPABILITIES

    def __init__(self) -> None:
        self._lock = Lock()
        self._submissions: dict[str, ProviderSubmission] = {}
        self._images: dict[str, ControlledImageBytes] = {}
        self._polls_remaining: dict[str, int] = {}
        self._cancelled: set[str] = set()
        self._failed_once_prompts: set[str] = set()
        self._uncertain_once_prompts: set[str] = set()
        self._submits_by_key: Counter[str] = Counter()
        self._submit_count = 0
        self._poll_count = 0
        self._cancel_count = 0

    @staticmethod
    def _key(request: ProviderGenerationRequest) -> str:
        return request.upstream_idempotency_key or f"no-key:{request.prompt}:{request.size}"

    @staticmethod
    def _image(request: ProviderGenerationRequest) -> ControlledImageBytes:
        try:
            width_text, height_text = request.size.split("x", 1)
            width = int(width_text)
            height = int(height_text)
        except (AttributeError, ValueError) as exc:
            raise ProviderError("fake_size_invalid", "The fake Provider requires a valid size") from exc
        if not 1 <= width <= 2_048 or not 1 <= height <= 2_048:
            raise ProviderError("fake_size_invalid", "The fake Provider size is out of bounds")
        digest = hashlib.sha256(
            (
                "facai-canvas-e2e-provider-v1\0"
                f"{request.prompt}\0{request.size}\0{request.upstream_idempotency_key or ''}"
            ).encode("utf-8")
        ).digest()
        image = Image.new("RGB", (width, height), tuple(digest[:3]))
        output = io.BytesIO()
        try:
            image.save(output, format="PNG", compress_level=9, optimize=False)
            return ControlledImageBytes(data=output.getvalue())
        finally:
            image.close()

    def runtime_factory(self) -> ProviderRuntime:
        return ProviderRuntime(api_key="e2e-offline", transport=_OfflineTransport())

    def validate_request(
        self,
        request: ProviderGenerationRequest,
        capabilities: ModelCapabilities,
    ) -> None:
        if not isinstance(request.prompt, str) or not request.prompt.strip():
            raise ProviderError("fake_prompt_invalid", "The fake Provider requires a prompt")
        if request.quantity != 1:
            raise ProviderError("fake_quantity_invalid", "The fake Provider accepts one image per request")
        if capabilities.max_reference_images < len(request.reference_images):
            raise ProviderError("fake_reference_invalid", "The fake Provider received too many references")

    async def submit(
        self,
        request: ProviderGenerationRequest,
        runtime: ProviderRuntime,
    ) -> ProviderSubmission:
        del runtime
        self.validate_request(request, self.capabilities)
        key = self._key(request)
        with self._lock:
            existing = self._submissions.get(key)
            if existing is not None:
                return existing
            self._submit_count += 1
            self._submits_by_key[key] += 1
            if "[e2e:fail-once]" in request.prompt and request.prompt not in self._failed_once_prompts:
                self._failed_once_prompts.add(request.prompt)
                raise ProviderError("fake_forced_failure", "The E2E Provider forced this item to fail")
            if (
                "[e2e:uncertain-once]" in request.prompt
                and request.prompt not in self._uncertain_once_prompts
            ):
                self._uncertain_once_prompts.add(request.prompt)
                raise ProviderError(
                    "fake_uncertain_submission",
                    "The E2E Provider could not verify the accepted request",
                    retryable=True,
                )
            if "[e2e:fail]" in request.prompt:
                raise ProviderError("fake_forced_failure", "The E2E Provider forced this item to fail")
            if "[e2e:uncertain]" in request.prompt:
                raise ProviderError(
                    "fake_uncertain_submission",
                    "The E2E Provider could not verify the accepted request",
                    retryable=True,
                )
            image = self._image(request)
            if "[e2e:async]" in request.prompt or "[e2e:delay]" in request.prompt or "[e2e:cancel-delay]" in request.prompt:
                external_task_id = f"fake-task:{hashlib.sha256(key.encode('utf-8')).hexdigest()[:24]}"
                submission = ProviderSubmission(
                    status="pending",
                    request_id=f"fake-request:{len(self._submissions) + 1}",
                    external_task_id=external_task_id,
                )
                self._submissions[key] = submission
                self._images[external_task_id] = image
                # The cancellation test must retain a Provider task long enough
                # to issue its saved-task cancellation.  Normal delayed work
                # stays short so the browser idempotency scenario remains fast.
                if "[e2e:cancel-delay]" in request.prompt:
                    self._polls_remaining[external_task_id] = 120
                else:
                    self._polls_remaining[external_task_id] = 2 if "[e2e:delay]" in request.prompt else 1
                return submission
            submission = ProviderSubmission(
                status="completed",
                request_id=f"fake-request:{len(self._submissions) + 1}",
                image=image,
            )
            self._submissions[key] = submission
            return submission

    async def poll(
        self,
        submission: ProviderSubmission,
        runtime: ProviderRuntime,
    ) -> ProviderPollResult:
        del runtime
        task_id = submission.external_task_id
        if task_id is None:
            return ProviderPollResult(kind="failed")
        with self._lock:
            self._poll_count += 1
            if task_id in self._cancelled:
                return ProviderPollResult(kind="failed")
            remaining = self._polls_remaining.get(task_id)
            image = self._images.get(task_id)
            if remaining is None or image is None:
                return ProviderPollResult(kind="failed")
            if remaining > 0:
                self._polls_remaining[task_id] = remaining - 1
                return ProviderPollResult(kind="pending")
            return ProviderPollResult(kind="completed", image=image)

    async def cancel(
        self,
        submission: ProviderSubmission,
        runtime: ProviderRuntime,
    ) -> ProviderCancelResult:
        del runtime
        task_id = submission.external_task_id
        with self._lock:
            self._cancel_count += 1
            if task_id is None or task_id not in self._images:
                return ProviderCancelResult(kind="already_terminal")
            self._cancelled.add(task_id)
            return ProviderCancelResult(kind="cancelled")

    async def recover_by_idempotency_key(
        self,
        upstream_key: str,
        runtime: ProviderRuntime,
    ):
        del runtime
        with self._lock:
            submission = self._submissions.get(upstream_key)
            if submission is None:
                return ProviderRecoveryNotFound()
            if submission.status == "pending":
                return ProviderRecoveryFoundPending(submission=submission)
            # The recovery contract has no local-bytes completed shape. A
            # completed local result is already persisted by this test runtime.
            return ProviderRecoveryFoundCompleted(image=None)

    def audit_snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "submitCount": self._submit_count,
                "pollCount": self._poll_count,
                "cancelCount": self._cancel_count,
                "submitsByIdempotencyKey": dict(sorted(self._submits_by_key.items())),
            }

    def reset_audit(self) -> None:
        with self._lock:
            self._submissions.clear()
            self._images.clear()
            self._polls_remaining.clear()
            self._cancelled.clear()
            self._failed_once_prompts.clear()
            self._uncertain_once_prompts.clear()
            self._submits_by_key.clear()
            self._submit_count = 0
            self._poll_count = 0
            self._cancel_count = 0


def build_e2e_provider_registry(provider: FakeCanvasProvider) -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(provider)
    return registry


def seed_e2e_model_profiles(db_factory) -> None:
    """Idempotently create the only no-network models available to E2E Canvas."""

    profiles = (
        (E2E_FAKE_SYNC_MODEL_PROFILE_ID, "fake-sync-v1", "Fake Sync", SYNC_CAPABILITIES),
        (E2E_FAKE_ASYNC_MODEL_PROFILE_ID, "fake-async-v1", "Fake Async", ASYNC_CAPABILITIES),
    )
    with db_factory() as db:
        provider = db.get(ImageProviderConnection, E2E_FAKE_PROVIDER_ID)
        if provider is None:
            provider = ImageProviderConnection(
                id=E2E_FAKE_PROVIDER_ID,
                adapter_type=E2E_FAKE_ADAPTER_TYPE,
                name="E2E Fake Provider",
                base_url="http://e2e.invalid/offline",
                auth_type="none",
                encrypted_credential=None,
                environment_credential_ref=None,
                credential_hint="Isolated test Provider",
                enabled=True,
                config_version=1,
            )
            db.add(provider)
        else:
            provider.adapter_type = E2E_FAKE_ADAPTER_TYPE
            provider.name = "E2E Fake Provider"
            provider.base_url = "http://e2e.invalid/offline"
            provider.auth_type = "none"
            provider.encrypted_credential = None
            provider.environment_credential_ref = None
            provider.credential_hint = "Isolated test Provider"
            provider.enabled = True
            provider.config_version = 1
        db.flush()
        for profile_id, model_id, display_name, capabilities in profiles:
            profile = db.get(ImageModelProfile, profile_id)
            if profile is None:
                profile = ImageModelProfile(
                    id=profile_id,
                    provider_id=E2E_FAKE_PROVIDER_ID,
                    model_id=model_id,
                    display_name=display_name,
                    capabilities_json=_json(asdict(capabilities)),
                    config_json=_json({"offline": True, "testOnly": True}),
                    enabled=True,
                    config_version=1,
                )
                db.add(profile)
            else:
                profile.provider_id = E2E_FAKE_PROVIDER_ID
                profile.model_id = model_id
                profile.display_name = display_name
                profile.capabilities_json = _json(asdict(capabilities))
                profile.config_json = _json({"offline": True, "testOnly": True})
                profile.enabled = True
                profile.config_version = 1
        db.commit()


__all__ = [
    "ASYNC_CAPABILITIES",
    "E2E_FAKE_ADAPTER_TYPE",
    "E2E_FAKE_ASYNC_MODEL_PROFILE_ID",
    "E2E_FAKE_PROVIDER_ID",
    "E2E_FAKE_SYNC_MODEL_PROFILE_ID",
    "FakeCanvasProvider",
    "SYNC_CAPABILITIES",
    "build_e2e_provider_registry",
    "seed_e2e_model_profiles",
]
