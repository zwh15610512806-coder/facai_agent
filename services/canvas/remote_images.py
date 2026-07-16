"""Remote Provider image verification and immediate controlled persistence."""
from __future__ import annotations

import hashlib
import io
import warnings
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin

from PIL import Image, UnidentifiedImageError

from services.canvas.assets import persist_derived_image
from services.canvas.provider_network import (
    PinnedEndpoint,
    PinnedHttpCoreTransport,
    ProviderNetworkPolicy,
    ProviderNetworkError,
    resolve_pinned_target,
    resolve_public_https_endpoint,
    validate_provider_base_url,
)
from services.canvas.provider_schemas import (
    ProviderError,
    ProviderGenerationRequest,
    ProviderRuntime,
)
from services.canvas.providers.base import ImageProviderAdapter


_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_MIME_BY_FORMAT = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "WEBP": "image/webp",
}
_UNSAFE_METADATA_MARKERS = ("credential", "secret", "token", "url")


class RemoteImageValidationError(RuntimeError):
    """Provider image failure with no URL or upstream bytes in its message."""


@dataclass(frozen=True)
class VerifiedRemoteImage:
    data: bytes = field(repr=False)
    mime_type: str
    width: int
    height: int
    sha256: str
    source_format: str


def _magic_format(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if data.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "WEBP"
    return None


def verify_remote_image(
    data: bytes,
    *,
    declared_mime: str,
    max_bytes: int,
) -> VerifiedRemoteImage:
    if not isinstance(data, bytes) or not data or len(data) > max_bytes:
        raise RemoteImageValidationError("Provider image exceeded the size limit")
    mime_type = declared_mime.split(";", 1)[0].strip().lower()
    magic_format = _magic_format(data)
    if magic_format is None or _MIME_BY_FORMAT.get(magic_format) != mime_type:
        raise RemoteImageValidationError("Provider image type is invalid")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as probe:
                if probe.format != magic_format:
                    raise RemoteImageValidationError("Provider image format is inconsistent")
                if bool(getattr(probe, "is_animated", False)) or int(
                    getattr(probe, "n_frames", 1)
                ) != 1:
                    raise RemoteImageValidationError("Animated Provider images are not allowed")
                width, height = probe.size
                if width <= 0 or height <= 0 or width * height * 4 > max_bytes:
                    raise RemoteImageValidationError(
                        "Decoded Provider image exceeded the size limit"
                    )
                probe.verify()
            with Image.open(io.BytesIO(data)) as decoded:
                if decoded.format != magic_format:
                    raise RemoteImageValidationError("Provider image format is inconsistent")
                if bool(getattr(decoded, "is_animated", False)) or int(
                    getattr(decoded, "n_frames", 1)
                ) != 1:
                    raise RemoteImageValidationError("Animated Provider images are not allowed")
                decoded.load()
                canonical = decoded.convert("RGBA")
                try:
                    # Never persist upstream PNG containers verbatim. A valid
                    # image may carry tEXt/EXIF/ICC chunks containing signed
                    # result URLs or other untrusted metadata. A fresh RGBA
                    # image and fresh encoder preserve pixels while dropping
                    # every ancillary input chunk for all supported formats.
                    canonical.info.clear()
                    normalized = io.BytesIO()
                    canonical.save(
                        normalized,
                        format="PNG",
                        optimize=False,
                        compress_level=6,
                    )
                    png_data = normalized.getvalue()
                finally:
                    canonical.close()
    except RemoteImageValidationError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise RemoteImageValidationError("Provider image dimensions are unsafe") from None
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise RemoteImageValidationError("Provider image could not be decoded") from None

    if len(png_data) > max_bytes:
        raise RemoteImageValidationError("Normalized Provider image exceeded the size limit")
    return VerifiedRemoteImage(
        data=png_data,
        mime_type="image/png",
        width=width,
        height=height,
        sha256=hashlib.sha256(png_data).hexdigest(),
        source_format=magic_format.lower(),
    )


async def download_remote_image(
    remote_url: str,
    *,
    transport: Any | None = None,
    max_bytes: int | None = None,
    endpoint_validator: Callable[[str], PinnedEndpoint] = resolve_public_https_endpoint,
    policy: ProviderNetworkPolicy | None = None,
) -> VerifiedRemoteImage:
    if max_bytes is None:
        from config import CANVAS_REMOTE_IMAGE_MAX_BYTES

        max_bytes = CANVAS_REMOTE_IMAGE_MAX_BYTES
    requester = transport or PinnedHttpCoreTransport()
    current_url = remote_url
    redirect_count = 0
    while True:
        try:
            if policy is None:
                endpoint = endpoint_validator(current_url)
            else:
                origin = validate_provider_base_url(current_url, policy=policy)
                target = resolve_pinned_target(origin, policy=policy)
                endpoint = PinnedEndpoint(
                    url=current_url,
                    hostname=target.hostname,
                    port=target.port,
                    pinned_ip=target.pinned_ip,
                    private_http=target.private_http,
                )
            response = await requester.request(
                method="GET",
                url=current_url,
                headers={"Accept": "image/png,image/jpeg,image/webp"},
                max_bytes=max_bytes,
                pinned_endpoint=endpoint,
            )
        except RemoteImageValidationError:
            raise
        except ProviderNetworkError:
            raise RemoteImageValidationError("Provider image download failed") from None
        except Exception:
            raise RemoteImageValidationError("Provider image download failed") from None

        if response.status_code in _REDIRECT_STATUSES:
            if redirect_count >= 2:
                raise RemoteImageValidationError("Provider image redirected too many times")
            location = response.header("location")
            if not location:
                raise RemoteImageValidationError("Provider image redirect was invalid")
            current_url = urljoin(current_url, location)
            redirect_count += 1
            continue
        if response.status_code < 200 or response.status_code >= 300:
            raise RemoteImageValidationError("Provider image download was unsuccessful")
        content_type = response.header("content-type") or ""
        return verify_remote_image(
            response.body,
            declared_mime=content_type,
            max_bytes=max_bytes,
        )


def _metadata_is_safe(value: object, *, key: str = "") -> bool:
    normalized_key = key.lower()
    if any(marker in normalized_key for marker in _UNSAFE_METADATA_MARKERS):
        return False
    if isinstance(value, str):
        lowered = value.lower()
        return "http://" not in lowered and "https://" not in lowered
    if isinstance(value, Mapping):
        return all(_metadata_is_safe(item, key=str(item_key)) for item_key, item in value.items())
    if isinstance(value, (list, tuple)):
        return all(_metadata_is_safe(item, key=key) for item in value)
    return value is None or isinstance(value, (bool, int, float))


async def generate_and_persist_background(
    *,
    adapter: ImageProviderAdapter,
    request: ProviderGenerationRequest,
    runtime: ProviderRuntime,
    db_factory: Callable[[], Any],
    project_id: str,
    source_asset_id: str | None,
    metadata: Mapping[str, object],
    endpoint_validator: Callable[[str], PinnedEndpoint] = resolve_public_https_endpoint,
    policy: ProviderNetworkPolicy | None = None,
) -> str:
    """Finish every network await, then open one short persistence transaction."""

    submission = await adapter.submit(request, runtime)
    if submission.status != "completed" or submission.image is None:
        raise ProviderError(
            "provider_submission_incomplete",
            "The synchronous Provider did not return a completed image",
        )
    verified = await download_remote_image(
        submission.image.remote_url,
        transport=runtime.transport,
        endpoint_validator=endpoint_validator,
        policy=policy,
    )
    if not _metadata_is_safe(metadata):
        raise RemoteImageValidationError("Provider persistence metadata is unsafe")
    safe_metadata = dict(metadata)
    safe_metadata.update(
        {
            "providerAdapter": adapter.adapter_type,
            "providerModelId": getattr(adapter, "MODEL_ID", ""),
            "providerRequestId": submission.request_id,
            "sourceFormat": verified.source_format,
            "verifiedSha256": verified.sha256,
        }
    )
    with db_factory() as db:
        try:
            asset = persist_derived_image(
                db,
                project_id=project_id,
                asset_type="generated_background",
                data=verified.data,
                mime_type="image/png",
                source_asset_id=source_asset_id,
                metadata=safe_metadata,
                processor_version=f"{adapter.adapter_type}-provider-v1",
            )
            asset_id = str(asset.id)
            db.commit()
        except Exception:
            rollback = getattr(db, "rollback", None)
            if callable(rollback):
                rollback()
            raise
    return asset_id


__all__ = [
    "RemoteImageValidationError",
    "VerifiedRemoteImage",
    "download_remote_image",
    "generate_and_persist_background",
    "verify_remote_image",
]
