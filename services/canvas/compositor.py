"""Deterministic pure Product Canvas image composition primitives."""
from __future__ import annotations

import io
import math
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Mapping, Sequence
from typing import Any

from PIL import Image
from config import CANVAS_MAX_IMAGE_PIXELS

from services.canvas.composition_schema import PixelPlacement
from services.canvas.font_resource import BUILT_FONT_PATH, FONT_RESOURCE_VERSION
from services.canvas.schemas import TextSnapshot
from services.canvas.text_layout import RequestFontProvider, render_text_lines


COMPOSE_PROCESSOR_VERSION = "pillow-12.3.0-compose-v1"


class CanvasCompositionError(ValueError):
    """Raised when immutable composition input cannot be rendered safely."""


@dataclass(frozen=True)
class LockedProductLayer:
    image: Image.Image
    placement: PixelPlacement


def _resize_background(background: Image.Image, output_size: tuple[int, int]) -> Image.Image:
    canonical = background.convert("RGBA")
    if canonical.size == output_size:
        return canonical
    resized = canonical.resize(output_size, Image.Resampling.LANCZOS)
    canonical.close()
    return resized


def _render_product(product: LockedProductLayer) -> tuple[Image.Image, tuple[int, int]]:
    placement = product.placement
    source = product.image.convert("RGBA")
    if source.size != (placement.width, placement.height):
        resized = source.resize(
            (placement.width, placement.height),
            Image.Resampling.LANCZOS,
        )
        source.close()
        source = resized
    if placement.rotation == 0:
        return source, (placement.x, placement.y)
    rotated = source.rotate(
        -placement.rotation,
        resample=Image.Resampling.BICUBIC,
        expand=True,
        fillcolor=(0, 0, 0, 0),
    )
    source.close()
    center_x = placement.x + placement.width / 2
    center_y = placement.y + placement.height / 2
    left = math.floor(center_x - rotated.width / 2 + 0.5)
    top = math.floor(center_y - rotated.height / 2 + 0.5)
    return rotated, (left, top)


def compose_image(
    *,
    background: Image.Image,
    products: Sequence[LockedProductLayer],
    text_layers: Sequence[TextSnapshot],
    output_size: tuple[int, int],
    font_path: Path = BUILT_FONT_PATH,
    expected_font_version: str = FONT_RESOURCE_VERSION,
) -> Image.Image:
    """Compose fixed z-bands: background, below text, products, above text."""

    width, height = output_size
    if type(width) is not int or type(height) is not int or width <= 0 or height <= 0:
        raise CanvasCompositionError("composition output size must contain positive integers")
    if width * height > CANVAS_MAX_IMAGE_PIXELS:
        raise CanvasCompositionError("composition output exceeds the configured pixel limit")
    font_provider = (
        RequestFontProvider(font_path, expected_font_version)
        if text_layers
        else None
    )
    result = _resize_background(background, output_size)
    ordered_text = sorted(text_layers, key=lambda layer: (layer.sort_order, layer.id))
    for layer in ordered_text:
        if layer.z_band == "below-product":
            render_text_lines(
                result,
                layer=layer,
                font_path=font_path,
                expected_font_version=expected_font_version,
                font_provider=font_provider,
            )
    for product in products:
        rendered, position = _render_product(product)
        try:
            result.alpha_composite(rendered, dest=position)
        finally:
            rendered.close()
    for layer in ordered_text:
        if layer.z_band == "above-product":
            render_text_lines(
                result,
                layer=layer,
                font_path=font_path,
                expected_font_version=expected_font_version,
                font_provider=font_provider,
            )
    result.info.clear()
    return result


def encode_composed_png(image: Image.Image) -> bytes:
    canonical = image.convert("RGBA")
    try:
        canonical.info.clear()
        output = io.BytesIO()
        canonical.save(output, format="PNG", optimize=False, compress_level=9)
        return output.getvalue()
    finally:
        canonical.close()


def compose_to_asset(
    db: Any,
    *,
    project_id: str,
    spec: Mapping[str, Any],
    operation_id: str,
    data: bytes,
    background_asset_id: str,
    generation_id: str | None = None,
) -> Any:
    """Persist already-rendered bytes; only the compose worker calls this boundary."""

    from services.canvas import assets

    return assets.persist_derived_image(
        db,
        project_id=project_id,
        asset_type="composed",
        data=data,
        mime_type="image/png",
        source_asset_id=background_asset_id,
        metadata={
            "operationId": operation_id,
            "processorVersion": COMPOSE_PROCESSOR_VERSION,
            "snapshot": dict(spec),
        },
        processor_version=COMPOSE_PROCESSOR_VERSION,
        generation_id=generation_id,
    )


__all__ = [
    "COMPOSE_PROCESSOR_VERSION",
    "CanvasCompositionError",
    "LockedProductLayer",
    "compose_image",
    "compose_to_asset",
    "encode_composed_png",
]
