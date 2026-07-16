import {
  Circle,
  FabricImage,
  Line,
  Rect,
  FabricText,
  type FabricObject,
} from "fabric";

import type {
  CanvasNode,
  CanvasProjectState,
  NormalizedPoint,
  OutputType,
  TypedEdge,
} from "../domain/types";
import { parseProjectState } from "../domain/validation";
import { lineTopFromAnchor } from "../domain/text-layout";

export const PRESENTATION_METADATA = "__canvasPresentation";

export type PresentationRole =
  | "node"
  | "edge"
  | "port"
  | "board"
  | "background"
  | "product"
  | "text";

export interface CanvasPresentationMetadata {
  key: string;
  role: PresentationRole;
  domainId: string;
  node?: CanvasNode;
  outputType?: OutputType;
}

interface DescriptorBase {
  key: string;
  role: PresentationRole;
  domainId: string;
  fingerprint: string;
  properties: Record<string, unknown>;
}

export interface SyncPresentationDescriptor extends DescriptorBase {
  kind: "sync";
  create(): FabricObject;
}

export interface ImagePresentationDescriptor extends DescriptorBase {
  kind: "image";
  load(signal: AbortSignal): Promise<FabricObject>;
}

export type PresentationDescriptor =
  | SyncPresentationDescriptor
  | ImagePresentationDescriptor;

export interface PresentationPlan {
  project: CanvasProjectState;
  descriptors: PresentationDescriptor[];
  boardToNodeId: Map<string, string>;
}

type WorkspaceMode = CanvasProjectState["semanticState"]["mode"];

const NODE_FILL: Record<CanvasNode["kind"], string> = {
  product_source: "#fef3c7",
  sku_reference: "#ffedd5",
  auto_cutout: "#ecfccb",
  prompt: "#e0e7ff",
  model_generation: "#dbeafe",
  main_output: "#dcfce7",
  sku_output: "#ccfbf1",
  detail_output: "#cffafe",
  text_layer: "#fae8ff",
  composition_group: "#f3e8ff",
  export: "#f1f5f9",
};

function metadataProperties(
  key: string,
  role: PresentationRole,
  domainId: string,
  extra: Partial<CanvasPresentationMetadata> = {},
): Record<string, unknown> {
  return {
    [PRESENTATION_METADATA]: {
      key,
      role,
      domainId,
      ...extra,
    } satisfies CanvasPresentationMetadata,
  };
}

function applyProperties(
  object: FabricObject,
  properties: Record<string, unknown>,
): FabricObject {
  object.set(properties);
  object.setCoords();
  return object;
}

function pointForNode(
  project: CanvasProjectState,
  nodeId: string,
  index: number,
): NormalizedPoint {
  return (
    project.layoutState.nodePositions[nodeId] ?? {
      x: index * 220,
      y: Math.floor(index / 4) * 140,
    }
  );
}

function nodeLabel(node: CanvasNode): string {
  const detail = node.prompt?.trim();
  return detail === undefined || detail.length === 0
    ? node.kind
    : `${node.kind}: ${detail}`;
}

function nodeDescriptor(
  node: CanvasNode,
  position: NormalizedPoint,
): SyncPresentationDescriptor {
  const key = `node:${node.id}`;
  const lockedSystemNode = node.kind === "product_source" || node.kind === "auto_cutout";
  const properties: Record<string, unknown> = {
    left: position.x,
    top: position.y,
    width: 180,
    height: 96,
    rx: 12,
    ry: 12,
    originX: "center",
    originY: "center",
    fill: NODE_FILL[node.kind],
    stroke: "#334155",
    strokeWidth: 1.5,
    label: nodeLabel(node),
    visible: true,
    selectable: !lockedSystemNode,
    evented: !lockedSystemNode,
    ...metadataProperties(key, "node", node.id, {
      node: structuredClone(node),
      outputType:
        node.kind === "main_output"
          ? "main"
          : node.kind === "sku_output"
            ? "sku"
            : node.kind === "detail_output"
              ? "detail"
              : undefined,
    }),
  };
  return {
    kind: "sync",
    key,
    role: "node",
    domainId: node.id,
    fingerprint: JSON.stringify({ node, position }),
    properties,
    create: () => applyProperties(new Rect(), properties),
  };
}

function edgeDescriptor(
  edge: TypedEdge,
  source: NormalizedPoint,
  target: NormalizedPoint,
  mode: WorkspaceMode,
): SyncPresentationDescriptor {
  const key = `edge:${edge.id}`;
  const visible = mode === "advanced";
  const properties: Record<string, unknown> = {
    x1: source.x,
    y1: source.y,
    x2: target.x,
    y2: target.y,
    stroke: "#64748b",
    strokeWidth: 2,
    selectable: false,
    evented: false,
    visible,
    ...metadataProperties(key, "edge", edge.id),
  };
  return {
    kind: "sync",
    key,
    role: "edge",
    domainId: edge.id,
    fingerprint: JSON.stringify({ edge, source, target, visible }),
    properties,
    create: () =>
      applyProperties(
        new Line([source.x, source.y, target.x, target.y]),
        properties,
      ),
  };
}

function portDescriptor(
  edge: TypedEdge,
  end: "source" | "target",
  position: NormalizedPoint,
  mode: WorkspaceMode,
): SyncPresentationDescriptor {
  const nodeId = end === "source" ? edge.sourceNodeId : edge.targetNodeId;
  const port = end === "source" ? edge.sourcePort : edge.targetPort;
  const key = `port:${edge.id}:${end}`;
  const visible = mode === "advanced";
  const properties: Record<string, unknown> = {
    left: position.x,
    top: position.y,
    radius: 6,
    originX: "center",
    originY: "center",
    fill: end === "source" ? "#2563eb" : "#7c3aed",
    stroke: "#ffffff",
    strokeWidth: 1,
    selectable: false,
    evented: false,
    visible,
    ...metadataProperties(key, "port", `${nodeId}:${port}`),
  };
  return {
    kind: "sync",
    key,
    role: "port",
    domainId: `${nodeId}:${port}`,
    fingerprint: JSON.stringify({ edgeId: edge.id, end, position, visible }),
    properties,
    create: () => applyProperties(new Circle(), properties),
  };
}

function productDescriptor(
  project: CanvasProjectState,
  layer: CanvasProjectState["layoutState"]["productLayers"][number],
): ImagePresentationDescriptor {
  const transform = project.layoutState.objectTransforms[layer.transformId];
  if (transform === undefined) {
    throw new Error(`missing validated transform ${layer.transformId}`);
  }
  const key = `product:${layer.id}`;
  const properties: Record<string, unknown> = {
    left: transform.x,
    top: transform.y,
    scaleX: transform.scale,
    scaleY: transform.scale,
    angle: transform.rotation,
    cropX: 0,
    cropY: 0,
    skewX: 0,
    skewY: 0,
    flipX: false,
    flipY: false,
    filters: [],
    opacity: 1,
    globalCompositeOperation: "source-over",
    originX: "center",
    originY: "center",
    selectable: !layer.locked,
    evented: !layer.locked,
    visible: true,
    ...metadataProperties(key, "product", layer.id),
  };
  return {
    kind: "image",
    key,
    role: "product",
    domainId: layer.id,
    fingerprint: JSON.stringify({ layer, transform }),
    properties,
    load: async (signal) => {
      const image = await FabricImage.fromURL(
        `/api/canvas/assets/${encodeURIComponent(layer.renderAssetId)}/content?variant=preview`,
        { crossOrigin: "anonymous", signal },
      );
      return applyProperties(image, properties);
    },
  };
}

function backgroundPreviewDescriptor(assetId: string): ImagePresentationDescriptor {
  const key = "background:selected-result-preview";
  const properties: Record<string, unknown> = {
    left: 0,
    top: 0,
    originX: "left",
    originY: "top",
    selectable: false,
    evented: false,
    visible: true,
    ...metadataProperties(key, "background", assetId),
  };
  return {
    kind: "image",
    key,
    role: "background",
    domainId: assetId,
    fingerprint: JSON.stringify({ assetId }),
    properties,
    load: async (signal) => {
      const image = await FabricImage.fromURL(
        `/api/canvas/assets/${encodeURIComponent(assetId)}/content?variant=preview`,
        { crossOrigin: "anonymous", signal },
      );
      return applyProperties(image, properties);
    },
  };
}

function lineAnchorX(
  x: number,
  width: number,
  boxWidth: number,
  align: "left" | "center" | "right",
): number {
  const frameWidth = width > 0 ? width : boxWidth;
  if (align === "center") return x + frameWidth / 2;
  if (align === "right") return x + frameWidth;
  return x;
}

function textDescriptors(
  snapshot: CanvasProjectState["layoutState"]["textSnapshots"][number],
): SyncPresentationDescriptor[] {
  return snapshot.lines.map((line, lineIndex) => {
    const key = `text:${snapshot.id}:line:${lineIndex}`;
    const lineFrameWidth = line.width > 0 ? line.width : snapshot.boxWidth;
    const properties: Record<string, unknown> = {
      text: line.text,
      left: lineAnchorX(line.x, line.width, snapshot.boxWidth, snapshot.align),
      top: lineTopFromAnchor(line.y, snapshot.fontSize, snapshot.baseline),
      lineFrameLeft: line.x,
      lineFrameWidth,
      fontFamily: snapshot.fontFamily,
      fontSize: snapshot.fontSize,
      charSpacing: snapshot.fontSize === 0
        ? 0
        : snapshot.letterSpacing * 1000 / snapshot.fontSize,
      letterSpacingPixels: snapshot.letterSpacing,
      lineHeight: snapshot.lineHeight,
      textAlign: snapshot.align,
      originX: snapshot.align,
      originY: "top",
      fill: snapshot.color,
      visible: true,
      selectable: false,
      evented: false,
      ...metadataProperties(key, "text", snapshot.id),
    };
    return {
      kind: "sync",
      key,
      role: "text",
      domainId: snapshot.id,
      fingerprint: JSON.stringify({ snapshot, line, lineIndex }),
      properties,
      create: () => applyProperties(new FabricText(line.text), properties),
    };
  });
}

export function createPresentationPlan(
  domainState: CanvasProjectState,
  mode: WorkspaceMode = domainState.semanticState.mode,
  selectedBackgroundPreviewAssetId: string | null = null,
): PresentationPlan {
  const project = parseProjectState(domainState);
  const nodePositions = new Map<string, NormalizedPoint>();
  project.semanticState.nodes.forEach((node, index) => {
    nodePositions.set(node.id, pointForNode(project, node.id, index));
  });

  const descriptors: PresentationDescriptor[] = selectedBackgroundPreviewAssetId === null
    ? []
    : [backgroundPreviewDescriptor(selectedBackgroundPreviewAssetId)];
  descriptors.push(...project.semanticState.nodes.map(
    (node, index) =>
      nodeDescriptor(node, nodePositions.get(node.id) ?? pointForNode(project, node.id, index)),
  ));
  for (const edge of project.semanticState.edges) {
    const source = nodePositions.get(edge.sourceNodeId);
    const target = nodePositions.get(edge.targetNodeId);
    if (source === undefined || target === undefined) {
      throw new Error(`validated edge ${edge.id} has no presentation endpoint`);
    }
    descriptors.push(
      edgeDescriptor(edge, source, target, mode),
      portDescriptor(edge, "source", source, mode),
      portDescriptor(edge, "target", target, mode),
    );
  }
  const orderedText = [...project.layoutState.textSnapshots].sort(
    (left, right) => left.sortOrder - right.sortOrder || left.id.localeCompare(right.id),
  );
  descriptors.push(
    ...orderedText
      .filter((snapshot) => snapshot.zBand === "below-product")
      .flatMap(textDescriptors),
    ...project.layoutState.productLayers.map((layer) => productDescriptor(project, layer)),
    ...orderedText
      .filter((snapshot) => snapshot.zBand === "above-product")
      .flatMap(textDescriptors),
  );

  return {
    project,
    descriptors,
    boardToNodeId: new Map(
      project.semanticState.outputBoards.map((board) => [
        board.id,
        board.outputNodeId,
      ]),
    ),
  };
}
