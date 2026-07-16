"""Strict v1 wire schemas for persisted Product Canvas project state."""
from __future__ import annotations

import math
import re
import unicodedata
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from services.canvas.composition_schema import (
    DEFAULT_COMPOSITION_LAYOUT,
    CompositionLayout,
)


MAX_CANVAS_NODES = 500
MAX_CANVAS_EDGES = 1_000
MAX_PROMPT_CHARACTERS = 4_000
MAX_TEXT_CHARACTERS = 100_000

NODE_KINDS = (
    "product_source",
    "sku_reference",
    "auto_cutout",
    "prompt",
    "model_generation",
    "main_output",
    "sku_output",
    "detail_output",
    "text_layer",
    "composition_group",
    "export",
)

NodeKind = Literal[
    "product_source",
    "sku_reference",
    "auto_cutout",
    "prompt",
    "model_generation",
    "main_output",
    "sku_output",
    "detail_output",
    "text_layer",
    "composition_group",
    "export",
]

EDGE_KINDS = (
    "product_asset",
    "cutout_asset",
    "prompt",
    "background_image",
    "composition",
    "text_layer",
    "output_image",
)

EdgeKind = Literal[
    "product_asset",
    "cutout_asset",
    "prompt",
    "background_image",
    "composition",
    "text_layer",
    "output_image",
]
OutputType = Literal["main", "sku", "detail"]
ManagedBy = Literal["complete-set"]

Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Prompt = Annotated[str, StringConstraints(max_length=MAX_PROMPT_CHARACTERS)]
TextContent = Annotated[str, StringConstraints(max_length=MAX_TEXT_CHARACTERS)]


_WINDOWS_ABSOLUTE_PATH = re.compile(r"^[A-Za-z]:[\\/]")
_REMOTE_URL = re.compile(r"\b[A-Za-z][A-Za-z0-9+.-]*://")
_FABRIC_MARKER_KEYS = {
    "generationhistory",
    "history",
    "objects",
    "resultassetids",
    "resultversions",
    "version",
    "versionhistory",
    "versions",
}


def to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in tail)


def _reject_unsafe_wire_values(value: Any, *, path: str = "state") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"JSON object keys must be strings at {path}")
            if key.casefold() in _FABRIC_MARKER_KEYS:
                raise ValueError(f"Fabric marker {key!r} is forbidden at {path}")
            _reject_unsafe_wire_values(item, path=f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _reject_unsafe_wire_values(item, path=f"{path}[{index}]")
        return
    if value is None or isinstance(value, (bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"JSON numbers must be finite at {path}")
        return
    if not isinstance(value, str):
        raise ValueError(f"non-JSON value is forbidden at {path}")

    stripped = value.strip()
    lowered = stripped.casefold()
    if lowered.startswith("data:"):
        raise ValueError(f"data URLs are forbidden at {path}")
    if _REMOTE_URL.search(stripped) or lowered.startswith(("//", "blob:", "file:")):
        raise ValueError(f"remote URLs are forbidden at {path}")
    if stripped.startswith(("/", "\\")) or _WINDOWS_ABSOLUTE_PATH.match(stripped):
        raise ValueError(f"absolute paths are forbidden at {path}")


class CanvasWireModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        allow_inf_nan=False,
        extra="forbid",
        populate_by_name=False,
        strict=True,
        validate_assignment=True,
    )

    @model_validator(mode="before")
    @classmethod
    def reject_unsafe_wire_values(cls, value: Any) -> Any:
        _reject_unsafe_wire_values(value)
        return value


class CanvasNodeBase(CanvasWireModel):
    id: Identifier
    kind: NodeKind
    managed_by: ManagedBy | None = None
    sku_id: Identifier | None = None
    asset_id: Identifier | None = None
    model_profile_id: Identifier | None = None
    prompt: Prompt | None = None
    composition_group_id: Identifier | None = None
    text_snapshot_id: Identifier | None = None
    output_board_id: Identifier | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class ProductSourceNode(CanvasNodeBase):
    kind: Literal["product_source"]


class SkuReferenceNode(CanvasNodeBase):
    kind: Literal["sku_reference"]


class AutoCutoutNode(CanvasNodeBase):
    kind: Literal["auto_cutout"]


class PromptNode(CanvasNodeBase):
    kind: Literal["prompt"]


class ModelGenerationNode(CanvasNodeBase):
    kind: Literal["model_generation"]


class MainOutputNode(CanvasNodeBase):
    kind: Literal["main_output"]


class SkuOutputNode(CanvasNodeBase):
    kind: Literal["sku_output"]


class DetailOutputNode(CanvasNodeBase):
    kind: Literal["detail_output"]


class TextLayerNode(CanvasNodeBase):
    kind: Literal["text_layer"]


class CompositionGroupNode(CanvasNodeBase):
    kind: Literal["composition_group"]


class ExportNode(CanvasNodeBase):
    kind: Literal["export"]


CanvasNode = Annotated[
    Union[
        ProductSourceNode,
        SkuReferenceNode,
        AutoCutoutNode,
        PromptNode,
        ModelGenerationNode,
        MainOutputNode,
        SkuOutputNode,
        DetailOutputNode,
        TextLayerNode,
        CompositionGroupNode,
        ExportNode,
    ],
    Field(discriminator="kind"),
]


class CanvasEdgeBase(CanvasWireModel):
    id: Identifier
    kind: EdgeKind
    source_node_id: Identifier
    source_port: Identifier
    target_node_id: Identifier
    target_port: Identifier
    sku_id: Identifier | None = None


class ProductAssetEdge(CanvasEdgeBase):
    kind: Literal["product_asset"]


class CutoutAssetEdge(CanvasEdgeBase):
    kind: Literal["cutout_asset"]


class PromptEdge(CanvasEdgeBase):
    kind: Literal["prompt"]


class BackgroundImageEdge(CanvasEdgeBase):
    kind: Literal["background_image"]


class CompositionEdge(CanvasEdgeBase):
    kind: Literal["composition"]


class TextLayerEdge(CanvasEdgeBase):
    kind: Literal["text_layer"]


class OutputImageEdge(CanvasEdgeBase):
    kind: Literal["output_image"]


CanvasEdge = Annotated[
    Union[
        ProductAssetEdge,
        CutoutAssetEdge,
        PromptEdge,
        BackgroundImageEdge,
        CompositionEdge,
        TextLayerEdge,
        OutputImageEdge,
    ],
    Field(discriminator="kind"),
]


class OutputBoard(CanvasWireModel):
    id: Identifier
    output_node_id: Identifier
    output_type: OutputType
    sku_id: Identifier | None = None
    sort_order: int = Field(ge=0)
    selected_result_asset_id: Identifier | None = None


class CompleteSetOutput(CanvasWireModel):
    output_type: OutputType
    sku_id: Identifier | None = None
    quantity: int | None = Field(default=None, ge=1, le=500)
    aspect_ratio: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)] | None = None
    width: int | None = Field(default=None, ge=1, le=32_768)
    height: int | None = Field(default=None, ge=1, le=32_768)
    prompt: Prompt = ""
    model_profile_id: Identifier | None = None
    model_parameters: dict[str, Any] = Field(default_factory=dict)
    reference_asset_id: Identifier | None = None
    composition_group_id: Identifier | None = None


class CompleteSetSettings(CanvasWireModel):
    selected_output_types: list[OutputType] = Field(max_length=3)
    outputs: list[CompleteSetOutput] = Field(max_length=500)

    @model_validator(mode="after")
    def selected_output_types_are_unique(self) -> "CompleteSetSettings":
        if len(set(self.selected_output_types)) != len(self.selected_output_types):
            raise ValueError("selectedOutputTypes must not contain duplicates")
        return self


class CompositionGroup(CanvasWireModel):
    id: Identifier
    sku_ids: list[Identifier] = Field(max_length=500)
    product_layer_ids: list[Identifier] = Field(max_length=500)
    layout_hash: Annotated[str, StringConstraints(max_length=200)]
    layout: CompositionLayout = Field(
        default_factory=lambda: CompositionLayout.model_validate(DEFAULT_COMPOSITION_LAYOUT)
    )

    @model_validator(mode="after")
    def memberships_are_unique(self) -> "CompositionGroup":
        if len(set(self.sku_ids)) != len(self.sku_ids):
            raise ValueError("composition skuIds must not contain duplicates")
        if len(set(self.product_layer_ids)) != len(self.product_layer_ids):
            raise ValueError("composition productLayerIds must not contain duplicates")
        return self


class CanvasSemanticState(CanvasWireModel):
    nodes: list[CanvasNode] = Field(max_length=MAX_CANVAS_NODES)
    edges: list[CanvasEdge] = Field(max_length=MAX_CANVAS_EDGES)
    output_boards: list[OutputBoard] = Field(max_length=500)
    mode: Literal["complete-set", "advanced"]
    advanced_customized: bool
    complete_set: CompleteSetSettings
    composition_groups: list[CompositionGroup] = Field(max_length=500)

    @model_validator(mode="after")
    def composition_group_ids_are_unique(self) -> "CanvasSemanticState":
        ids = [group.id for group in self.composition_groups]
        if len(ids) != len(set(ids)):
            raise ValueError("composition group ids must be unique")
        return self


class NormalizedPoint(CanvasWireModel):
    x: float
    y: float


class NormalizedTransform(CanvasWireModel):
    x: float
    y: float
    scale: float = Field(gt=0, le=1_000)
    rotation: float = Field(ge=-360_000, le=360_000)


class CanvasViewport(CanvasWireModel):
    x: float
    y: float
    zoom: float = Field(gt=0, le=1_000)


class ProductLayer(CanvasWireModel):
    id: Identifier
    source_asset_id: Identifier
    render_asset_id: Identifier
    allow_opaque_fallback: bool = False
    sku_id: Identifier | None = None
    composition_group_id: Identifier | None = None
    transform_id: Identifier
    locked: bool


class TextLineSnapshot(CanvasWireModel):
    text: TextContent
    x: float
    y: float
    width: float = Field(ge=0)


class TextSnapshot(CanvasWireModel):
    id: Identifier
    node_id: Identifier
    content: TextContent
    font_asset_id: Literal[None] = None
    font_family: Literal["Noto Sans CJK SC"] = "Noto Sans CJK SC"
    font_version: Literal[
        "sha256:2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b"
    ] = "sha256:2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b"
    box_width: float = Field(default=0, ge=0)
    lines: list[TextLineSnapshot] = Field(default_factory=list, max_length=10_000)
    font_size: int = Field(default=16, strict=True, gt=0, le=10_000)
    color: Annotated[str, StringConstraints(pattern=r"^#[0-9a-fA-F]{6}$")] = "#0f172a"
    letter_spacing: float = Field(default=0, ge=-10_000, le=10_000)
    line_height: float = Field(default=1, gt=0, le=1_000)
    align: Literal["left", "center", "right"] = "left"
    baseline: Literal["alphabetic", "top", "middle", "bottom"] = "alphabetic"
    z_band: Literal["below-product", "above-product"] = "above-product"
    sort_order: int = Field(default=0, ge=0, le=10_000)

    @model_validator(mode="after")
    def bound_line_snapshot_text(self) -> "TextSnapshot":
        if sum(len(line.text) for line in self.lines) > MAX_TEXT_CHARACTERS:
            raise ValueError(
                f"text snapshot lines exceed {MAX_TEXT_CHARACTERS} characters"
            )
        if any("\r" in line.text or "\n" in line.text for line in self.lines):
            raise ValueError("text snapshot lines must not contain CR or LF")
        expected_content = "\n".join(line.text for line in self.lines)
        if self.content != expected_content or (not self.content and self.lines):
            raise ValueError("text snapshot content must match canonical explicit lines")
        if self.letter_spacing != 0:
            for line in self.lines:
                for character in line.text:
                    codepoint = ord(character)
                    if (
                        codepoint > 0xFFFF
                        or codepoint == 0x200D
                        or 0xFE00 <= codepoint <= 0xFE0F
                        or unicodedata.category(character).startswith("M")
                    ):
                        raise ValueError(
                            "letter spacing supports only independent BMP code points"
                        )
        return self


class CanvasLayoutState(CanvasWireModel):
    node_positions: dict[Identifier, NormalizedPoint]
    object_transforms: dict[Identifier, NormalizedTransform]
    viewport: CanvasViewport
    product_layers: list[ProductLayer] = Field(max_length=500)
    text_snapshots: list[TextSnapshot] = Field(max_length=500)

    @model_validator(mode="after")
    def product_layer_ids_are_unique(self) -> "CanvasLayoutState":
        ids = [layer.id for layer in self.product_layers]
        if len(ids) != len(set(ids)):
            raise ValueError("product layer ids must be unique")
        return self


class SkuCreate(CanvasWireModel):
    name: Name
    reference_asset_id: Identifier | None = None
    prompt: Prompt = ""
    config: dict[str, Any] = Field(default_factory=dict)


class SkuUpdate(CanvasWireModel):
    name: Name | None = None
    reference_asset_id: Identifier | None = None
    prompt: Prompt | None = None
    config: dict[str, Any] | None = None
    sort_order: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> "SkuUpdate":
        if not self.model_fields_set:
            raise ValueError("at least one SKU field is required")
        return self


def empty_semantic_state() -> CanvasSemanticState:
    return CanvasSemanticState.model_validate(
        {
            "nodes": [],
            "edges": [],
            "outputBoards": [],
            "mode": "complete-set",
            "advancedCustomized": False,
            "completeSet": {"selectedOutputTypes": [], "outputs": []},
            "compositionGroups": [],
        }
    )


def empty_layout_state() -> CanvasLayoutState:
    return CanvasLayoutState.model_validate(
        {
            "nodePositions": {},
            "objectTransforms": {},
            "viewport": {"x": 0, "y": 0, "zoom": 1},
            "productLayers": [],
            "textSnapshots": [],
        }
    )
