"""Strict public and immutable internal schemas for Canvas generations."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from pydantic.alias_generators import to_camel
from typing_extensions import Annotated

from services.canvas.schemas import CanvasWireModel, Identifier, Prompt


LayoutHash = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        pattern=r"^sha256:[0-9a-f]{64}$",
        min_length=71,
        max_length=71,
    ),
]
Ratio = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        pattern=r"^[1-9][0-9]{0,4}:[1-9][0-9]{0,4}$",
        min_length=3,
        max_length=11,
    ),
]
InputRole = Literal["product", "reference"]


class GenerationInputCreate(CanvasWireModel):
    asset_id: Identifier
    input_role: InputRole
    ordinal: int = Field(ge=0, le=49)


class GenerationItemCreate(CanvasWireModel):
    output_type: Literal["main", "sku", "detail"]
    sku_id: Identifier | None = None
    board_id: Identifier
    node_id: Identifier
    board_order: int = Field(ge=0, le=10_000)
    model_profile_id: Identifier
    prompt: Prompt
    width: int = Field(strict=True, ge=1, le=32_768)
    height: int = Field(strict=True, ge=1, le=32_768)
    ratio: Ratio
    composition_group_id: Identifier | None = None
    layout_hash: LayoutHash
    inputs: list[GenerationInputCreate] = Field(min_length=1, max_length=20)
    text_snapshot_ids: list[Identifier] = Field(default_factory=list, max_length=500)

    @model_validator(mode="after")
    def validate_bindings(self) -> "GenerationItemCreate":
        product_inputs = [item for item in self.inputs if item.input_role == "product"]
        if len(product_inputs) != 1:
            raise ValueError("each generation item requires exactly one product material")
        bindings = [(item.input_role, item.ordinal) for item in self.inputs]
        if len(bindings) != len(set(bindings)):
            raise ValueError("generation input role/ordinal bindings must be unique")
        if len(self.text_snapshot_ids) != len(set(self.text_snapshot_ids)):
            raise ValueError("textSnapshotIds must be unique")
        if self.output_type == "sku":
            if self.sku_id is None:
                raise ValueError("SKU output requires skuId")
            if self.composition_group_id is None:
                raise ValueError("SKU output requires compositionGroupId")
        elif self.sku_id is not None:
            raise ValueError("main/detail output cannot bind a SKU")
        return self


class CanvasGenerationCreate(CanvasWireModel):
    revision: int = Field(strict=True, ge=1)
    mode: Literal["complete-set", "advanced"]
    items: list[GenerationItemCreate] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def validate_expanded_items(self) -> "CanvasGenerationCreate":
        board_ids = [item.board_id for item in self.items]
        if len(board_ids) != len(set(board_ids)):
            raise ValueError("each generation item requires a unique output board")
        node_ids = [item.node_id for item in self.items]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("each generation item requires a unique output node")
        groups: dict[tuple[str, str | None], int] = {}
        for item in self.items:
            key = (item.output_type, item.sku_id)
            groups[key] = groups.get(key, 0) + 1
        if any(count > 20 for count in groups.values()):
            raise ValueError("each output group is limited to 20 explicit items")
        return self


class _CanvasResponseModel(BaseModel):
    # Services construct response DTOs with Python field names; the HTTP wire
    # representation remains camelCase through the inherited alias generator.
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        populate_by_name=True,
    )


class GenerationAttemptDetail(_CanvasResponseModel):
    id: Identifier
    attempt_no: int
    status: str
    provider_result_stage: str
    provider_request_id: str | None = None
    external_task_id: str | None = None
    background_asset_id: Identifier | None = None
    background_preview_asset_id: Identifier | None = None
    composed_asset_id: Identifier | None = None
    composed_preview_asset_id: Identifier | None = None
    safe_error_code: str | None = None
    safe_error_summary: str | None = None
    created_at: str
    completed_at: str | None = None


class GenerationItemDetail(_CanvasResponseModel):
    id: Identifier
    ordinal: int
    output_type: Literal["main", "sku", "detail"]
    sku_id: Identifier | None = None
    sku_name: str | None = None
    board_id: Identifier
    node_id: Identifier
    board_order: int
    model_profile_id: Identifier
    model_display_name: str
    prompt: str
    width: int
    height: int
    ratio: str
    status: str
    attempt_count: int
    latest_background_asset_id: Identifier | None = None
    latest_composed_asset_id: Identifier | None = None
    safe_error_code: str | None = None
    safe_error_summary: str | None = None
    attempts: list[GenerationAttemptDetail]


class GenerationDetail(_CanvasResponseModel):
    id: Identifier
    project_id: Identifier
    mode: Literal["complete-set", "advanced"]
    project_revision: int
    fingerprint: str
    status: str
    total_items: int
    succeeded_items: int
    failed_items: int
    cancelled_items: int
    unknown_items: int
    storage_reservation_bytes: int
    storage_reservation_remaining_bytes: int
    safe_storage_block_reason: str | None = None
    created_at: str
    updated_at: str
    started_at: str | None = None
    completed_at: str | None = None
    items: list[GenerationItemDetail]


class ResultVersion(_CanvasResponseModel):
    version_id: Identifier
    generation_id: Identifier
    item_id: Identifier
    attempt_id: Identifier
    board_id: Identifier
    output_type: Literal["main", "sku", "detail"]
    sku_id: Identifier | None = None
    background_asset_id: Identifier
    background_preview_asset_id: Identifier
    composed_asset_id: Identifier
    composed_preview_asset_id: Identifier
    width: int
    height: int
    model_profile_id: Identifier
    model_display_name: str
    model_config_version: int
    created_at: str


class ResultVersionPage(_CanvasResponseModel):
    items: list[ResultVersion]
    next_cursor: str | None = None


@dataclass(frozen=True)
class GenerationInputSnapshot:
    asset_id: str
    input_role: str
    ordinal: int
    asset_sha256: str


@dataclass(frozen=True)
class GenerationItemSnapshot:
    ordinal: int
    output_type: str
    sku_id: str | None
    sku_name: str | None
    board_id: str
    node_id: str
    board_order: int
    provider_id: str
    provider_config_version: int
    provider_config: dict[str, Any]
    model_profile_id: str
    model_display_name: str
    model_config_version: int
    model_config: dict[str, Any]
    prompt: str
    width: int
    height: int
    ratio: str
    composition_group_id: str | None
    layout_hash: str
    layout: dict[str, Any]
    inputs: tuple[GenerationInputSnapshot, ...]
    text_snapshots: tuple[dict[str, Any], ...]


__all__ = [
    "CanvasGenerationCreate",
    "GenerationAttemptDetail",
    "GenerationDetail",
    "GenerationInputCreate",
    "GenerationInputSnapshot",
    "GenerationItemDetail",
    "GenerationItemCreate",
    "GenerationItemSnapshot",
    "LayoutHash",
    "ResultVersion",
    "ResultVersionPage",
]
