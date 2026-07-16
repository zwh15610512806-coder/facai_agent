"""Strict public and immutable internal schemas for Canvas exports."""
from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from services.canvas.compose_operations import ComposeRequestSnapshot
from services.canvas.composition_schema import CompositionWireModel
from services.canvas.schemas import CanvasWireModel, Identifier


ExportMode = Literal["single", "category_zip", "detail_slices_zip", "detail_long"]
ExportFormat = Literal["png", "jpeg", "webp"]


class SelectedBoardVersion(CanvasWireModel):
    board_id: Identifier
    version_id: Identifier
    composed_asset_id: Identifier
    order: int = Field(ge=0, le=49)


class CanvasExportCreate(CanvasWireModel):
    project_revision: int = Field(strict=True, ge=1)
    mode: ExportMode
    format: ExportFormat
    selected_boards: list[SelectedBoardVersion] = Field(min_length=1, max_length=50)
    jpeg_background: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")

    @model_validator(mode="after")
    def validate_export_shape(self) -> "CanvasExportCreate":
        if self.format == "jpeg" and self.jpeg_background is None:
            raise ValueError("JPEG exports require jpegBackground")
        if self.format != "jpeg" and self.jpeg_background is not None:
            raise ValueError("jpegBackground is only valid for JPEG exports")
        if self.mode == "single" and len(self.selected_boards) != 1:
            raise ValueError("single export requires one selected board")
        bindings = [
            (item.board_id, item.version_id, item.composed_asset_id)
            for item in self.selected_boards
        ]
        if len(bindings) != len(set(bindings)):
            raise ValueError("selected board versions must be unique")
        orders = [item.order for item in self.selected_boards]
        if sorted(orders) != list(range(len(orders))):
            raise ValueError("selected board order must be contiguous and unique")
        return self


class ExportSelectionSnapshot(CompositionWireModel):
    board_id: Identifier
    version_id: Identifier
    composed_asset_id: Identifier
    composed_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_type: Literal["main", "sku", "detail"]
    sku_id: Identifier | None = None
    sku_name: str | None = Field(default=None, max_length=200)
    order: int = Field(ge=0, le=49)
    authoritative_render: ComposeRequestSnapshot


class ExportRequestSnapshot(CompositionWireModel):
    schema_version: Literal[1]
    project_id: Identifier
    project_name: str = Field(min_length=1, max_length=200)
    project_revision: int = Field(ge=1)
    mode: ExportMode
    format: ExportFormat
    jpeg_background: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    selected_boards: list[ExportSelectionSnapshot] = Field(min_length=1, max_length=50)
    processor_version: Literal["canvas-authoritative-export-v1"]

    @model_validator(mode="after")
    def validate_snapshot_shape(self) -> "ExportRequestSnapshot":
        if self.format == "jpeg" and self.jpeg_background is None:
            raise ValueError("JPEG exports require jpegBackground")
        if self.format != "jpeg" and self.jpeg_background is not None:
            raise ValueError("jpegBackground is only valid for JPEG exports")
        if self.mode == "single" and len(self.selected_boards) != 1:
            raise ValueError("single export requires one selected board")
        orders = [selection.order for selection in self.selected_boards]
        if sorted(orders) != list(range(len(orders))):
            raise ValueError("selected board order must be contiguous and unique")
        bindings = [
            (
                selection.board_id,
                selection.version_id,
                selection.composed_asset_id,
            )
            for selection in self.selected_boards
        ]
        if len(bindings) != len(set(bindings)):
            raise ValueError("selected board versions must be unique")
        if self.mode in {"detail_slices_zip", "detail_long"} and any(
            selection.output_type != "detail" for selection in self.selected_boards
        ):
            raise ValueError("detail exports require detail boards only")
        return self


__all__ = [
    "CanvasExportCreate",
    "ExportFormat",
    "ExportMode",
    "ExportRequestSnapshot",
    "ExportSelectionSnapshot",
    "SelectedBoardVersion",
]
