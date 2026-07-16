"""Deterministic composition hashing, projection, and lineage validation."""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from services.canvas.composition_schema import (
    CompositionLayout,
    CompositionSpec,
    PixelPlacement,
)
from services.canvas.schemas import CanvasLayoutState, CanvasSemanticState, ProductLayer


class CompositionValidationError(ValueError):
    """Raised when persisted composition state is internally inconsistent."""


def _round_six_half_away_from_zero(value: float) -> float:
    rounded = float(
        Decimal(str(value)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    )
    return 0.0 if rounded == 0 else rounded


def _canonical_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _canonical_value(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_canonical_value(item) for item in value]
    if isinstance(value, bool) or value is None or isinstance(value, (str, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CompositionValidationError("composition numbers must be finite")
        rounded = _round_six_half_away_from_zero(value)
        if rounded == 0:
            return 0
        if rounded.is_integer():
            return int(rounded)
        return rounded
    raise CompositionValidationError("composition layout contains a non-JSON value")


def _canonical_json_text(value: Any) -> str:
    if isinstance(value, dict):
        return "{" + ",".join(
            f"{json.dumps(key, ensure_ascii=False)}:{_canonical_json_text(item)}"
            for key, item in value.items()
        ) + "}"
    if isinstance(value, list):
        return "[" + ",".join(_canonical_json_text(item) for item in value) + "]"
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.6f}".rstrip("0").rstrip(".")
    raise CompositionValidationError("composition layout contains a non-JSON value")


def canonical_layout_json(layout: CompositionLayout) -> bytes:
    value = _canonical_value(layout.model_dump(by_alias=True))
    return _canonical_json_text(value).encode("utf-8")


def composition_layout_hash(layout: CompositionLayout) -> str:
    return f"sha256:{hashlib.sha256(canonical_layout_json(layout)).hexdigest()}"


def map_product_to_board(
    layout: CompositionLayout,
    *,
    source_size: tuple[int, int],
    output_size: tuple[int, int],
) -> PixelPlacement:
    source_width, source_height = source_size
    output_width, output_height = output_size
    if min(source_width, source_height, output_width, output_height) <= 0:
        raise CompositionValidationError("source and output sizes must be positive")

    slot_left = layout.slot.x * output_width
    slot_top = layout.slot.y * output_height
    slot_right = (layout.slot.x + layout.slot.width) * output_width
    slot_bottom = (layout.slot.y + layout.slot.height) * output_height
    safe_left = layout.safe_area.left * output_width
    safe_top = layout.safe_area.top * output_height
    safe_right = (1 - layout.safe_area.right) * output_width
    safe_bottom = (1 - layout.safe_area.bottom) * output_height
    left = max(slot_left, safe_left)
    top = max(slot_top, safe_top)
    right = min(slot_right, safe_right)
    bottom = min(slot_bottom, safe_bottom)
    if left >= right or top >= bottom:
        raise CompositionValidationError("composition slot does not intersect the safe area")

    box_width = (right - left) * layout.relative_product_fraction
    box_height = (bottom - top) * layout.relative_product_fraction
    normalized_rotation = _round_six_half_away_from_zero(layout.rotation)
    angle = math.radians(normalized_rotation)
    cosine = abs(math.cos(angle))
    sine = abs(math.sin(angle))
    rotated_source_width = source_width * cosine + source_height * sine
    rotated_source_height = source_width * sine + source_height * cosine
    scale = min(box_width / rotated_source_width, box_height / rotated_source_height)
    width = max(1, math.floor(source_width * scale + 1e-9))
    height = max(1, math.floor(source_height * scale + 1e-9))
    rotated_width = width * cosine + height * sine
    rotated_height = width * sine + height * cosine
    target_x = slot_left + (slot_right - slot_left) * layout.anchor.x
    target_y = layout.baseline * output_height
    target_center_x = target_x + (0.5 - layout.anchor.x) * width
    target_center_y = target_y + (0.5 - layout.anchor.y) * height
    minimum_x = math.ceil(left + rotated_width / 2 - width / 2)
    maximum_x = math.floor(right - rotated_width / 2 - width / 2)
    minimum_y = math.ceil(top + rotated_height / 2 - height / 2)
    maximum_y = math.floor(bottom - rotated_height / 2 - height / 2)
    if minimum_x > maximum_x or minimum_y > maximum_y:
        raise CompositionValidationError("rotated product cannot fit inside the composition slot")
    desired_x = math.floor(target_center_x - width / 2 + 0.5)
    desired_y = math.floor(target_center_y - height / 2 + 0.5)
    x = min(max(desired_x, minimum_x), maximum_x)
    y = min(max(desired_y, minimum_y), maximum_y)
    return PixelPlacement.model_validate(
        {
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "rotation": normalized_rotation,
        }
    )


def _expected_transform(layout: CompositionLayout) -> tuple[float, float, float, float]:
    return (
        layout.slot.x + layout.slot.width * layout.anchor.x,
        layout.baseline,
        layout.relative_product_fraction,
        _round_six_half_away_from_zero(layout.rotation),
    )


def validate_composition_state(
    semantic_state: CanvasSemanticState,
    layout_state: CanvasLayoutState,
) -> None:
    groups = {group.id: group for group in semantic_state.composition_groups}
    layers = {layer.id: layer for layer in layout_state.product_layers}
    grouped_layers: set[str] = set()
    for group in groups.values():
        if group.layout_hash != composition_layout_hash(group.layout):
            raise CompositionValidationError(f"composition group {group.id} has a stale layout hash")
        member_ids = set(group.product_layer_ids)
        actual_ids = {
            layer.id for layer in layers.values() if layer.composition_group_id == group.id
        }
        if member_ids != actual_ids or grouped_layers.intersection(member_ids):
            raise CompositionValidationError(f"composition group {group.id} membership is inconsistent")
        grouped_layers.update(member_ids)
        expected_skus = {
            layers[layer_id].sku_id for layer_id in member_ids if layers[layer_id].sku_id is not None
        }
        if set(group.sku_ids) != expected_skus:
            raise CompositionValidationError(f"composition group {group.id} SKU membership is inconsistent")
        expected = _expected_transform(group.layout)
        for layer_id in group.product_layer_ids:
            layer = layers.get(layer_id)
            if layer is None or not layer.locked:
                raise CompositionValidationError("composition product layers must exist and remain locked")
            transform = layout_state.object_transforms.get(layer.transform_id)
            if transform is None:
                raise CompositionValidationError("composition product layer is missing its projection")
            actual = (transform.x, transform.y, transform.scale, transform.rotation)
            if any(abs(left - right) > 1e-6 for left, right in zip(actual, expected, strict=True)):
                raise CompositionValidationError("composition product projection does not match its group")
            if layer.allow_opaque_fallback and layer.render_asset_id != layer.source_asset_id:
                raise CompositionValidationError("opaque fallback must render the immutable working asset")
    if any(
        layer.composition_group_id is not None and layer.id not in grouped_layers
        for layer in layers.values()
    ):
        raise CompositionValidationError("product layer references an unknown composition group")


def _asset_value(asset: Mapping[str, Any] | Any, camel: str, snake: str) -> Any:
    if isinstance(asset, Mapping):
        return asset.get(camel, asset.get(snake))
    return getattr(asset, snake)


def _validate_asset_lineage(
    *,
    project_id: str,
    layer: ProductLayer,
    assets: Mapping[str, Mapping[str, Any] | Any],
) -> tuple[int, int]:
    source = assets.get(layer.source_asset_id)
    render = assets.get(layer.render_asset_id)
    if source is None or render is None:
        raise CompositionValidationError("composition product references a missing asset")
    if _asset_value(source, "projectId", "project_id") != project_id:
        raise CompositionValidationError("composition source asset belongs to another project")
    if _asset_value(render, "projectId", "project_id") != project_id:
        raise CompositionValidationError("composition render asset belongs to another project")
    if _asset_value(source, "assetType", "asset_type") != "working":
        raise CompositionValidationError("composition sourceAssetId must reference a working asset")
    source_width = int(_asset_value(source, "width", "width"))
    source_height = int(_asset_value(source, "height", "height"))
    if layer.render_asset_id == layer.source_asset_id:
        transparency = _asset_value(source, "transparencyStatus", "transparency_status")
        if transparency != "transparent" and not layer.allow_opaque_fallback:
            raise CompositionValidationError(
                "opaque working assets require an explicit fallback or a derived cutout"
            )
    else:
        if (
            _asset_value(render, "assetType", "asset_type") != "cutout"
            or _asset_value(render, "sourceAssetId", "source_asset_id") != layer.source_asset_id
        ):
            raise CompositionValidationError("composition render asset is not derived from its working source")
        if (
            int(_asset_value(render, "width", "width")) != source_width
            or int(_asset_value(render, "height", "height")) != source_height
        ):
            raise CompositionValidationError("composition cutout dimensions must match its working source")
    return (source_width, source_height)


def build_composition_specs(
    *,
    project_id: str,
    semantic_state: CanvasSemanticState,
    layout_state: CanvasLayoutState,
    sku_reference_asset_ids: Mapping[str, str | None],
    assets: Mapping[str, Mapping[str, Any] | Any],
    output_ratios: Mapping[str, Mapping[str, int]],
) -> list[CompositionSpec]:
    validate_composition_state(semantic_state, layout_state)
    layers = {layer.id: layer for layer in layout_state.product_layers}
    main_layers = [layer for layer in layers.values() if layer.sku_id is None and layer.locked]
    if semantic_state.composition_groups and len(main_layers) != 1:
        raise CompositionValidationError("composition requires exactly one locked main product")
    main = main_layers[0] if main_layers else None
    specs: list[CompositionSpec] = []
    for group in semantic_state.composition_groups:
        for layer_id in group.product_layer_ids:
            layer = layers[layer_id]
            if layer.sku_id is not None:
                reference = sku_reference_asset_ids.get(layer.sku_id)
                if reference is None:
                    if main is None or (
                        layer.source_asset_id != main.source_asset_id
                        or layer.render_asset_id != main.render_asset_id
                    ):
                        raise CompositionValidationError(
                            "SKU without a reference must reuse the locked main product"
                        )
                elif layer.source_asset_id != reference:
                    raise CompositionValidationError("SKU product does not match its reference asset")
            source_width, source_height = _validate_asset_lineage(
                project_id=project_id,
                layer=layer,
                assets=assets,
            )
            ratio = output_ratios.get(layer.sku_id or "", {"width": 1, "height": 1})
            specs.append(
                CompositionSpec.model_validate(
                    {
                        "schemaVersion": 1,
                        "projectId": project_id,
                        "compositionGroupId": group.id,
                        "skuId": layer.sku_id,
                        "productLayerId": layer.id,
                        "sourceAssetId": layer.source_asset_id,
                        "renderAssetId": layer.render_asset_id,
                        "allowOpaqueFallback": layer.allow_opaque_fallback,
                        "layout": group.layout.model_dump(by_alias=True),
                        "layoutHash": group.layout_hash,
                        "sourceSize": {"width": source_width, "height": source_height},
                        "outputRatio": dict(ratio),
                    }
                )
            )
    return specs
