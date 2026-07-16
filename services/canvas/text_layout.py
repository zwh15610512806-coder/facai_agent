"""Render only persisted explicit text lines with the pinned Canvas font."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from dataclasses import dataclass, field

from PIL import Image, ImageDraw, ImageFont

from services.canvas.font_resource import (
    BUILT_FONT_PATH,
    FONT_FAMILY,
    FONT_RESOURCE_VERSION,
    verify_font_resource,
)
from services.canvas.schemas import TextSnapshot


_ALIGN_ANCHORS = {"left": "l", "center": "m", "right": "r"}
_BASELINE_TOP_EM = {
    "top": 0.0,
    "middle": -0.5,
    "bottom": -1.0,
    "alphabetic": -0.8,
}


class CanvasTextLayoutError(ValueError):
    """Raised when a persisted text metric cannot be rendered exactly."""


@dataclass(frozen=True)
class PairAwareTextMetrics:
    """Fabric-compatible total advance and per-character drawing starts."""

    total_advance: float
    character_starts: tuple[float, ...]


def pair_aware_text_metrics(
    text: str,
    *,
    measure_text: Callable[[str], float],
    letter_spacing: float,
) -> PairAwareTextMetrics:
    """Measure text with Fabric's adjacent-pair kerning and pixel spacing."""

    if not text:
        return PairAwareTextMetrics(total_advance=0.0, character_starts=())

    characters = tuple(text)
    widths = tuple(float(measure_text(character)) for character in characters)
    kerned_advances = [widths[0]]
    character_starts = [0.0]
    for index in range(1, len(characters)):
        pair_width = float(measure_text(characters[index - 1] + characters[index]))
        kerned_advances.append(pair_width - widths[index - 1])
        character_starts.append(
            character_starts[-1] + pair_width - widths[index] + letter_spacing
        )
    total_advance = max(
        0.0,
        sum(kerned_advances) + letter_spacing * max(0, len(characters) - 1),
    )
    return PairAwareTextMetrics(
        total_advance=total_advance,
        character_starts=tuple(character_starts),
    )


def line_top_from_anchor(
    y: float,
    *,
    font_size: int,
    baseline: str,
) -> float:
    """Map the persisted logical-em baseline anchor to a shared top coordinate."""

    if type(font_size) is not int or font_size <= 0 or baseline not in _BASELINE_TOP_EM:
        raise CanvasTextLayoutError("Canvas text layer uses unsupported baseline metrics")
    return y + font_size * _BASELINE_TOP_EM[baseline]


@dataclass
class RequestFontProvider:
    """One verified font resource and integer-size cache scoped to one composition."""

    font_path: Path = BUILT_FONT_PATH
    expected_font_version: str = FONT_RESOURCE_VERSION
    _verified_path: Path = field(init=False)
    _fonts: dict[int, ImageFont.FreeTypeFont] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self._verified_path = verify_font_resource(
            self.font_path,
            self.expected_font_version,
        )

    def get(self, font_size: int) -> ImageFont.FreeTypeFont:
        if type(font_size) is not int or font_size <= 0:
            raise CanvasTextLayoutError("Canvas font size must be a positive integer")
        cached = self._fonts.get(font_size)
        if cached is not None:
            return cached
        try:
            loaded = ImageFont.truetype(str(self._verified_path), size=font_size)
        except (OSError, ValueError) as exc:
            raise CanvasTextLayoutError("Canvas font resource could not be loaded") from exc
        self._fonts[font_size] = loaded
        return loaded


def _line_anchor_x(*, x: float, width: float, box_width: float, align: str) -> float:
    """Treat x as the line-frame left; zero width explicitly inherits boxWidth."""

    frame_width = width if width > 0 else box_width
    if align == "center":
        return x + frame_width / 2
    if align == "right":
        return x + frame_width
    return x


def _draw_spaced_text(
    draw: ImageDraw.ImageDraw,
    *,
    position: tuple[float, float],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: str,
    align: str,
    letter_spacing: float,
) -> None:
    anchor = _ALIGN_ANCHORS[align] + "t"
    if not text or letter_spacing == 0:
        draw.text(position, text, font=font, fill=fill, anchor=anchor)
        return
    metrics = pair_aware_text_metrics(
        text,
        measure_text=lambda value: float(draw.textlength(value, font=font)),
        letter_spacing=letter_spacing,
    )
    x, y = position
    if align == "center":
        x -= metrics.total_advance / 2
    elif align == "right":
        x -= metrics.total_advance
    character_anchor = "lt"
    for character, character_start in zip(text, metrics.character_starts, strict=True):
        draw.text(
            (x + character_start, y),
            character,
            font=font,
            fill=fill,
            anchor=character_anchor,
        )


def render_text_lines(
    target: Image.Image,
    *,
    layer: TextSnapshot,
    font_path: Path = BUILT_FONT_PATH,
    expected_font_version: str = FONT_RESOURCE_VERSION,
    font_provider: RequestFontProvider | None = None,
) -> None:
    """Draw saved lines at saved coordinates; content is never reflowed or wrapped."""

    if layer.font_asset_id is not None or layer.font_family != FONT_FAMILY:
        raise CanvasTextLayoutError("Canvas text layer uses an unsupported font")
    if layer.font_version != expected_font_version:
        raise CanvasTextLayoutError("Canvas text layer font version does not match")
    if layer.align not in _ALIGN_ANCHORS or layer.baseline not in _BASELINE_TOP_EM:
        raise CanvasTextLayoutError("Canvas text layer uses unsupported metrics")
    provider = font_provider or RequestFontProvider(font_path, expected_font_version)
    font = provider.get(layer.font_size)
    draw = ImageDraw.Draw(target)
    for line in layer.lines:
        _draw_spaced_text(
            draw,
            position=(
                _line_anchor_x(
                    x=line.x,
                    width=line.width,
                    box_width=layer.box_width,
                    align=layer.align,
                ),
                line_top_from_anchor(
                    line.y,
                    font_size=layer.font_size,
                    baseline=layer.baseline,
                ),
            ),
            text=line.text,
            font=font,
            fill=layer.color,
            align=layer.align,
            letter_spacing=layer.letter_spacing,
        )


__all__ = [
    "CanvasTextLayoutError",
    "PairAwareTextMetrics",
    "RequestFontProvider",
    "line_top_from_anchor",
    "pair_aware_text_metrics",
    "render_text_lines",
]
