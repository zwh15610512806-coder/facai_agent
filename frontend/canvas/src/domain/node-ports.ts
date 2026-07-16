import type { CanvasNode, TypedEdge } from "./types";

export type NodeKind = CanvasNode["kind"];
export type CanvasPort = TypedEdge["sourcePort"] | TypedEdge["targetPort"];

const PORTS: Record<NodeKind, readonly CanvasPort[]> = {
  product_source: ["product"],
  sku_reference: ["product"],
  auto_cutout: ["reference", "cutout"],
  prompt: ["prompt"],
  model_generation: ["reference", "prompt", "output"],
  main_output: ["background", "composition", "text", "input"],
  sku_output: ["background", "composition", "text", "input"],
  detail_output: ["background", "composition", "text", "input"],
  text_layer: ["text"],
  composition_group: ["composition"],
  export: ["input"],
};

const OUTPUT_KINDS = new Set<NodeKind>(["main_output", "sku_output", "detail_output"]);
const EDGE_KINDS: TypedEdge["kind"][] = [
  "product_asset", "cutout_asset", "prompt",
  "composition", "text_layer", "output_image",
];

export function nodePorts(kind: NodeKind): readonly CanvasPort[] {
  return PORTS[kind];
}

export function canConnectNodes(
  source: NodeKind,
  target: NodeKind,
  edgeKind: TypedEdge["kind"],
): boolean {
  switch (edgeKind) {
    case "product_asset":
      return (source === "product_source" || source === "sku_reference") &&
        target === "auto_cutout";
    case "cutout_asset":
      return source === "auto_cutout" && target === "model_generation";
    case "prompt":
      return source === "prompt" && target === "model_generation";
    case "background_image":
      return false;
    case "composition":
      return source === "composition_group" && OUTPUT_KINDS.has(target);
    case "text_layer":
      return source === "text_layer" && OUTPUT_KINDS.has(target);
    case "output_image":
      return source === "model_generation" && OUTPUT_KINDS.has(target);
  }
}

export function compatibleEdgeKinds(
  source: NodeKind,
  target: NodeKind,
): TypedEdge["kind"][] {
  return EDGE_KINDS.filter((kind) => canConnectNodes(source, target, kind));
}

export function typedEdgePorts(kind: TypedEdge["kind"]): Pick<TypedEdge, "sourcePort" | "targetPort"> {
  switch (kind) {
    case "product_asset": return { sourcePort: "product", targetPort: "reference" };
    case "cutout_asset": return { sourcePort: "cutout", targetPort: "reference" };
    case "prompt": return { sourcePort: "prompt", targetPort: "prompt" };
    case "background_image": return { sourcePort: "image", targetPort: "background" };
    case "composition": return { sourcePort: "composition", targetPort: "composition" };
    case "text_layer": return { sourcePort: "text", targetPort: "text" };
    case "output_image": return { sourcePort: "output", targetPort: "input" };
  }
}

export function createTypedEdge(
  id: string,
  kind: TypedEdge["kind"],
  sourceNodeId: string,
  targetNodeId: string,
): TypedEdge {
  const base = { id, sourceNodeId, targetNodeId, skuId: null };
  switch (kind) {
    case "product_asset": return { ...base, kind, sourcePort: "product", targetPort: "reference" };
    case "cutout_asset": return { ...base, kind, sourcePort: "cutout", targetPort: "reference" };
    case "prompt": return { ...base, kind, sourcePort: "prompt", targetPort: "prompt" };
    case "background_image": return { ...base, kind, sourcePort: "image", targetPort: "background" };
    case "composition": return { ...base, kind, sourcePort: "composition", targetPort: "composition" };
    case "text_layer": return { ...base, kind, sourcePort: "text", targetPort: "text" };
    case "output_image": return { ...base, kind, sourcePort: "output", targetPort: "input" };
  }
}
