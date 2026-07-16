export type JsonValue =
  | null
  | boolean
  | number
  | string
  | JsonValue[]
  | { [key: string]: JsonValue };

export type NodeId = string;
export type EdgeId = string;
export type SkuId = string;
export type AssetId = string;
export type ModelProfileId = string;
export type OutputBoardId = string;
export type CompositionGroupId = string;
export type ProductLayerId = string;
export type TextLayerId = string;
export type TextSnapshotId = string;
export type TaskId = string;

export type OutputType = "main" | "sku" | "detail";
export type ManagedBy = "complete-set";
export type NodeKind =
  | "product_source"
  | "sku_reference"
  | "auto_cutout"
  | "prompt"
  | "model_generation"
  | "main_output"
  | "sku_output"
  | "detail_output"
  | "text_layer"
  | "composition_group"
  | "export";

export interface CanvasNodeBase {
  id: NodeId;
  managedBy: ManagedBy | null;
  skuId: SkuId | null;
  assetId: AssetId | null;
  modelProfileId: ModelProfileId | null;
  prompt: string | null;
  compositionGroupId: CompositionGroupId | null;
  textSnapshotId: TextSnapshotId | null;
  outputBoardId: OutputBoardId | null;
  parameters: { [key: string]: JsonValue };
}

export type CanvasNode = {
  [Kind in NodeKind]: CanvasNodeBase & { kind: Kind };
}[NodeKind];

interface CanvasEdgeBase {
  id: EdgeId;
  sourceNodeId: NodeId;
  targetNodeId: NodeId;
  skuId: SkuId | null;
}

export interface ProductAssetEdge extends CanvasEdgeBase {
  kind: "product_asset";
  sourcePort: "product";
  targetPort: "reference";
}

export interface CutoutAssetEdge extends CanvasEdgeBase {
  kind: "cutout_asset";
  sourcePort: "cutout";
  targetPort: "reference";
}

export interface PromptEdge extends CanvasEdgeBase {
  kind: "prompt";
  sourcePort: "prompt";
  targetPort: "prompt";
}

export interface BackgroundImageEdge extends CanvasEdgeBase {
  kind: "background_image";
  sourcePort: "image";
  targetPort: "background";
}

export interface CompositionEdge extends CanvasEdgeBase {
  kind: "composition";
  sourcePort: "composition";
  targetPort: "composition";
}

export interface TextLayerEdge extends CanvasEdgeBase {
  kind: "text_layer";
  sourcePort: "text";
  targetPort: "text";
}

export interface OutputImageEdge extends CanvasEdgeBase {
  kind: "output_image";
  sourcePort: "output";
  targetPort: "input";
}

export type TypedEdge =
  | ProductAssetEdge
  | CutoutAssetEdge
  | PromptEdge
  | BackgroundImageEdge
  | CompositionEdge
  | TextLayerEdge
  | OutputImageEdge;

export interface OutputBoard {
  id: OutputBoardId;
  outputNodeId: NodeId;
  outputType: OutputType;
  skuId: SkuId | null;
  sortOrder: number;
  selectedResultAssetId: AssetId | null;
}

export interface CompleteSetOutput {
  outputType: OutputType;
  skuId: SkuId | null;
  quantity: number | null;
  aspectRatio: string | null;
  width: number | null;
  height: number | null;
  prompt: string;
  modelProfileId: ModelProfileId | null;
  modelParameters: { [key: string]: JsonValue };
  referenceAssetId: AssetId | null;
  compositionGroupId: CompositionGroupId | null;
}

export interface CompleteSetSettings {
  selectedOutputTypes: OutputType[];
  outputs: CompleteSetOutput[];
}

export interface NormalizedSlot extends NormalizedPoint {
  width: number;
  height: number;
}

export interface NormalizedAnchor extends NormalizedPoint {}

export interface SafeArea {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

export interface CompositionLayout {
  slot: NormalizedSlot;
  anchor: NormalizedAnchor;
  baseline: number;
  relativeProductFraction: number;
  contain: true;
  safeArea: SafeArea;
  rotation: number;
}

export interface CompositionGroup {
  id: CompositionGroupId;
  skuIds: SkuId[];
  productLayerIds: ProductLayerId[];
  layoutHash: string;
  layout: CompositionLayout;
}

export interface CanvasSemanticState {
  nodes: CanvasNode[];
  edges: TypedEdge[];
  outputBoards: OutputBoard[];
  mode: "complete-set" | "advanced";
  advancedCustomized: boolean;
  completeSet: CompleteSetSettings;
  compositionGroups: CompositionGroup[];
}

export interface NormalizedPoint {
  x: number;
  y: number;
}

export interface NormalizedTransform extends NormalizedPoint {
  scale: number;
  rotation: number;
}

export interface CanvasViewport extends NormalizedPoint {
  zoom: number;
}

export interface ProductLayer {
  id: ProductLayerId;
  sourceAssetId: AssetId;
  renderAssetId: AssetId;
  allowOpaqueFallback: boolean;
  skuId: SkuId | null;
  compositionGroupId: CompositionGroupId | null;
  transformId: string;
  locked: boolean;
}

export interface TextLineSnapshot extends NormalizedPoint {
  text: string;
  width: number;
}

export interface TextSnapshot {
  id: TextSnapshotId;
  nodeId: NodeId;
  content: string;
  fontAssetId: null;
  fontFamily: "Noto Sans CJK SC";
  fontVersion: "sha256:2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b";
  boxWidth: number;
  lines: TextLineSnapshot[];
  fontSize: number;
  color: string;
  letterSpacing: number;
  lineHeight: number;
  align: "left" | "center" | "right";
  baseline: "alphabetic" | "top" | "middle" | "bottom";
  zBand: "below-product" | "above-product";
  sortOrder: number;
}

export interface CanvasLayoutState {
  nodePositions: Record<NodeId, NormalizedPoint>;
  objectTransforms: Record<string, NormalizedTransform>;
  viewport: CanvasViewport;
  productLayers: ProductLayer[];
  textSnapshots: TextSnapshot[];
}

export interface CanvasProjectState {
  schemaVersion: 1;
  semanticState: CanvasSemanticState;
  layoutState: CanvasLayoutState;
}

export interface GenerationResultSnapshot {
  id: string;
  taskId: TaskId;
  boardId: OutputBoardId | null;
  assetId: AssetId;
}

export interface TaskSnapshot {
  id: TaskId;
  boardId: OutputBoardId | null;
  status: "queued" | "running" | "succeeded" | "failed" | "canceled" | "unknown";
  results: GenerationResultSnapshot[];
}

export interface UnlinkedBoardSnapshot {
  boardId: OutputBoardId;
  selectedResultAssetId: AssetId | null;
  taskIds: TaskId[];
  resultIds: string[];
}

export interface ProjectIdentity {
  projectId: string;
  revision: number;
}

export interface PendingConfirmation {
  token: string;
  actionIdentity: string;
  baseStateFingerprint: string;
  diffIdentity: string;
  projectId: string;
  revision: number;
  diff: ProjectDiff;
}

export interface ProjectRuntimeState {
  projectId: string;
  revision: number;
  selectedNodeId: NodeId | null;
  selectedBoardId: OutputBoardId | null;
  taskSnapshots: Record<TaskId, TaskSnapshot>;
  resultHistory: GenerationResultSnapshot[];
  allowedResultAssetIds: Record<OutputBoardId, AssetId[]>;
  unlinkedBoards: UnlinkedBoardSnapshot[];
  uploadIds: string[];
  paidGenerationRequestIds: string[];
  pendingConfirmation: PendingConfirmation | null;
}

export interface ProjectDiff {
  id: string;
  actionType:
    | "output/disable"
    | "output/setQuantity"
    | "sku/setOutputQuantity"
    | "completeSet/rebuild";
  removedNodeIds: NodeId[];
  removedEdgeIds: EdgeId[];
  removedBoardIds: OutputBoardId[];
  addedNodeIds: NodeId[];
  addedEdgeIds: EdgeId[];
  addedBoardIds: OutputBoardId[];
  selectedResultAssetIds: AssetId[];
  taskIds: TaskId[];
  historyResultIds: string[];
  preservedCustomNodeIds: NodeId[];
}

export interface ConfirmationRequest {
  token: string;
  diff: ProjectDiff;
}

export interface CanvasNodePatch {
  prompt?: string | null;
  modelProfileId?: ModelProfileId | null;
  parameters?: { [key: string]: JsonValue };
  assetId?: AssetId | null;
  skuId?: SkuId | null;
  compositionGroupId?: CompositionGroupId | null;
}

export type TextLayerPatch = Partial<
  Pick<
    TextSnapshot,
    | "content"
    | "boxWidth"
    | "lines"
    | "fontSize"
    | "color"
    | "letterSpacing"
    | "lineHeight"
    | "align"
    | "baseline"
    | "zBand"
    | "sortOrder"
  >
>;

export type ProjectAction =
  | { type: "output/enable"; outputType: OutputType }
  | {
      type: "output/disable";
      outputType: OutputType;
      acceptedDiffId?: string;
    }
  | {
      type: "output/setQuantity";
      outputType: Exclude<OutputType, "sku">;
      quantity: number | null;
      acceptedDiffId?: string;
    }
  | {
      type: "sku/setOutputQuantity";
      skuId: SkuId;
      quantity: number | null;
      acceptedDiffId?: string;
    }
  | {
      type: "output/configure";
      outputType: OutputType;
      skuId: SkuId | null;
      patch: Partial<Pick<
        CompleteSetOutput,
        | "prompt"
        | "modelProfileId"
        | "modelParameters"
        | "referenceAssetId"
        | "compositionGroupId"
        | "aspectRatio"
        | "width"
        | "height"
      >>;
    }
  | {
      type: "board/selectResult";
      boardId: OutputBoardId;
      assetId: AssetId | null;
    }
  | { type: "task/statusReceived"; task: TaskSnapshot }
  | { type: "runtime/setAllowedResultAssets"; boardId: OutputBoardId; assetIds: AssetId[] }
  | { type: "asset/useRectangularSource"; workingAssetId: AssetId }
  | { type: "mode/set"; mode: "complete-set" | "advanced" }
  | { type: "viewport/set"; viewport: CanvasViewport }
  | { type: "node/add"; node: CanvasNode }
  | { type: "node/update"; nodeId: NodeId; patch: CanvasNodePatch }
  | { type: "node/move"; nodeId: NodeId; position: NormalizedPoint }
  | { type: "edge/connect"; edge: TypedEdge }
  | { type: "text/update"; layerId: TextLayerId; patch: TextLayerPatch }
  | {
      type: "composition/update";
      groupId: CompositionGroupId;
      layout: CompositionLayout;
    }
  | {
      type: "composition/create";
      skuProducts: Array<Pick<ProductLayer, "skuId" | "sourceAssetId" | "renderAssetId" | "allowOpaqueFallback">>;
    }
  | { type: "runtime/select"; nodeId: NodeId | null; boardId: OutputBoardId | null }
  | { type: "upload/record"; uploadId: string }
  | { type: "generation/paidRequested"; requestId: string }
  | { type: "completeSet/rebuild"; acceptedDiffId?: string };

export interface DispatchResult {
  applied: boolean;
  confirmation?: ConfirmationRequest;
}

export function createEmptyRuntimeState(
  identity: ProjectIdentity = { projectId: "local-project", revision: 0 },
): ProjectRuntimeState {
  return {
    projectId: identity.projectId,
    revision: identity.revision,
    selectedNodeId: null,
    selectedBoardId: null,
    taskSnapshots: {},
    resultHistory: [],
    allowedResultAssetIds: {},
    unlinkedBoards: [],
    uploadIds: [],
    paidGenerationRequestIds: [],
    pendingConfirmation: null,
  };
}

export function createEmptyProjectState(): CanvasProjectState {
  return {
    schemaVersion: 1,
    semanticState: {
      nodes: [],
      edges: [],
      outputBoards: [],
      mode: "complete-set",
      advancedCustomized: false,
      completeSet: { selectedOutputTypes: [], outputs: [] },
      compositionGroups: [],
    },
    layoutState: {
      nodePositions: {},
      objectTransforms: {},
      viewport: { x: 0, y: 0, zoom: 1 },
      productLayers: [],
      textSnapshots: [],
    },
  };
}
