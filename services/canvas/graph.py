"""Canonical server-side validation for persisted Canvas graph topology."""
from __future__ import annotations

from dataclasses import dataclass

from services.canvas.schemas import CanvasSemanticState


class CanvasGraphValidationError(ValueError):
    """Raised when canvas graph topology cannot be persisted safely."""


@dataclass(frozen=True)
class EdgeRule:
    source_kinds: frozenset[str]
    target_kinds: frozenset[str]
    source_port: str
    target_port: str
    singleton_target_port: bool


OUTPUT_NODE_KIND_BY_TYPE = {
    "main": "main_output",
    "sku": "sku_output",
    "detail": "detail_output",
}
OUTPUT_NODE_KINDS = frozenset(OUTPUT_NODE_KIND_BY_TYPE.values())

# This mirrors the persisted graph contract, not the browser implementation.
# ``background_image`` intentionally has no valid source: the frontend exposes
# its wire type for compatibility but does not permit it to be connected.
EDGE_RULES: dict[str, EdgeRule] = {
    "product_asset": EdgeRule(
        source_kinds=frozenset({"product_source", "sku_reference"}),
        target_kinds=frozenset({"auto_cutout"}),
        source_port="product",
        target_port="reference",
        singleton_target_port=True,
    ),
    "cutout_asset": EdgeRule(
        source_kinds=frozenset({"auto_cutout"}),
        target_kinds=frozenset({"model_generation"}),
        source_port="cutout",
        target_port="reference",
        singleton_target_port=True,
    ),
    "prompt": EdgeRule(
        source_kinds=frozenset({"prompt"}),
        target_kinds=frozenset({"model_generation"}),
        source_port="prompt",
        target_port="prompt",
        singleton_target_port=True,
    ),
    "background_image": EdgeRule(
        source_kinds=frozenset(),
        target_kinds=OUTPUT_NODE_KINDS,
        source_port="image",
        target_port="background",
        singleton_target_port=True,
    ),
    "composition": EdgeRule(
        source_kinds=frozenset({"composition_group"}),
        target_kinds=OUTPUT_NODE_KINDS,
        source_port="composition",
        target_port="composition",
        singleton_target_port=True,
    ),
    "text_layer": EdgeRule(
        source_kinds=frozenset({"text_layer"}),
        target_kinds=OUTPUT_NODE_KINDS,
        source_port="text",
        target_port="text",
        singleton_target_port=False,
    ),
    "output_image": EdgeRule(
        source_kinds=frozenset({"model_generation"}),
        target_kinds=OUTPUT_NODE_KINDS,
        source_port="output",
        target_port="input",
        singleton_target_port=True,
    ),
}


def _require_unique(values: list[str], label: str) -> None:
    if len(values) != len(set(values)):
        raise CanvasGraphValidationError(f"canvas {label} identifiers must be unique")


def _validate_output_boards(semantic_state: CanvasSemanticState, nodes_by_id: dict[str, object]) -> None:
    boards_by_id = {board.id: board for board in semantic_state.output_boards}
    bound_node_ids: set[str] = set()
    for board in semantic_state.output_boards:
        node = nodes_by_id.get(board.output_node_id)
        expected_kind = OUTPUT_NODE_KIND_BY_TYPE[board.output_type]
        if node is None or node.kind != expected_kind:
            raise CanvasGraphValidationError("output board must reference its matching output node")
        if board.output_node_id in bound_node_ids:
            raise CanvasGraphValidationError("output node cannot be bound to multiple boards")
        bound_node_ids.add(board.output_node_id)
        if node.output_board_id != board.id:
            raise CanvasGraphValidationError("output board and output node bindings must be reciprocal")
        if node.sku_id is not None and node.sku_id != board.sku_id:
            raise CanvasGraphValidationError("output board and output node SKU bindings must match")
        if (board.output_type == "sku") != (board.sku_id is not None):
            raise CanvasGraphValidationError("output board type and SKU binding are inconsistent")

    for node in nodes_by_id.values():
        if node.kind not in OUTPUT_NODE_KINDS or node.output_board_id is None:
            continue
        board = boards_by_id.get(node.output_board_id)
        if board is None or board.output_node_id != node.id:
            raise CanvasGraphValidationError("output node must reference its reciprocal board")


def validate_canvas_graph(semantic_state: CanvasSemanticState) -> None:
    """Validate canonical graph edges and output-board bindings before persistence."""

    _require_unique([node.id for node in semantic_state.nodes], "node")
    _require_unique([edge.id for edge in semantic_state.edges], "edge")
    _require_unique([board.id for board in semantic_state.output_boards], "output board")

    nodes_by_id = {node.id: node for node in semantic_state.nodes}
    singleton_inputs: set[tuple[str, str]] = set()
    for edge in semantic_state.edges:
        source = nodes_by_id.get(edge.source_node_id)
        target = nodes_by_id.get(edge.target_node_id)
        if source is None or target is None:
            raise CanvasGraphValidationError("canvas edge endpoints must exist")
        rule = EDGE_RULES[edge.kind]
        if (
            source.kind not in rule.source_kinds
            or target.kind not in rule.target_kinds
            or edge.source_port != rule.source_port
            or edge.target_port != rule.target_port
        ):
            raise CanvasGraphValidationError("canvas edge does not match its canonical connection rule")
        if rule.singleton_target_port:
            key = (edge.target_node_id, edge.target_port)
            if key in singleton_inputs:
                raise CanvasGraphValidationError("canvas target port accepts only one input")
            singleton_inputs.add(key)

    _validate_output_boards(semantic_state, nodes_by_id)
