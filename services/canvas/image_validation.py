"""Fail-closed image inspection for Product Canvas uploads."""
from __future__ import annotations

import hashlib
import io
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image, UnidentifiedImageError

from config import (
    CANVAS_MAX_IMAGE_EDGE,
    CANVAS_MAX_IMAGE_PIXELS,
    CANVAS_MAX_UPLOAD_BYTES,
)


ImageFormat = Literal["JPEG", "PNG", "WEBP"]

_EXTENSION_FORMATS: dict[str, ImageFormat] = {
    ".jpeg": "JPEG",
    ".jpg": "JPEG",
    ".png": "PNG",
    ".webp": "WEBP",
}
_MIME_FORMATS: dict[str, ImageFormat] = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}
_FORMAT_MIMES: dict[ImageFormat, str] = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}


class CanvasImageValidationError(ValueError):
    """Stable image rejection surfaced to later HTTP adapters."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class InspectedImage:
    format: ImageFormat
    mime_type: str
    width: int
    height: int
    sha256: str
    has_alpha: bool


def _reject(code: str, message: str) -> None:
    raise CanvasImageValidationError(code, message)


def _magic_format(data: bytes) -> ImageFormat | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "WEBP"
    return None


def _open_checks(image: Image.Image, expected_format: ImageFormat) -> tuple[int, int]:
    actual_format = image.format
    if actual_format not in _FORMAT_MIMES or actual_format != expected_format:
        _reject(
            "canvas_image_format_mismatch",
            "decoded image format does not match its signature",
        )
    width, height = image.size
    if width <= 0 or height <= 0:
        _reject("canvas_image_decode_failed", "decoded image dimensions are invalid")
    if max(width, height) > CANVAS_MAX_IMAGE_EDGE:
        _reject("canvas_image_edge_exceeded", "image edge exceeds the configured limit")
    if width * height > CANVAS_MAX_IMAGE_PIXELS:
        _reject("canvas_image_pixels_exceeded", "image pixels exceed the configured limit")
    if bool(getattr(image, "is_animated", False)) or int(
        getattr(image, "n_frames", 1)
    ) > 1:
        _reject("canvas_image_animated", "animated images are not supported")
    return width, height


def _decode_failure(exc: BaseException) -> CanvasImageValidationError:
    if isinstance(exc, (Image.DecompressionBombError, Image.DecompressionBombWarning)):
        return CanvasImageValidationError(
            "canvas_image_decompression_bomb",
            "image triggered Pillow decompression-bomb protection",
        )
    return CanvasImageValidationError(
        "canvas_image_decode_failed",
        "image could not be decoded completely",
    )


def _inspect_image(
    data: bytes,
    *,
    filename: str,
    declared_mime: str,
    enforce_upload_limit: bool,
    retain_loaded_pixels: bool = False,
) -> tuple[InspectedImage, Image.Image | None]:
    """Inspect immutable upload bytes in a fixed, fail-closed validation order."""
    if type(data) is not bytes:
        _reject("canvas_image_invalid_bytes", "image payload must be bytes")
    if not data:
        _reject("canvas_image_empty", "image payload is empty")
    if enforce_upload_limit and len(data) > CANVAS_MAX_UPLOAD_BYTES:
        _reject("canvas_image_too_large", "image payload exceeds the upload limit")

    if not isinstance(filename, str):
        _reject("canvas_image_extension_unsupported", "image filename is invalid")
    extension_format = _EXTENSION_FORMATS.get(Path(filename).suffix.lower())
    if extension_format is None:
        _reject(
            "canvas_image_extension_unsupported",
            "image filename extension is unsupported",
        )

    normalized_mime = declared_mime.strip().lower() if isinstance(declared_mime, str) else ""
    mime_format = _MIME_FORMATS.get(normalized_mime)
    if mime_format is None:
        _reject("canvas_image_mime_unsupported", "declared image MIME is unsupported")

    magic_format = _magic_format(data)
    if (
        magic_format is None
        or extension_format != mime_format
        or extension_format != magic_format
    ):
        _reject(
            "canvas_image_signature_mismatch",
            "image extension, MIME, and signature do not agree",
        )

    loaded_pixels: Image.Image | None = None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                width, height = _open_checks(image, magic_format)
                image.verify()
    except CanvasImageValidationError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise _decode_failure(exc) from exc
    except Exception as exc:
        raise _decode_failure(exc) from exc

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                reopened_width, reopened_height = _open_checks(image, magic_format)
                if (reopened_width, reopened_height) != (width, height):
                    _reject(
                        "canvas_image_format_mismatch",
                        "decoded image dimensions changed between validation passes",
                    )
                image.load()
                loaded_width, loaded_height = _open_checks(image, magic_format)
                if (loaded_width, loaded_height) != (width, height):
                    _reject(
                        "canvas_image_format_mismatch",
                        "decoded image dimensions changed during full load",
                    )
                has_alpha = "A" in image.getbands() or "transparency" in image.info
                if retain_loaded_pixels:
                    loaded_pixels = image.copy()
    except CanvasImageValidationError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise _decode_failure(exc) from exc
    except Exception as exc:
        raise _decode_failure(exc) from exc

    return (
        InspectedImage(
            format=magic_format,
            mime_type=_FORMAT_MIMES[magic_format],
            width=width,
            height=height,
            sha256=hashlib.sha256(data).hexdigest(),
            has_alpha=has_alpha,
        ),
        loaded_pixels,
    )


def inspect_image(
    data: bytes,
    *,
    filename: str,
    declared_mime: str,
) -> InspectedImage:
    """Inspect an untrusted upload, including the configured upload byte cap."""
    inspected, _loaded_pixels = _inspect_image(
        data,
        filename=filename,
        declared_mime=declared_mime,
        enforce_upload_limit=True,
    )
    return inspected


def _inspect_image_with_loaded_pixels(
    data: bytes,
    *,
    filename: str,
    declared_mime: str,
) -> tuple[InspectedImage, Image.Image]:
    """Validate an upload and retain its one fully decoded pixel buffer."""
    inspected, loaded_pixels = _inspect_image(
        data,
        filename=filename,
        declared_mime=declared_mime,
        enforce_upload_limit=True,
        retain_loaded_pixels=True,
    )
    if loaded_pixels is None:  # Defensive invariant; never expose a partial result.
        _reject("canvas_image_decode_failed", "image pixels could not be retained")
    return inspected, loaded_pixels


def inspect_trusted_image(
    data: bytes,
    *,
    filename: str,
    declared_mime: str,
) -> InspectedImage:
    """Inspect trusted processor output without applying the inbound upload cap."""
    inspected, _loaded_pixels = _inspect_image(
        data,
        filename=filename,
        declared_mime=declared_mime,
        enforce_upload_limit=False,
    )
    return inspected
