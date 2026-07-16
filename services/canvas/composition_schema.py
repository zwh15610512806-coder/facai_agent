"""Strict camelCase v1 composition contracts shared by persistence and workers."""
from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


def _to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in tail)


Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
LayoutHash = Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]


class CompositionWireModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        allow_inf_nan=False,
        extra="forbid",
        populate_by_name=False,
        strict=True,
        validate_assignment=True,
    )


class NormalizedSlot(CompositionWireModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def remains_inside_board(self) -> "NormalizedSlot":
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("normalized slot must remain inside the board")
        return self


class NormalizedAnchor(CompositionWireModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class SafeArea(CompositionWireModel):
    top: float = Field(ge=0, lt=1)
    right: float = Field(ge=0, lt=1)
    bottom: float = Field(ge=0, lt=1)
    left: float = Field(ge=0, lt=1)

    @model_validator(mode="after")
    def leaves_visible_area(self) -> "SafeArea":
        if self.left + self.right >= 1 or self.top + self.bottom >= 1:
            raise ValueError("safe area insets must leave a visible board region")
        return self


class CompositionLayout(CompositionWireModel):
    slot: NormalizedSlot
    anchor: NormalizedAnchor
    baseline: float = Field(ge=0, le=1)
    relative_product_fraction: float = Field(gt=0, le=1)
    contain: Literal[True]
    safe_area: SafeArea
    rotation: float = Field(ge=-180, le=180)


class PixelSize(CompositionWireModel):
    width: int = Field(gt=0, le=32_768)
    height: int = Field(gt=0, le=32_768)


class OutputRatio(CompositionWireModel):
    width: int = Field(gt=0, le=32_768)
    height: int = Field(gt=0, le=32_768)


class PixelPlacement(CompositionWireModel):
    """Unrotated integer pixel rectangle; rotation is around its center."""

    x: int
    y: int
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    rotation: float = Field(ge=-180, le=180)


class CompositionSpec(CompositionWireModel):
    schema_version: Literal[1]
    project_id: Identifier
    composition_group_id: Identifier
    sku_id: Identifier | None = None
    product_layer_id: Identifier
    source_asset_id: Identifier
    render_asset_id: Identifier
    allow_opaque_fallback: bool
    layout: CompositionLayout
    layout_hash: LayoutHash
    source_size: PixelSize
    output_ratio: OutputRatio
    background: str = ""
    model: str = ""
    lighting: str = ""
    color: str = ""
    decoration: str = ""


DEFAULT_COMPOSITION_LAYOUT: dict[str, Any] = {
    "slot": {"x": 0.1, "y": 0.1, "width": 0.8, "height": 0.8},
    "anchor": {"x": 0.5, "y": 0.5},
    "baseline": 0.9,
    "relativeProductFraction": 0.8,
    "contain": True,
    "safeArea": {"top": 0.05, "right": 0.05, "bottom": 0.05, "left": 0.05},
    "rotation": 0.0,
}
