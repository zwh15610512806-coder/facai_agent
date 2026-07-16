"""One pinned OFL font used identically by browser previews and Pillow."""
from __future__ import annotations

import hashlib
from pathlib import Path


FONT_FAMILY = "Noto Sans CJK SC"
FONT_FILENAME = "NotoSansCJKsc-Regular.otf"
FONT_SHA256 = "2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b"
FONT_RESOURCE_VERSION = f"sha256:{FONT_SHA256}"
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SOURCE_FONT_PATH = _REPOSITORY_ROOT / "frontend" / "canvas" / "public" / "fonts" / FONT_FILENAME
BUILT_FONT_PATH = _REPOSITORY_ROOT / "static" / "canvas" / "fonts" / FONT_FILENAME


class CanvasFontResourceError(ValueError):
    """Raised before loading when the exact vendored font cannot be verified."""


def verify_font_resource(
    path: Path = BUILT_FONT_PATH,
    expected_font_version: str = FONT_RESOURCE_VERSION,
) -> Path:
    if expected_font_version != FONT_RESOURCE_VERSION:
        raise CanvasFontResourceError("unsupported Canvas font resource version")
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise CanvasFontResourceError("Canvas font resource is unavailable") from exc
    if digest != FONT_SHA256:
        raise CanvasFontResourceError("Canvas font resource digest does not match")
    return path


__all__ = [
    "BUILT_FONT_PATH",
    "CanvasFontResourceError",
    "FONT_FAMILY",
    "FONT_FILENAME",
    "FONT_RESOURCE_VERSION",
    "FONT_SHA256",
    "SOURCE_FONT_PATH",
    "verify_font_resource",
]
