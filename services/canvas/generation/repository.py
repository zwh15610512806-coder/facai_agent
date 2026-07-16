"""Strict, idempotent persistence for Product Canvas generations."""
from __future__ import annotations

import base64
import hashlib
import json
import re
import time
from dataclasses import asdict
from datetime import datetime
from math import gcd
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from canvas_models import (
    CanvasAsset,
    CanvasGeneration,
    CanvasGenerationAttempt,
    CanvasGenerationItem,
    CanvasGenerationItemInput,
    CanvasProject,
    CanvasProjectSku,
    ImageModelProfile,
    ImageProviderConnection,
)
from config import CANVAS_REMOTE_IMAGE_MAX_BYTES
from services.canvas import storage
from services.canvas.composition import composition_layout_hash
from services.canvas.graph import OUTPUT_NODE_KIND_BY_TYPE
from services.canvas.generation.fingerprints import (
    compute_generation_fingerprint,
    estimate_generation_storage_reservation,
)
from services.canvas.generation.schemas import (
    CanvasGenerationCreate,
    GenerationInputSnapshot,
    GenerationItemSnapshot,
    GenerationAttemptDetail,
    GenerationDetail,
    GenerationItemDetail,
    ResultVersion,
    ResultVersionPage,
)
from services.canvas.projects import (
    CanvasProjectStatusConflict,
    CanvasRevisionConflict,
    get_project_snapshot,
)
from services.canvas.provider_schemas import ModelCapabilities


_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$")
_ACTIVE_GENERATION_STATUSES = {
    "queued",
    "running",
    "cancel_requested",
    "unknown",
    "interrupted",
}
_UNSAFE_CONFIGURATION_KEY_MARKERS = (
    "authorization",
    "credential",
    "secret",
    "token",
    "api_key",
    "apikey",
    "password",
)
_SQLITE_BEGIN_RETRY_DELAYS_SECONDS = (0.05, 0.10, 0.20)


class CanvasGenerationError(RuntimeError):
    """Base class for stable generation-domain failures."""


class CanvasGenerationValidationError(CanvasGenerationError, ValueError):
    pass


class CanvasGenerationNotFound(CanvasGenerationError, LookupError):
    pass


class CanvasGenerationIdempotencyConflict(CanvasGenerationError):
    pass


class CanvasGenerationActiveConflict(CanvasGenerationError):
    pass


class CanvasGenerationTransactionError(CanvasGenerationError):
    pass


class CanvasGenerationReservationError(CanvasGenerationError):
    pass


def _is_transient_sqlite_lock(db: Session, exc: OperationalError) -> bool:
    bind = db.get_bind()
    if bind.dialect.name != "sqlite":
        return False
    message = str(exc).lower()
    return "database is locked" in message or "database is busy" in message


def _begin_generation_transaction(db: Session) -> None:
    """Acquire the SQLite writer lease without turning a transient race into HTTP 500.

    Generation creation is fully durable before this call returns, so retrying
    only the first ``BEGIN IMMEDIATE`` cannot duplicate a paid request.  Other
    database errors remain visible to the caller; an exhausted lock window is
    a stable, retryable Canvas transaction error.
    """

    for delay in (*_SQLITE_BEGIN_RETRY_DELAYS_SECONDS, None):
        try:
            db.execute(text("BEGIN IMMEDIATE"))
            return
        except OperationalError as exc:
            db.rollback()
            if not _is_transient_sqlite_lock(db, exc):
                raise
            if delay is None:
                raise CanvasGenerationTransactionError(
                    "Canvas generation writer is temporarily busy"
                ) from exc
            time.sleep(delay)


def validate_idempotency_key(value: str) -> str:
    if not isinstance(value, str) or _IDEMPOTENCY_KEY.fullmatch(value) is None:
        raise CanvasGenerationValidationError(
            "Idempotency-Key must contain 16-128 safe ASCII characters"
        )
    return value


def _json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _parse_object(value: str, *, field: str) -> dict[str, Any]:
    try:
        document = json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise CanvasGenerationValidationError(f"{field} is not valid JSON") from exc
    if not isinstance(document, dict):
        raise CanvasGenerationValidationError(f"{field} must be an object")
    return document


def _client_request_hash(request: CanvasGenerationCreate) -> str:
    payload = request.model_dump(by_alias=True, mode="json")
    return hashlib.sha256(_json(payload).encode("utf-8")).hexdigest()


def _request_snapshot(
    request: CanvasGenerationCreate,
    *,
    client_request_hash: str,
    fingerprint: str,
) -> str:
    return _json(
        {
            "version": 1,
            "clientRequestHash": client_request_hash,
            "fingerprint": fingerprint,
            "request": request.model_dump(by_alias=True, mode="json"),
        }
    )


def _existing_client_hash(generation: CanvasGeneration) -> str | None:
    try:
        value = json.loads(generation.request_snapshot_json)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    result = value.get("clientRequestHash")
    return result if isinstance(result, str) else None


def _strip_url_secrets(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"}:
        return value
    if parsed.username is not None or parsed.password is not None:
        raise CanvasGenerationValidationError("Provider URL must not contain userinfo")
    hostname = parsed.hostname or ""
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    netloc = f"{hostname}:{parsed.port}" if parsed.port is not None else hostname
    return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))


def _provider_snapshot(provider: ImageProviderConnection) -> dict[str, Any]:
    # Credentials and environment references are deliberately absent.
    return {
        "id": provider.id,
        "adapterType": provider.adapter_type,
        "name": provider.name,
        "baseUrl": _strip_url_secrets(provider.base_url),
        "authType": provider.auth_type,
        "configVersion": provider.config_version,
    }


def _safe_configuration(value: object, *, path: str = "configuration") -> object:
    if value is None or isinstance(value, (bool, int, float, str)):
        if isinstance(value, str):
            return _strip_url_secrets(value)
        return value
    if isinstance(value, list):
        return [
            _safe_configuration(item, path=f"{path}[]")
            for item in value
        ]
    if isinstance(value, dict):
        cleaned: dict[str, object] = {}
        for key, item in value.items():
            normalized = str(key).lower().replace("-", "_")
            if any(marker in normalized for marker in _UNSAFE_CONFIGURATION_KEY_MARKERS):
                raise CanvasGenerationValidationError(
                    f"{path} contains a credential-like field"
                )
            cleaned[str(key)] = _safe_configuration(
                item,
                path=f"{path}.{key}",
            )
        return cleaned
    raise CanvasGenerationValidationError(f"{path} contains an unsupported value")


def _model_snapshot(model: ImageModelProfile) -> dict[str, Any]:
    capabilities_document = _parse_object(
        model.capabilities_json,
        field="model capabilities",
    )
    capabilities = ModelCapabilities(**capabilities_document)
    configuration = _safe_configuration(
        _parse_object(model.config_json, field="model configuration")
    )
    return {
        "id": model.id,
        "providerId": model.provider_id,
        "modelId": model.model_id,
        "displayName": model.display_name,
        "configVersion": model.config_version,
        "capabilities": asdict(capabilities),
        "configuration": configuration,
    }


def _require_unique(values: Iterable[str], *, label: str) -> None:
    values_list = list(values)
    if len(values_list) != len(set(values_list)):
        raise CanvasGenerationValidationError(f"project contains duplicate {label} ids")


def _one_by_id(values: Iterable[Any], identifier: str, *, label: str) -> Any:
    matches = [value for value in values if value.id == identifier]
    if len(matches) != 1:
        raise CanvasGenerationValidationError(f"{label} is missing or ambiguous")
    return matches[0]


def _active_asset(db: Session, *, project_id: str, asset_id: str) -> CanvasAsset:
    asset = db.scalar(
        select(CanvasAsset).where(
            CanvasAsset.id == asset_id,
            CanvasAsset.project_id == project_id,
            CanvasAsset.deleted_at.is_(None),
        )
    )
    if asset is None:
        raise CanvasGenerationValidationError("generation material is unavailable")
    return asset


def _active_sku(db: Session, *, project_id: str, sku_id: str) -> CanvasProjectSku:
    sku = db.scalar(
        select(CanvasProjectSku).where(
            CanvasProjectSku.id == sku_id,
            CanvasProjectSku.project_id == project_id,
            CanvasProjectSku.deleted_at.is_(None),
        )
    )
    if sku is None:
        raise CanvasGenerationValidationError("generation SKU is unavailable")
    return sku


def _validate_model_dimensions(
    capabilities: ModelCapabilities,
    *,
    width: int,
    height: int,
    ratio: str,
    reference_count: int,
) -> None:
    if not capabilities.text_to_image or capabilities.max_quantity < 1:
        raise CanvasGenerationValidationError("selected model cannot generate this output")
    if capabilities.min_width is not None and width < capabilities.min_width:
        raise CanvasGenerationValidationError("selected width is below the model minimum")
    if capabilities.max_width is not None and width > capabilities.max_width:
        raise CanvasGenerationValidationError("selected width exceeds the model maximum")
    if capabilities.min_height is not None and height < capabilities.min_height:
        raise CanvasGenerationValidationError("selected height is below the model minimum")
    if capabilities.max_height is not None and height > capabilities.max_height:
        raise CanvasGenerationValidationError("selected height exceeds the model maximum")
    size = f"{width}x{height}"
    if capabilities.allowed_sizes and size not in capabilities.allowed_sizes:
        raise CanvasGenerationValidationError("selected size is unsupported by the model")
    if capabilities.allowed_ratios and ratio not in capabilities.allowed_ratios:
        raise CanvasGenerationValidationError("selected ratio is unsupported by the model")
    if reference_count > capabilities.max_reference_images:
        raise CanvasGenerationValidationError("too many reference images for the model")
    if reference_count and not capabilities.image_to_image:
        raise CanvasGenerationValidationError("selected model does not support product references")
    if reference_count and capabilities.reference_transfer == "none":
        raise CanvasGenerationValidationError("selected model does not accept references")


def _generation_node_dimensions(node: Any) -> tuple[int, int, str]:
    width = node.parameters.get("width")
    height = node.parameters.get("height")
    if (
        isinstance(width, bool)
        or not isinstance(width, int)
        or width < 1
        or isinstance(height, bool)
        or not isinstance(height, int)
        or height < 1
    ):
        raise CanvasGenerationValidationError(
            "advanced generation node must define positive integer dimensions"
        )
    divisor = gcd(width, height)
    return width, height, f"{width // divisor}:{height // divisor}"


def _advanced_route_binding(
    *,
    semantic: Any,
    layout_state: Any,
    requested: Any,
    output_node: Any,
) -> tuple[str, str, tuple[str, ...]]:
    """Resolve one advanced item only from its explicit, canonical graph route."""

    nodes = {node.id: node for node in semantic.nodes}

    def single_edge(kind: str, target_node_id: str, label: str) -> Any:
        matches = [
            edge
            for edge in semantic.edges
            if edge.kind == kind and edge.target_node_id == target_node_id
        ]
        if len(matches) != 1:
            raise CanvasGenerationValidationError(
                f"advanced {label} must have exactly one {kind} input"
            )
        return matches[0]

    if (
        output_node.model_profile_id is not None
        or output_node.prompt is not None
        or output_node.composition_group_id is not None
    ):
        raise CanvasGenerationValidationError(
            "advanced output bindings must be expressed by graph edges"
        )

    composition_edge = single_edge("composition", output_node.id, "output")
    composition = nodes.get(composition_edge.source_node_id)
    if composition is None or composition.kind != "composition_group":
        raise CanvasGenerationValidationError("advanced output composition source is invalid")
    group_id = composition.composition_group_id
    if group_id is None or group_id != requested.composition_group_id:
        raise CanvasGenerationValidationError("advanced output composition binding is inconsistent")

    generation_edge = single_edge("output_image", output_node.id, "output")
    generation = nodes.get(generation_edge.source_node_id)
    if generation is None or generation.kind != "model_generation":
        raise CanvasGenerationValidationError("advanced output generation source is invalid")
    if generation.model_profile_id != requested.model_profile_id:
        raise CanvasGenerationValidationError("advanced output model binding is stale")
    node_width, node_height, node_ratio = _generation_node_dimensions(generation)
    if (
        requested.width != node_width
        or requested.height != node_height
        or requested.ratio != node_ratio
    ):
        raise CanvasGenerationValidationError(
            "advanced output dimensions must match the generation node"
        )

    prompt_edge = single_edge("prompt", generation.id, "generation")
    prompt = nodes.get(prompt_edge.source_node_id)
    if prompt is None or prompt.kind != "prompt" or prompt.prompt != requested.prompt:
        raise CanvasGenerationValidationError("advanced output prompt binding is stale")

    cutout_edge = single_edge("cutout_asset", generation.id, "generation")
    cutout = nodes.get(cutout_edge.source_node_id)
    if (
        cutout is None
        or cutout.id != "main-product-cutout"
        or cutout.kind != "auto_cutout"
        or cutout.sku_id is not None
        or cutout.asset_id is None
    ):
        raise CanvasGenerationValidationError("advanced product cutout is not the system projection")

    product_edge = single_edge("product_asset", cutout.id, "auto cutout")
    source = nodes.get(product_edge.source_node_id)
    if (
        source is None
        or source.id != "main-product-source"
        or source.kind != "product_source"
        or source.sku_id is not None
        or source.asset_id is None
    ):
        raise CanvasGenerationValidationError("advanced product source is not the system projection")
    main_layers = [
        layer
        for layer in layout_state.product_layers
        if layer.sku_id is None and layer.locked
    ]
    if (
        len(main_layers) != 1
        or source.asset_id != main_layers[0].source_asset_id
        or cutout.asset_id != main_layers[0].render_asset_id
    ):
        raise CanvasGenerationValidationError(
            "advanced system cutout does not match the locked product layer"
        )

    if any(
        edge.kind == "background_image" and edge.target_node_id == output_node.id
        for edge in semantic.edges
    ):
        raise CanvasGenerationValidationError("advanced output background edges are unsupported")
    text_snapshot_ids: list[str] = []
    for edge in semantic.edges:
        if edge.kind != "text_layer" or edge.target_node_id != output_node.id:
            continue
        text = nodes.get(edge.source_node_id)
        if text is None or text.kind != "text_layer" or text.text_snapshot_id is None:
            raise CanvasGenerationValidationError("advanced text edge has no text snapshot")
        text_snapshot_ids.append(text.text_snapshot_id)
    if len(text_snapshot_ids) != len(set(text_snapshot_ids)):
        raise CanvasGenerationValidationError("advanced output repeats a text snapshot")
    if set(text_snapshot_ids) != set(requested.text_snapshot_ids):
        raise CanvasGenerationValidationError("advanced text snapshots must be wired to the output")
    return group_id, cutout.asset_id, tuple(text_snapshot_ids)


def _resolve_item_snapshots(
    db: Session,
    *,
    project_id: str,
    request: CanvasGenerationCreate,
) -> list[GenerationItemSnapshot]:
    snapshot = get_project_snapshot(db, project_id=project_id)
    if snapshot.project.status != "active":
        raise CanvasProjectStatusConflict(snapshot.project.status)
    if snapshot.revision != request.revision:
        raise CanvasRevisionConflict(snapshot.revision)

    semantic = snapshot.semantic_state
    layout_state = snapshot.layout_state
    _require_unique((node.id for node in semantic.nodes), label="node")
    _require_unique((board.id for board in semantic.output_boards), label="board")
    _require_unique((edge.id for edge in semantic.edges), label="edge")
    _require_unique((group.id for group in semantic.composition_groups), label="group")
    _require_unique((layer.id for layer in layout_state.product_layers), label="product layer")
    _require_unique((item.id for item in layout_state.text_snapshots), label="text snapshot")
    if semantic.mode != request.mode:
        raise CanvasGenerationValidationError("generation mode is stale")

    result: list[GenerationItemSnapshot] = []
    for ordinal, requested in enumerate(request.items):
        board = _one_by_id(semantic.output_boards, requested.board_id, label="output board")
        node = _one_by_id(semantic.nodes, requested.node_id, label="output node")
        if board.output_node_id != node.id or node.output_board_id != board.id:
            raise CanvasGenerationValidationError("output board/node binding is inconsistent")
        if board.output_type != requested.output_type:
            raise CanvasGenerationValidationError("output board type does not match the request")
        if node.kind != OUTPUT_NODE_KIND_BY_TYPE[requested.output_type]:
            raise CanvasGenerationValidationError("output node type does not match the request")
        if requested.board_order != board.sort_order:
            raise CanvasGenerationValidationError("output board order is stale")
        if board.sku_id != requested.sku_id or node.sku_id != requested.sku_id:
            raise CanvasGenerationValidationError("output SKU binding is inconsistent")
        advanced_cutout_asset_id: str | None = None
        advanced_text_snapshot_ids: tuple[str, ...] | None = None
        if request.mode == "advanced":
            (
                group_id,
                advanced_cutout_asset_id,
                advanced_text_snapshot_ids,
            ) = _advanced_route_binding(
                semantic=semantic,
                layout_state=layout_state,
                requested=requested,
                output_node=node,
            )
        else:
            if node.model_profile_id is not None and node.model_profile_id != requested.model_profile_id:
                raise CanvasGenerationValidationError("output model binding is stale")
            if node.prompt is not None and node.prompt != requested.prompt:
                raise CanvasGenerationValidationError("output prompt binding is stale")
            if node.composition_group_id != requested.composition_group_id:
                raise CanvasGenerationValidationError("output composition binding is inconsistent")
            group_id = requested.composition_group_id

        group = _one_by_id(
            semantic.composition_groups,
            group_id or "",
            label="composition group",
        )
        authoritative_hash = composition_layout_hash(group.layout)
        if group.layout_hash != authoritative_hash or requested.layout_hash != authoritative_hash:
            raise CanvasGenerationValidationError("composition layout hash is stale or forged")
        if requested.sku_id is not None and requested.sku_id not in group.sku_ids:
            raise CanvasGenerationValidationError("SKU is not a member of the composition group")

        sku = (
            _active_sku(db, project_id=project_id, sku_id=requested.sku_id)
            if requested.sku_id is not None
            else None
        )
        model = db.scalar(
            select(ImageModelProfile).where(
                ImageModelProfile.id == requested.model_profile_id,
                ImageModelProfile.enabled.is_(True),
            )
        )
        if model is None:
            raise CanvasGenerationValidationError("selected model is unavailable")
        provider = db.scalar(
            select(ImageProviderConnection).where(
                ImageProviderConnection.id == model.provider_id,
                ImageProviderConnection.enabled.is_(True),
            )
        )
        if provider is None:
            raise CanvasGenerationValidationError("selected Provider is unavailable")
        model_snapshot = _model_snapshot(model)
        capabilities = ModelCapabilities(**model_snapshot["capabilities"])
        _validate_model_dimensions(
            capabilities,
            width=requested.width,
            height=requested.height,
            ratio=requested.ratio,
            reference_count=sum(
                1
                for material in requested.inputs
                if material.input_role in {"product", "reference"}
            ),
        )

        input_snapshots: list[GenerationInputSnapshot] = []
        input_assets: dict[str, CanvasAsset] = {}
        for material in requested.inputs:
            asset = _active_asset(
                db,
                project_id=project_id,
                asset_id=material.asset_id,
            )
            input_assets[material.asset_id] = asset
            input_snapshots.append(
                GenerationInputSnapshot(
                    asset_id=asset.id,
                    input_role=material.input_role,
                    ordinal=material.ordinal,
                    asset_sha256=asset.sha256,
                )
            )
        product_asset_id = next(
            value.asset_id for value in input_snapshots if value.input_role == "product"
        )
        if (
            advanced_cutout_asset_id is not None
            and product_asset_id != advanced_cutout_asset_id
        ):
            raise CanvasGenerationValidationError(
                "advanced product material must be the system cutout projection"
            )
        group_layers = [
            layer
            for layer in layout_state.product_layers
            if layer.id in group.product_layer_ids
            and layer.composition_group_id == group.id
            and layer.sku_id == requested.sku_id
            and product_asset_id in {layer.source_asset_id, layer.render_asset_id}
        ]
        if len(group_layers) != 1:
            raise CanvasGenerationValidationError(
                "product material is not bound to exactly one locked composition layer"
            )
        layer = group_layers[0]
        if not layer.locked:
            raise CanvasGenerationValidationError("product composition layer must be locked")
        source_asset = _active_asset(
            db,
            project_id=project_id,
            asset_id=layer.source_asset_id,
        )
        render_asset = _active_asset(
            db,
            project_id=project_id,
            asset_id=layer.render_asset_id,
        )
        transform = layout_state.object_transforms.get(layer.transform_id)
        if transform is None:
            raise CanvasGenerationValidationError("product transform is unavailable")

        requested_text_snapshot_ids = (
            advanced_text_snapshot_ids
            if advanced_text_snapshot_ids is not None
            else tuple(requested.text_snapshot_ids)
        )
        text_snapshots = [
            _one_by_id(layout_state.text_snapshots, identifier, label="text snapshot")
            for identifier in requested_text_snapshot_ids
        ]
        layout_snapshot = {
            "version": 1,
            "compositionGroupId": group.id,
            "composition": group.layout.model_dump(by_alias=True, mode="json"),
            "layoutHash": authoritative_hash,
            "productLayer": {
                **layer.model_dump(by_alias=True, mode="json"),
                "sourceAssetSha256": source_asset.sha256,
                "renderAssetSha256": render_asset.sha256,
                "sourceWidth": source_asset.width,
                "sourceHeight": source_asset.height,
                "renderWidth": render_asset.width,
                "renderHeight": render_asset.height,
                "transform": transform.model_dump(by_alias=True, mode="json"),
            },
            "textSnapshots": [
                item.model_dump(by_alias=True, mode="json") for item in text_snapshots
            ],
            "outputBoard": board.model_dump(by_alias=True, mode="json"),
            "outputNode": node.model_dump(by_alias=True, mode="json"),
        }
        result.append(
            GenerationItemSnapshot(
                ordinal=ordinal,
                output_type=requested.output_type,
                sku_id=requested.sku_id,
                sku_name=sku.name if sku is not None else None,
                board_id=board.id,
                node_id=node.id,
                board_order=board.sort_order,
                provider_id=provider.id,
                provider_config_version=provider.config_version,
                provider_config=_provider_snapshot(provider),
                model_profile_id=model.id,
                model_display_name=model.display_name,
                model_config_version=model.config_version,
                model_config=model_snapshot,
                prompt=requested.prompt,
                width=requested.width,
                height=requested.height,
                ratio=requested.ratio,
                composition_group_id=group.id,
                layout_hash=authoritative_hash,
                layout=layout_snapshot,
                inputs=tuple(input_snapshots),
                text_snapshots=tuple(
                    item.model_dump(by_alias=True, mode="json") for item in text_snapshots
                ),
            )
        )
    return result


def _reservation_totals(db: Session, *, project_id: str) -> tuple[int, int]:
    project_reserved = db.scalar(
        select(func.coalesce(func.sum(CanvasGeneration.storage_reservation_remaining_bytes), 0))
        .where(
            CanvasGeneration.project_id == project_id,
            CanvasGeneration.storage_reservation_remaining_bytes > 0,
        )
    )
    total_reserved = db.scalar(
        select(func.coalesce(func.sum(CanvasGeneration.storage_reservation_remaining_bytes), 0))
        .where(CanvasGeneration.storage_reservation_remaining_bytes > 0)
    )
    return int(project_reserved or 0), int(total_reserved or 0)


def active_generation_reservations(
    db: Session,
    *,
    project_id: str,
) -> tuple[int, int]:
    """Return current project/total remaining reservations for capacity writers."""

    return _reservation_totals(db, project_id=project_id)


def debit_generation_reservation(
    db: Session,
    *,
    generation_id: str,
    allocated_bytes: int,
    project_id: str | None = None,
) -> int:
    """Atomically debit bytes that were newly allocated by a durable stage."""

    if (
        isinstance(allocated_bytes, bool)
        or not isinstance(allocated_bytes, int)
        or allocated_bytes < 0
    ):
        raise CanvasGenerationReservationError("allocated bytes must be non-negative")
    if allocated_bytes == 0:
        generation = db.get(CanvasGeneration, generation_id)
        if generation is None:
            raise CanvasGenerationValidationError("generation does not exist")
        return generation.storage_reservation_remaining_bytes
    conditions = [
        CanvasGeneration.id == generation_id,
        CanvasGeneration.storage_reservation_remaining_bytes >= allocated_bytes,
    ]
    if project_id is not None:
        conditions.append(CanvasGeneration.project_id == project_id)
    result = db.execute(
        update(CanvasGeneration)
        .where(*conditions)
        .values(
            storage_reservation_remaining_bytes=(
                CanvasGeneration.storage_reservation_remaining_bytes - allocated_bytes
            )
        )
    )
    if result.rowcount != 1:
        raise CanvasGenerationReservationError(
            "generation reservation is missing or insufficient"
        )
    remaining = db.scalar(
        select(CanvasGeneration.storage_reservation_remaining_bytes).where(
            CanvasGeneration.id == generation_id
        )
    )
    assert remaining is not None
    return int(remaining)


def extend_generation_reservation(
    db: Session,
    *,
    generation_id: str,
    additional_bytes: int,
) -> int:
    """Extend a reservation before a stage writes beyond its saved estimate."""

    if (
        isinstance(additional_bytes, bool)
        or not isinstance(additional_bytes, int)
        or additional_bytes <= 0
    ):
        raise CanvasGenerationReservationError("additional bytes must be positive")
    if db.in_transaction():
        raise CanvasGenerationTransactionError(
            "extend_generation_reservation requires a fresh Session transaction"
        )
    with storage.CANVAS_ALLOCATION_LOCK:
        try:
            db.execute(text("BEGIN IMMEDIATE"))
            generation = db.get(CanvasGeneration, generation_id)
            if generation is None:
                raise CanvasGenerationValidationError("generation does not exist")
            project_reserved, total_reserved = _reservation_totals(
                db,
                project_id=generation.project_id,
            )
            storage.assert_canvas_capacity(
                project_id=generation.project_id,
                additional_bytes=additional_bytes,
                reserved_project_bytes=project_reserved,
                reserved_total_bytes=total_reserved,
            )
            generation.storage_reservation_bytes += additional_bytes
            generation.storage_reservation_remaining_bytes += additional_bytes
            new_remaining = generation.storage_reservation_remaining_bytes
            db.commit()
            return new_remaining
        except Exception:
            db.rollback()
            raise


def release_generation_reservation(
    db: Session,
    *,
    generation_id: str,
) -> None:
    """Release unused bytes inside the caller's terminal-state transaction."""

    result = db.execute(
        update(CanvasGeneration)
        .where(CanvasGeneration.id == generation_id)
        .values(storage_reservation_remaining_bytes=0)
    )
    if result.rowcount != 1:
        raise CanvasGenerationValidationError("generation does not exist")


def restore_generation_reservation(
    db: Session,
    *,
    generation_id: str,
    required_bytes: int,
) -> int:
    """Restore just the remaining peak capacity needed by a retry.

    A terminal generation releases its unused reservation.  Retrying an Item
    must therefore re-check quota before any new paid Attempt or local
    Operation is made durable.  Replays reuse an already-restored reservation
    instead of charging capacity twice.
    """

    if (
        isinstance(required_bytes, bool)
        or not isinstance(required_bytes, int)
        or required_bytes <= 0
    ):
        raise CanvasGenerationReservationError("required bytes must be positive")
    generation = db.get(CanvasGeneration, generation_id)
    if generation is None:
        raise CanvasGenerationValidationError("generation does not exist")
    existing = int(generation.storage_reservation_remaining_bytes)
    if existing >= required_bytes:
        return existing
    additional = required_bytes - existing
    with storage.CANVAS_ALLOCATION_LOCK:
        project_reserved, total_reserved = _reservation_totals(
            db,
            project_id=generation.project_id,
        )
        storage.assert_canvas_capacity(
            project_id=generation.project_id,
            additional_bytes=additional,
            reserved_project_bytes=project_reserved,
            reserved_total_bytes=total_reserved,
        )
        if generation.storage_reservation_bytes < required_bytes:
            generation.storage_reservation_bytes = required_bytes
        generation.storage_reservation_remaining_bytes = required_bytes
        generation.safe_storage_block_reason = None
        generation.storage_blocked_at = None
    return required_bytes


def _replay_or_conflict(
    generation: CanvasGeneration,
    *,
    client_request_hash: str,
) -> tuple[CanvasGeneration, bool]:
    if _existing_client_hash(generation) != client_request_hash:
        raise CanvasGenerationIdempotencyConflict(
            "Idempotency-Key was already used for a different generation request"
        )
    return generation, False


def create_generation(
    db: Session,
    *,
    project_id: str,
    request: CanvasGenerationCreate,
    idempotency_key: str,
) -> tuple[CanvasGeneration, bool]:
    """Create the complete Generation graph in one serialized transaction."""

    key = validate_idempotency_key(idempotency_key)
    client_hash = _client_request_hash(request)
    if db.in_transaction():
        raise CanvasGenerationTransactionError(
            "create_generation requires a fresh Session transaction"
        )

    with storage.CANVAS_ALLOCATION_LOCK:
        try:
            # This must be the first database statement on the fresh Session.
            _begin_generation_transaction(db)
            existing = db.scalar(
                select(CanvasGeneration).where(
                    CanvasGeneration.project_id == project_id,
                    CanvasGeneration.idempotency_key == key,
                )
            )
            if existing is not None:
                result = _replay_or_conflict(
                    existing,
                    client_request_hash=client_hash,
                )
                db.commit()
                return result

            active = db.scalar(
                select(CanvasGeneration.id).where(
                    CanvasGeneration.project_id == project_id,
                    CanvasGeneration.status.in_(_ACTIVE_GENERATION_STATUSES),
                ).limit(1)
            )
            if active is not None:
                raise CanvasGenerationActiveConflict(
                    "project already has an active generation"
                )

            item_snapshots = _resolve_item_snapshots(
                db,
                project_id=project_id,
                request=request,
            )
            fingerprint = compute_generation_fingerprint(
                project_revision=request.revision,
                items=item_snapshots,
            )
            reservation = estimate_generation_storage_reservation(
                item_snapshots,
                remote_image_max_bytes=CANVAS_REMOTE_IMAGE_MAX_BYTES,
            )
            project_reserved, total_reserved = _reservation_totals(
                db,
                project_id=project_id,
            )
            storage.assert_canvas_capacity(
                project_id=project_id,
                additional_bytes=reservation,
                reserved_project_bytes=project_reserved,
                reserved_total_bytes=total_reserved,
            )

            generation = CanvasGeneration(
                id=str(uuid4()),
                project_id=project_id,
                mode="complete_set" if request.mode == "complete-set" else "advanced",
                project_revision=request.revision,
                request_snapshot_json=_request_snapshot(
                    request,
                    client_request_hash=client_hash,
                    fingerprint=fingerprint,
                ),
                request_fingerprint=fingerprint,
                idempotency_key=key,
                status="queued",
                total_items=len(item_snapshots),
                storage_reservation_bytes=reservation,
                storage_reservation_remaining_bytes=reservation,
            )
            db.add(generation)
            # The persisted request graph has no ORM relationships.  Flush its
            # database parent before adding independently constructed children
            # so SQLite always validates the real FK topology, including the
            # isolated Provider-backed generation runtime.
            db.flush()
            for item_snapshot in item_snapshots:
                provider_json = _json(item_snapshot.provider_config)
                model_json = _json(item_snapshot.model_config)
                item = CanvasGenerationItem(
                    id=str(uuid4()),
                    generation_id=generation.id,
                    ordinal=item_snapshot.ordinal,
                    output_type=item_snapshot.output_type,
                    sku_id_snapshot=item_snapshot.sku_id,
                    sku_name_snapshot=item_snapshot.sku_name,
                    board_id=item_snapshot.board_id,
                    node_id=item_snapshot.node_id,
                    board_order_snapshot=item_snapshot.board_order,
                    provider_id=item_snapshot.provider_id,
                    provider_config_version=item_snapshot.provider_config_version,
                    model_profile_id=item_snapshot.model_profile_id,
                    model_config_version=item_snapshot.model_config_version,
                    provider_config_snapshot_json=provider_json,
                    model_config_snapshot_json=model_json,
                    prompt=item_snapshot.prompt,
                    width=item_snapshot.width,
                    height=item_snapshot.height,
                    ratio=item_snapshot.ratio,
                    composition_group_id=item_snapshot.composition_group_id,
                    layout_hash=item_snapshot.layout_hash,
                    layout_snapshot_json=_json(item_snapshot.layout),
                    attempt_count=1,
                    status="queued",
                )
                db.add(item)
                db.flush()
                for material in item_snapshot.inputs:
                    db.add(
                        CanvasGenerationItemInput(
                            id=str(uuid4()),
                            item_id=item.id,
                            asset_id=material.asset_id,
                            input_role=material.input_role,
                            ordinal=material.ordinal,
                            asset_sha256=material.asset_sha256,
                        )
                    )
                db.add(
                    CanvasGenerationAttempt(
                        id=str(uuid4()),
                        item_id=item.id,
                        attempt_no=1,
                        provider_id=item_snapshot.provider_id,
                        provider_config_version=item_snapshot.provider_config_version,
                        model_profile_id=item_snapshot.model_profile_id,
                        model_config_version=item_snapshot.model_config_version,
                        provider_config_snapshot_json=provider_json,
                        model_config_snapshot_json=model_json,
                        status="queued",
                        provider_result_stage="awaiting_provider",
                        upstream_idempotency_key=f"canvas:{generation.id}:{item.id}:1",
                        usage_json="{}",
                    )
                )
            db.flush()
            db.commit()
            return generation, True
        except IntegrityError:
            db.rollback()
            winner = db.scalar(
                select(CanvasGeneration).where(
                    CanvasGeneration.project_id == project_id,
                    CanvasGeneration.idempotency_key == key,
                )
            )
            if winner is not None:
                result = _replay_or_conflict(
                    winner,
                    client_request_hash=client_hash,
                )
                db.commit()
                return result
            raise
        except Exception:
            db.rollback()
            raise


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _display_name_from_snapshot(value: str) -> str:
    try:
        document = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return "Unknown model"
    result = document.get("displayName") if isinstance(document, dict) else None
    return result if isinstance(result, str) and result else "Unknown model"


def get_generation_detail(db: Session, *, generation_id: str) -> GenerationDetail:
    generation = db.get(CanvasGeneration, generation_id)
    if generation is None:
        raise CanvasGenerationNotFound("generation does not exist")
    items = list(
        db.scalars(
            select(CanvasGenerationItem)
            .where(CanvasGenerationItem.generation_id == generation.id)
            .order_by(CanvasGenerationItem.ordinal, CanvasGenerationItem.id)
        ).all()
    )
    item_details: list[GenerationItemDetail] = []
    for item in items:
        attempts = list(
            db.scalars(
                select(CanvasGenerationAttempt)
                .where(CanvasGenerationAttempt.item_id == item.id)
                .order_by(CanvasGenerationAttempt.attempt_no, CanvasGenerationAttempt.id)
            ).all()
        )
        item_details.append(
            GenerationItemDetail(
                id=item.id,
                ordinal=item.ordinal,
                output_type=item.output_type,
                sku_id=item.sku_id_snapshot,
                sku_name=item.sku_name_snapshot,
                board_id=item.board_id,
                node_id=item.node_id,
                board_order=item.board_order_snapshot,
                model_profile_id=item.model_profile_id,
                model_display_name=_display_name_from_snapshot(
                    item.model_config_snapshot_json
                ),
                prompt=item.prompt,
                width=item.width,
                height=item.height,
                ratio=item.ratio,
                status=item.status,
                attempt_count=item.attempt_count,
                latest_background_asset_id=item.latest_background_asset_id,
                latest_composed_asset_id=item.latest_composed_asset_id,
                safe_error_code=item.safe_current_error_code,
                safe_error_summary=item.safe_current_error_summary,
                attempts=[
                    GenerationAttemptDetail(
                        id=attempt.id,
                        attempt_no=attempt.attempt_no,
                        status=attempt.status,
                        provider_result_stage=attempt.provider_result_stage,
                        provider_request_id=attempt.provider_request_id,
                        external_task_id=attempt.external_task_id,
                        background_asset_id=attempt.background_asset_id,
                        background_preview_asset_id=attempt.background_preview_asset_id,
                        composed_asset_id=attempt.composed_asset_id,
                        composed_preview_asset_id=attempt.composed_preview_asset_id,
                        safe_error_code=attempt.normalized_error_code,
                        safe_error_summary=attempt.safe_error_summary,
                        created_at=_iso(attempt.created_at) or "",
                        completed_at=_iso(attempt.completed_at),
                    )
                    for attempt in attempts
                ],
            )
        )
    return GenerationDetail(
        id=generation.id,
        project_id=generation.project_id,
        mode="complete-set" if generation.mode == "complete_set" else "advanced",
        project_revision=generation.project_revision,
        fingerprint=generation.request_fingerprint,
        status=generation.status,
        total_items=generation.total_items,
        succeeded_items=generation.succeeded_items,
        failed_items=generation.failed_items,
        cancelled_items=generation.cancelled_items,
        unknown_items=generation.unknown_items,
        storage_reservation_bytes=generation.storage_reservation_bytes,
        storage_reservation_remaining_bytes=generation.storage_reservation_remaining_bytes,
        safe_storage_block_reason=generation.safe_storage_block_reason,
        created_at=_iso(generation.created_at) or "",
        updated_at=_iso(generation.updated_at) or "",
        started_at=_iso(generation.started_at),
        completed_at=_iso(generation.completed_at),
        items=item_details,
    )


def _encode_cursor(completed_at: datetime, attempt_id: str) -> str:
    raw = _json({"completedAt": completed_at.isoformat(), "attemptId": attempt_id})
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def _decode_cursor(value: str) -> tuple[datetime, str]:
    if not isinstance(value, str) or not value or len(value) > 1024:
        raise CanvasGenerationValidationError("result-version cursor is invalid")
    try:
        padded = value + "=" * (-len(value) % 4)
        document = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        completed_at = datetime.fromisoformat(document["completedAt"])
        attempt_id = document["attemptId"]
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CanvasGenerationValidationError("result-version cursor is invalid") from exc
    if not isinstance(attempt_id, str) or not attempt_id:
        raise CanvasGenerationValidationError("result-version cursor is invalid")
    return completed_at, attempt_id


def _valid_result_asset_chain(
    db: Session,
    *,
    project_id: str,
    attempt: CanvasGenerationAttempt,
    expected_width: int,
    expected_height: int,
) -> tuple[CanvasAsset, CanvasAsset, CanvasAsset, CanvasAsset] | None:
    identifiers = (
        attempt.background_asset_id,
        attempt.background_preview_asset_id,
        attempt.composed_asset_id,
        attempt.composed_preview_asset_id,
    )
    if any(identifier is None for identifier in identifiers):
        return None
    assets = {
        asset.id: asset
        for asset in db.scalars(
            select(CanvasAsset).where(
                CanvasAsset.id.in_(identifiers),
                CanvasAsset.project_id == project_id,
                CanvasAsset.deleted_at.is_(None),
            )
        ).all()
    }
    if len(assets) != 4:
        return None
    background = assets.get(attempt.background_asset_id)
    background_preview = assets.get(attempt.background_preview_asset_id)
    composed = assets.get(attempt.composed_asset_id)
    composed_preview = assets.get(attempt.composed_preview_asset_id)
    if None in (background, background_preview, composed, composed_preview):
        return None
    assert background is not None
    assert background_preview is not None
    assert composed is not None
    assert composed_preview is not None
    if (
        background.asset_type != "generated_background"
        or composed.asset_type != "composed"
        or background_preview.asset_type != "preview"
        or composed_preview.asset_type != "preview"
        or background_preview.source_asset_id != background.id
        or composed.source_asset_id != background.id
        or composed_preview.source_asset_id != composed.id
        or (background.width, background.height) != (expected_width, expected_height)
        or (composed.width, composed.height) != (expected_width, expected_height)
        or background_preview.width <= 0
        or background_preview.height <= 0
        or composed_preview.width <= 0
        or composed_preview.height <= 0
        or max(background_preview.width, background_preview.height) > 2_048
        or max(composed_preview.width, composed_preview.height) > 2_048
    ):
        return None
    return background, background_preview, composed, composed_preview


def list_board_result_versions(
    db: Session,
    *,
    project_id: str,
    board_id: str | None,
    cursor: str | None,
    limit: int,
) -> ResultVersionPage:
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1 or limit > 100:
        raise CanvasGenerationValidationError("result-version limit must be 1-100")
    if db.get(CanvasProject, project_id) is None:
        raise CanvasGenerationNotFound("project does not exist")
    query = (
        select(CanvasGenerationAttempt, CanvasGenerationItem, CanvasGeneration)
        .join(CanvasGenerationItem, CanvasGenerationItem.id == CanvasGenerationAttempt.item_id)
        .join(CanvasGeneration, CanvasGeneration.id == CanvasGenerationItem.generation_id)
        .where(
            CanvasGeneration.project_id == project_id,
            CanvasGenerationAttempt.status == "succeeded",
            CanvasGenerationAttempt.provider_result_stage == "complete",
            CanvasGenerationAttempt.completed_at.is_not(None),
        )
    )
    if board_id is not None:
        query = query.where(CanvasGenerationItem.board_id == board_id)
    if cursor is not None:
        cursor_time, cursor_attempt = _decode_cursor(cursor)
        query = query.where(
            (CanvasGenerationAttempt.completed_at < cursor_time)
            | (
                (CanvasGenerationAttempt.completed_at == cursor_time)
                & (CanvasGenerationAttempt.id < cursor_attempt)
            )
        )
    rows = db.execute(
        query.order_by(
            CanvasGenerationAttempt.completed_at.desc(),
            CanvasGenerationAttempt.id.desc(),
        ).limit(limit + 1)
    ).all()
    versions: list[ResultVersion] = []
    last_scanned: tuple[datetime, str] | None = None
    has_more = len(rows) > limit
    for attempt, item, generation in rows[:limit]:
        last_scanned = (attempt.completed_at, attempt.id)
        chain = _valid_result_asset_chain(
            db,
            project_id=project_id,
            attempt=attempt,
            expected_width=item.width,
            expected_height=item.height,
        )
        if chain is None:
            continue
        background, background_preview, composed, composed_preview = chain
        versions.append(
            ResultVersion(
                version_id=attempt.id,
                generation_id=generation.id,
                item_id=item.id,
                attempt_id=attempt.id,
                board_id=item.board_id,
                output_type=item.output_type,
                sku_id=item.sku_id_snapshot,
                background_asset_id=background.id,
                background_preview_asset_id=background_preview.id,
                composed_asset_id=composed.id,
                composed_preview_asset_id=composed_preview.id,
                width=item.width,
                height=item.height,
                model_profile_id=item.model_profile_id,
                model_display_name=_display_name_from_snapshot(
                    item.model_config_snapshot_json
                ),
                model_config_version=item.model_config_version,
                created_at=_iso(attempt.completed_at) or "",
            )
        )
    next_cursor = (
        _encode_cursor(*last_scanned)
        if has_more and last_scanned is not None
        else None
    )
    return ResultVersionPage(items=versions, next_cursor=next_cursor)


__all__ = [
    "CanvasGenerationActiveConflict",
    "CanvasGenerationError",
    "CanvasGenerationIdempotencyConflict",
    "CanvasGenerationNotFound",
    "CanvasGenerationReservationError",
    "CanvasGenerationTransactionError",
    "CanvasGenerationValidationError",
    "active_generation_reservations",
    "create_generation",
    "debit_generation_reservation",
    "extend_generation_reservation",
    "get_generation_detail",
    "list_board_result_versions",
    "release_generation_reservation",
    "restore_generation_reservation",
    "validate_idempotency_key",
]
