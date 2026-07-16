"""Canonical generation fingerprints and worst-case storage reservations."""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence
from dataclasses import asdict

from services.canvas.generation.schemas import GenerationItemSnapshot


def _positive_integer(value: object, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def encoded_rgba_png_upper_bound(width: int, height: int) -> int:
    """Return a conservative no-compression PNG bound for one RGBA image."""

    validated_width = _positive_integer(width, name="width")
    validated_height = _positive_integer(height, name="height")
    raw_scanlines = validated_height * (1 + validated_width * 4)
    # RFC 1950/1951 stored blocks need at most five bytes per 16,383 bytes,
    # plus the zlib header/adler checksum. PNG adds signature, IHDR, IDAT and IEND.
    zlib_bound = raw_scanlines + 5 * math.ceil(raw_scanlines / 16_383) + 6
    return zlib_bound + 57


def proxy_dimensions(width: int, height: int, *, longest_edge: int = 2_048) -> tuple[int, int]:
    validated_width = _positive_integer(width, name="width")
    validated_height = _positive_integer(height, name="height")
    validated_edge = _positive_integer(longest_edge, name="longest_edge")
    largest = max(validated_width, validated_height)
    if largest <= validated_edge:
        return validated_width, validated_height
    scale = validated_edge / largest
    return (
        max(1, math.ceil(validated_width * scale)),
        max(1, math.ceil(validated_height * scale)),
    )


def _canonical_item(item: GenerationItemSnapshot) -> dict[str, object]:
    document = asdict(item)
    document["inputs"] = sorted(
        document["inputs"],
        key=lambda value: (
            value["input_role"],
            value["ordinal"],
            value["asset_id"],
        ),
    )
    document["text_snapshots"] = sorted(
        document["text_snapshots"],
        key=lambda value: (
            value.get("sortOrder", value.get("sort_order", 0)),
            str(value.get("id", "")),
        ),
    )
    return document


def canonical_generation_document(
    *,
    project_revision: int,
    items: Sequence[GenerationItemSnapshot],
) -> dict[str, object]:
    revision = _positive_integer(project_revision, name="project_revision")
    canonical_items = [_canonical_item(item) for item in items]
    canonical_items.sort(key=lambda value: (value["ordinal"], value["board_id"]))
    return {
        "fingerprintVersion": 1,
        "projectRevision": revision,
        "items": canonical_items,
    }


def compute_generation_fingerprint(
    *,
    project_revision: int,
    items: Sequence[GenerationItemSnapshot],
) -> str:
    document = canonical_generation_document(
        project_revision=project_revision,
        items=items,
    )
    encoded = json.dumps(
        document,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def estimate_generation_storage_reservation(
    items: Sequence[GenerationItemSnapshot],
    *,
    remote_image_max_bytes: int,
) -> int:
    """Reserve the verified/full background peak, composed PNG and two proxies."""

    remote_limit = _positive_integer(
        remote_image_max_bytes,
        name="remote_image_max_bytes",
    )
    total = 0
    for item in items:
        proxy_width, proxy_height = proxy_dimensions(item.width, item.height)
        total += (
            2 * remote_limit
            + encoded_rgba_png_upper_bound(item.width, item.height)
            + 2 * encoded_rgba_png_upper_bound(proxy_width, proxy_height)
        )
    return total


__all__ = [
    "canonical_generation_document",
    "compute_generation_fingerprint",
    "encoded_rgba_png_upper_bound",
    "estimate_generation_storage_reservation",
    "proxy_dimensions",
]
