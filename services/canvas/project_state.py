"""Canonical persistence helpers and ownership reference scans for Canvas v1 state."""
from __future__ import annotations

import json
import math
from copy import deepcopy
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

from services.canvas.schemas import (
    CanvasLayoutState,
    CanvasSemanticState,
    empty_layout_state,
    empty_semantic_state,
)


CURRENT_PROJECT_SCHEMA_VERSION = 1
MAX_PROJECT_STATE_BYTES = 5 * 1024 * 1024


class ProjectStateError(ValueError):
    """Base class for persisted Canvas state errors."""


class ProjectStateVersionError(ProjectStateError):
    """Raised when a persisted schema version has no explicit upgrade path."""


class ProjectStateSizeError(ProjectStateError):
    """Raised when canonical state exceeds the project-state boundary."""


def _canonical_json(value: Any) -> str:
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    if len(serialized.encode("utf-8")) > MAX_PROJECT_STATE_BYTES:
        raise ProjectStateSizeError(
            f"project state exceeds {MAX_PROJECT_STATE_BYTES} UTF-8 bytes"
        )
    return serialized


def dump_project_state(state: BaseModel | Mapping[str, Any]) -> str:
    """Serialize a validated state model as compact deterministic camelCase JSON."""
    if isinstance(state, BaseModel):
        dumped = state.model_dump(by_alias=True, warnings=False)
        revalidated = type(state).model_validate(dumped)
        value = revalidated.model_dump(by_alias=True)
    elif isinstance(state, Mapping):
        value = dict(state)
    else:
        raise TypeError("project state must be a Pydantic model or mapping")
    return _canonical_json(value)


def _load_json_object(raw: str | bytes | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        return dict(raw)
    if not isinstance(raw, (str, bytes)):
        raise TypeError("persisted project state must be JSON text or an object")
    if len(raw.encode("utf-8") if isinstance(raw, str) else raw) > MAX_PROJECT_STATE_BYTES:
        raise ProjectStateSizeError(
            f"project state exceeds {MAX_PROJECT_STATE_BYTES} UTF-8 bytes"
        )
    try:
        value = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ProjectStateError("persisted project state is not valid JSON") from exc
    if not isinstance(value, dict):
        raise ProjectStateError("persisted project state must be a JSON object")
    return value


def _require_current_version(schema_version: int) -> None:
    if schema_version != CURRENT_PROJECT_SCHEMA_VERSION:
        raise ProjectStateVersionError(
            f"unsupported Canvas project schema version: {schema_version}"
        )


def load_semantic_state(
    raw: str | bytes | Mapping[str, Any],
    *,
    schema_version: int = CURRENT_PROJECT_SCHEMA_VERSION,
) -> CanvasSemanticState:
    _require_current_version(schema_version)
    return CanvasSemanticState.model_validate(_load_json_object(raw))


def load_layout_state(
    raw: str | bytes | Mapping[str, Any],
    *,
    schema_version: int = CURRENT_PROJECT_SCHEMA_VERSION,
) -> CanvasLayoutState:
    _require_current_version(schema_version)
    return CanvasLayoutState.model_validate(_load_json_object(raw))


def upgrade_project_state(
    *,
    semantic_state: str | bytes | Mapping[str, Any],
    layout_state: str | bytes | Mapping[str, Any],
    schema_version: int,
) -> tuple[dict[str, Any], dict[str, Any], int]:
    """Return canonical v1 objects; later versions must add an explicit tested branch."""
    _require_current_version(schema_version)
    semantic_wire = _load_json_object(semantic_state)
    layout_wire = _load_json_object(layout_state)
    _migrate_v1_composition_contract(semantic_wire, layout_wire)
    _migrate_v1_text_contract(layout_wire)
    semantic = load_semantic_state(semantic_wire, schema_version=schema_version)
    layout = load_layout_state(layout_wire, schema_version=schema_version)
    return (
        semantic.model_dump(by_alias=True),
        layout.model_dump(by_alias=True),
        CURRENT_PROJECT_SCHEMA_VERSION,
    )


def _migrate_v1_composition_contract(
    semantic_state: dict[str, Any],
    layout_state: dict[str, Any],
) -> None:
    """Upgrade early v1 composition/fallback fields without introducing a v2 wire."""
    from services.canvas.composition import composition_layout_hash
    from services.canvas.composition_schema import (
        DEFAULT_COMPOSITION_LAYOUT,
        CompositionLayout,
    )

    layers = {
        layer.get("id"): layer
        for layer in layout_state.get("productLayers", [])
        if isinstance(layer, dict) and isinstance(layer.get("id"), str)
    }
    transforms = layout_state.get("objectTransforms", {})
    for group in semantic_state.get("compositionGroups", []):
        if not isinstance(group, dict):
            continue
        legacy_layout = "layout" not in group
        if legacy_layout:
            migrated_layout = deepcopy(DEFAULT_COMPOSITION_LAYOUT)
            member_ids = group.get("productLayerIds")
            first_layer = (
                layers.get(member_ids[0])
                if isinstance(member_ids, list) and member_ids
                else None
            )
            transform = (
                transforms.get(first_layer.get("transformId"))
                if isinstance(first_layer, dict) and isinstance(transforms, dict)
                else None
            )
            if isinstance(transform, dict):
                x = transform.get("x")
                if isinstance(x, (int, float)) and 0 < x < 1:
                    width = min(0.8, 2 * x, 2 * (1 - x))
                    migrated_layout["slot"]["width"] = width
                    migrated_layout["slot"]["x"] = x - width * 0.5
                migrated_layout["baseline"] = transform.get(
                    "y", migrated_layout["baseline"]
                )
                migrated_layout["relativeProductFraction"] = transform.get(
                    "scale", migrated_layout["relativeProductFraction"]
                )
                migrated_layout["rotation"] = transform.get(
                    "rotation", migrated_layout["rotation"]
                )
            group["layout"] = migrated_layout
        parsed_layout = CompositionLayout.model_validate(group["layout"])
        current_hash = group.get("layoutHash")
        if (
            legacy_layout
            or not isinstance(current_hash, str)
            or not current_hash.startswith("sha256:")
        ):
            group["layoutHash"] = composition_layout_hash(parsed_layout)

    fallback_assets: set[str] = set()
    for node in semantic_state.get("nodes", []):
        if not isinstance(node, dict) or node.get("kind") != "product_source":
            continue
        parameters = node.get("parameters")
        if not isinstance(parameters, dict) or parameters.get("allowOpaqueFallback") is not True:
            continue
        asset_id = node.get("assetId")
        if isinstance(asset_id, str):
            fallback_assets.add(asset_id)
        parameters.pop("allowOpaqueFallback", None)

    for layer in layout_state.get("productLayers", []):
        if not isinstance(layer, dict):
            continue
        if layer.get("skuId") is None and layer.get("sourceAssetId") in fallback_assets:
            layer["allowOpaqueFallback"] = True
        else:
            layer.setdefault("allowOpaqueFallback", False)


def _migrate_v1_text_contract(layout_state: dict[str, Any]) -> None:
    """Pin early v1 text snapshots to the only authoritative font resource."""

    from services.canvas.font_resource import FONT_FAMILY, FONT_RESOURCE_VERSION

    snapshots = layout_state.get("textSnapshots", [])
    if not isinstance(snapshots, list):
        return
    for index, snapshot in enumerate(snapshots):
        if not isinstance(snapshot, dict):
            continue
        snapshot["fontAssetId"] = None
        snapshot["fontFamily"] = FONT_FAMILY
        snapshot["fontVersion"] = FONT_RESOURCE_VERSION
        snapshot.setdefault("color", "#0f172a")
        snapshot.setdefault("sortOrder", index)
        font_size = snapshot.get("fontSize")
        if (
            type(font_size) is float
            and math.isfinite(font_size)
            and font_size.is_integer()
        ):
            snapshot["fontSize"] = int(font_size)


def empty_project_state_json() -> tuple[str, str]:
    return (
        dump_project_state(empty_semantic_state()),
        dump_project_state(empty_layout_state()),
    )


def _collect_ids(value: Any, *, singular_suffix: str, plural_suffix: str) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            singular_name = singular_suffix[:1].lower() + singular_suffix[1:]
            plural_name = plural_suffix[:1].lower() + plural_suffix[1:]
            if (
                (key == singular_name or key.endswith(singular_suffix))
                and isinstance(item, str)
            ):
                found.add(item)
            elif (
                (key == plural_name or key.endswith(plural_suffix))
                and isinstance(item, list)
            ):
                found.update(candidate for candidate in item if isinstance(candidate, str))
            else:
                found.update(
                    _collect_ids(
                        item,
                        singular_suffix=singular_suffix,
                        plural_suffix=plural_suffix,
                    )
                )
    elif isinstance(value, list):
        for item in value:
            found.update(
                _collect_ids(
                    item,
                    singular_suffix=singular_suffix,
                    plural_suffix=plural_suffix,
                )
            )
    return found


def collect_sku_ids(
    semantic_state: CanvasSemanticState,
    layout_state: CanvasLayoutState,
) -> set[str]:
    payload = {
        "semantic": semantic_state.model_dump(by_alias=True),
        "layout": layout_state.model_dump(by_alias=True),
    }
    return _collect_ids(payload, singular_suffix="SkuId", plural_suffix="SkuIds")


def collect_asset_ids(
    semantic_state: CanvasSemanticState,
    layout_state: CanvasLayoutState,
) -> set[str]:
    payload = {
        "semantic": semantic_state.model_dump(by_alias=True),
        "layout": layout_state.model_dump(by_alias=True),
    }
    return _collect_ids(payload, singular_suffix="AssetId", plural_suffix="AssetIds")


def collect_asset_reference_sections(
    semantic_state: CanvasSemanticState,
    layout_state: CanvasLayoutState,
    *,
    asset_id: str,
) -> set[str]:
    """Return stable top-level state sections that currently reference an asset."""
    semantic = semantic_state.model_dump(by_alias=True)
    layout = layout_state.model_dump(by_alias=True)
    sections = {
        "nodes": semantic["nodes"],
        "edges": semantic["edges"],
        "outputBoards": semantic["outputBoards"],
        "completeSet": semantic["completeSet"],
        "compositionGroups": semantic["compositionGroups"],
        "productLayers": layout["productLayers"],
        "textSnapshots": layout["textSnapshots"],
    }
    references: set[str] = set()
    for section_name, value in sections.items():
        ids = _collect_ids(value, singular_suffix="AssetId", plural_suffix="AssetIds")
        if asset_id in ids:
            references.add(section_name)
    return references


def collect_sku_reference_sections(
    semantic_state: CanvasSemanticState,
    layout_state: CanvasLayoutState,
    *,
    sku_id: str,
) -> set[str]:
    semantic = semantic_state.model_dump(by_alias=True)
    layout = layout_state.model_dump(by_alias=True)
    sections = {
        "nodes": semantic["nodes"],
        "edges": semantic["edges"],
        "outputBoards": semantic["outputBoards"],
        "completeSet": semantic["completeSet"],
        "compositionGroups": semantic["compositionGroups"],
        "productLayers": layout["productLayers"],
    }
    references: set[str] = set()
    for section_name, value in sections.items():
        ids = _collect_ids(value, singular_suffix="SkuId", plural_suffix="SkuIds")
        if sku_id in ids:
            references.add(section_name)
    return references
