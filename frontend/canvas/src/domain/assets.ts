import type { ProjectSku } from "../api/client";
import type {
  CanvasNode,
  CanvasProjectState,
  ProductLayer,
} from "./types";

export const CANVAS_MAX_UPLOAD_BYTES = 12 * 1024 * 1024;
export const CANVAS_ACCEPTED_IMAGE_TYPES = [
  "image/jpeg",
  "image/png",
  "image/webp",
] as const;

export type CanvasImageMimeType = (typeof CANVAS_ACCEPTED_IMAGE_TYPES)[number];
export type AssetType =
  | "source"
  | "working"
  | "preview"
  | "cutout"
  | "generated_background"
  | "composed"
  | "export";
export type TransparencyStatus = "unknown" | "opaque" | "transparent";
export type AssetOperationStatus =
  | "cancel_requested"
  | "cancelled"
  | "failed"
  | "interrupted"
  | "queued"
  | "running"
  | "succeeded";

export interface SafeOperationError {
  code: string;
  message: string;
  retryable: boolean;
}

export interface AssetRecord {
  id: string;
  projectId: string;
  assetType: AssetType;
  originalFilename: string;
  mimeType: string;
  byteCount: number;
  width: number;
  height: number;
  sha256: string;
  sourceAssetId: string | null;
  transparencyStatus: TransparencyStatus;
  processorVersion: string | null;
  metadata: Record<string, unknown>;
}

export interface AssetOperation {
  id: string;
  projectId: string;
  operationType: "compose" | "cutout" | "export";
  status: AssetOperationStatus;
  attemptCount: number;
  inputAssetId: string;
  outputAssetId: string | null;
  safeError: SafeOperationError | null;
}

export interface AssetOperationProgress {
  id: string;
  projectId: string;
  operationType: "compose" | "cutout" | "export";
  status: AssetOperationStatus;
  attemptCount?: number;
  inputAssetId?: string;
  outputAssetId?: string | null;
  safeError?: SafeOperationError | null;
}

export interface UploadedAssetBundle {
  source: AssetRecord;
  working: AssetRecord;
  preview: AssetRecord;
  operation: AssetOperation | null;
}

export type CutoutProjectionStatus =
  | "ready"
  | "queued"
  | "running"
  | "failed"
  | "interrupted";

export interface ProjectedAsset {
  projectId: string;
  sourceAssetId: string;
  workingAssetId: string;
  previewAssetId: string;
  renderAssetId: string;
  cutoutAssetId: string | null;
  operationId: string | null;
  cutoutStatus: CutoutProjectionStatus;
  allowOpaqueFallback: boolean;
  error: SafeOperationError | null;
}

export interface ProjectedAssetResult {
  project: CanvasProjectState;
  asset: ProjectedAsset;
}

export type FileValidation =
  | { ok: true }
  | { ok: false; message: string };

const MAIN_PRODUCT_LAYER_ID = "main-product";
const MAIN_PRODUCT_NODE_ID = "main-product-source";
const MAIN_CUTOUT_NODE_ID = "main-product-cutout";
const MAIN_PRODUCT_CUTOUT_EDGE_ID = "main-product-source-cutout";

export function validateAssetFile(
  file: Pick<File, "size" | "type">,
  maxBytes = CANVAS_MAX_UPLOAD_BYTES,
): FileValidation {
  if (!(CANVAS_ACCEPTED_IMAGE_TYPES as readonly string[]).includes(file.type)) {
    return { ok: false, message: "请选择 JPG、PNG 或 WebP 图片" };
  }
  if (file.size > maxBytes) {
    return { ok: false, message: "图片不能超过 12 MB" };
  }
  return { ok: true };
}

export function previewContentUrl(apiBase: string, assetId: string): string {
  const base = apiBase.replace(/\/+$/, "");
  return `${base}/assets/${encodeURIComponent(assetId)}/content?variant=preview`;
}

function node(id: string, kind: CanvasNode["kind"], assetId: string): CanvasNode {
  return {
    id,
    kind,
    managedBy: null,
    skuId: null,
    assetId,
    modelProfileId: null,
    prompt: null,
    compositionGroupId: null,
    textSnapshotId: null,
    outputBoardId: null,
    parameters: {},
  };
}

function replaceNode(project: CanvasProjectState, replacement: CanvasNode): void {
  const index = project.semanticState.nodes.findIndex(
    (candidate) => candidate.id === replacement.id,
  );
  if (index === -1) {
    project.semanticState.nodes.push(replacement);
  } else {
    project.semanticState.nodes[index] = replacement;
  }
}

function ensureMainCutoutRoute(project: CanvasProjectState): void {
  const edge = {
    id: MAIN_PRODUCT_CUTOUT_EDGE_ID,
    kind: "product_asset" as const,
    sourceNodeId: MAIN_PRODUCT_NODE_ID,
    sourcePort: "product" as const,
    targetNodeId: MAIN_CUTOUT_NODE_ID,
    targetPort: "reference" as const,
    skuId: null,
  };
  const index = project.semanticState.edges.findIndex(
    (candidate) => candidate.id === MAIN_PRODUCT_CUTOUT_EDGE_ID,
  );
  if (index === -1) {
    project.semanticState.edges.push(edge);
  } else {
    project.semanticState.edges[index] = edge;
  }
}

function setOpaqueFallback(project: CanvasProjectState, allowed: boolean): void {
  const layer = project.layoutState.productLayers.find(
    (candidate) => candidate.id === MAIN_PRODUCT_LAYER_ID && candidate.skuId === null,
  );
  if (layer === undefined) {
    throw new Error("Canvas main product layer is missing");
  }
  layer.allowOpaqueFallback = allowed;
  if (layer.compositionGroupId !== null) {
    for (const member of project.layoutState.productLayers) {
      if (
        member.compositionGroupId === layer.compositionGroupId &&
        member.sourceAssetId === layer.sourceAssetId &&
        member.renderAssetId === layer.renderAssetId
      ) {
        member.allowOpaqueFallback = allowed;
      }
    }
  }
}

function replaceMainLayer(
  project: CanvasProjectState,
  workingAssetId: string,
  renderAssetId: string,
): void {
  const existing = project.layoutState.productLayers.find(
    (candidate) => candidate.id === MAIN_PRODUCT_LAYER_ID,
  );
  const replacement: ProductLayer = {
    id: MAIN_PRODUCT_LAYER_ID,
    sourceAssetId: workingAssetId,
    renderAssetId,
    allowOpaqueFallback: false,
    skuId: null,
    compositionGroupId: existing?.compositionGroupId ?? null,
    transformId: existing?.transformId ?? MAIN_PRODUCT_LAYER_ID,
    locked: true,
  };
  const index = project.layoutState.productLayers.findIndex(
    (candidate) => candidate.id === MAIN_PRODUCT_LAYER_ID,
  );
  if (index === -1) {
    project.layoutState.productLayers.push(replacement);
  } else {
    project.layoutState.productLayers[index] = replacement;
  }
  if (existing?.compositionGroupId !== null && existing?.compositionGroupId !== undefined) {
    for (const layer of project.layoutState.productLayers) {
      if (
        layer.id !== replacement.id &&
        layer.compositionGroupId === existing.compositionGroupId &&
        layer.sourceAssetId === existing.sourceAssetId
      ) {
        layer.sourceAssetId = workingAssetId;
        layer.renderAssetId = renderAssetId;
        layer.allowOpaqueFallback = false;
      }
    }
  }
  project.layoutState.objectTransforms[MAIN_PRODUCT_LAYER_ID] ??= {
    x: 0.5,
    y: 0.5,
    scale: 1,
    rotation: 0,
  };
}

function requireUploadContract(upload: UploadedAssetBundle): void {
  const projectId = upload.source.projectId;
  if (
    upload.source.assetType !== "source" ||
    upload.working.assetType !== "working" ||
    upload.preview.assetType !== "preview" ||
    upload.working.projectId !== projectId ||
    upload.preview.projectId !== projectId ||
    upload.working.sourceAssetId !== upload.source.id ||
    upload.preview.sourceAssetId !== upload.working.id
  ) {
    throw new Error("Canvas upload response has invalid asset derivation");
  }
  if (
    upload.operation !== null &&
    (upload.operation.projectId !== projectId ||
      upload.operation.operationType !== "cutout" ||
      upload.operation.inputAssetId !== upload.working.id)
  ) {
    throw new Error("Canvas upload response has invalid cutout operation");
  }
}

function initialCutoutStatus(upload: UploadedAssetBundle): CutoutProjectionStatus {
  if (upload.working.transparencyStatus === "transparent") {
    if (upload.operation !== null) {
      throw new Error("Transparent Canvas assets cannot enqueue automatic cutout");
    }
    return "ready";
  }
  if (upload.operation === null) {
    throw new Error("Opaque Canvas assets require an automatic cutout operation");
  }
  return upload.operation.status === "running" ? "running" : "queued";
}

export function projectUploadedAsset(
  current: CanvasProjectState,
  upload: UploadedAssetBundle,
): ProjectedAssetResult {
  requireUploadContract(upload);
  const project = structuredClone(current);
  const cutoutStatus = initialCutoutStatus(upload);
  replaceNode(project, node(MAIN_PRODUCT_NODE_ID, "product_source", upload.working.id));
  replaceNode(project, node(MAIN_CUTOUT_NODE_ID, "auto_cutout", upload.working.id));
  ensureMainCutoutRoute(project);
  replaceMainLayer(project, upload.working.id, upload.working.id);
  return {
    project,
    asset: {
      projectId: upload.source.projectId,
      sourceAssetId: upload.source.id,
      workingAssetId: upload.working.id,
      previewAssetId: upload.preview.id,
      renderAssetId: upload.working.id,
      cutoutAssetId: null,
      operationId: upload.operation?.id ?? null,
      cutoutStatus,
      allowOpaqueFallback: false,
      error: null,
    },
  };
}

function projectedStatus(status: AssetOperationStatus): CutoutProjectionStatus {
  switch (status) {
    case "queued":
    case "cancel_requested":
      return "queued";
    case "running":
      return "running";
    case "failed":
      return "failed";
    case "interrupted":
    case "cancelled":
      return "interrupted";
    case "succeeded":
      return "ready";
  }
}

export function applyCutoutEvent(
  current: ProjectedAssetResult,
  operation: AssetOperationProgress,
): ProjectedAssetResult {
  if (
    operation.id !== current.asset.operationId ||
    operation.projectId !== current.asset.projectId ||
    (operation.inputAssetId !== undefined &&
      operation.inputAssetId !== current.asset.workingAssetId) ||
    operation.operationType !== "cutout"
  ) {
    return current;
  }
  const project = structuredClone(current.project);
  const succeeded = operation.status === "succeeded";
  if (succeeded && operation.outputAssetId === null) {
    throw new Error("Succeeded Canvas cutout has no output asset");
  }
  const shouldSwapToCutout = succeeded && !current.asset.allowOpaqueFallback;
  const renderAssetId = shouldSwapToCutout
    ? operation.outputAssetId as string
    : current.asset.renderAssetId;
  if (shouldSwapToCutout) {
    replaceMainLayer(project, current.asset.workingAssetId, renderAssetId);
    replaceNode(project, node(MAIN_CUTOUT_NODE_ID, "auto_cutout", renderAssetId));
    setOpaqueFallback(project, false);
  }
  return {
    project,
    asset: {
      ...current.asset,
      renderAssetId,
      cutoutAssetId: succeeded
        ? operation.outputAssetId as string
        : current.asset.cutoutAssetId,
      cutoutStatus: projectedStatus(operation.status),
      allowOpaqueFallback: shouldSwapToCutout ? false : current.asset.allowOpaqueFallback,
      error:
        operation.status === "queued" ||
        operation.status === "running" ||
        operation.status === "succeeded"
          ? null
          : operation.safeError ?? current.asset.error,
    },
  };
}

export function hydrateProjectedAsset(
  current: CanvasProjectState,
  assets: readonly AssetRecord[],
  operations: readonly AssetOperation[],
): ProjectedAssetResult | null {
  const layer = current.layoutState.productLayers.find(
    (candidate) => candidate.skuId === null && candidate.locked,
  );
  if (layer === undefined) {
    return null;
  }
  const working = assets.find(
    (asset) => asset.id === layer.sourceAssetId && asset.assetType === "working",
  );
  if (working === undefined || working.sourceAssetId === null) {
    return null;
  }
  const source = assets.find(
    (asset) => asset.id === working.sourceAssetId && asset.assetType === "source",
  );
  const preview = assets.find(
    (asset) => asset.assetType === "preview" && asset.sourceAssetId === working.id,
  );
  if (source === undefined || preview === undefined) {
    return null;
  }
  const operation = [...operations]
    .filter(
      (candidate) =>
        candidate.projectId === working.projectId &&
        candidate.operationType === "cutout" &&
        candidate.inputAssetId === working.id,
    )
    .at(-1) ?? null;
  const rendered = assets.find((asset) => asset.id === layer.renderAssetId);
  const cutoutAssetId = rendered?.assetType === "cutout"
    ? rendered.id
    : operation?.status === "succeeded"
      ? operation.outputAssetId
      : null;
  const cutoutStatus: CutoutProjectionStatus = working.transparencyStatus === "transparent"
    ? "ready"
    : operation === null
      ? cutoutAssetId === null ? "queued" : "ready"
      : projectedStatus(operation.status);
  const allowOpaqueFallback = isOpaqueFallbackAllowed(current);
  const hydrated: ProjectedAssetResult = {
    project: structuredClone(current),
    asset: {
      projectId: working.projectId,
      sourceAssetId: source.id,
      workingAssetId: working.id,
      previewAssetId: preview.id,
      renderAssetId: layer.renderAssetId,
      cutoutAssetId,
      operationId: operation?.id ?? null,
      cutoutStatus,
      allowOpaqueFallback,
      error: operation?.safeError ?? null,
    },
  };
  if (
    operation?.status === "succeeded" &&
    operation.outputAssetId !== null &&
    !allowOpaqueFallback
  ) {
    return applyCutoutEvent(hydrated, operation);
  }
  return hydrated;
}

export function selectRectangularFallback(
  current: ProjectedAssetResult,
): ProjectedAssetResult {
  const project = structuredClone(current.project);
  replaceMainLayer(project, current.asset.workingAssetId, current.asset.workingAssetId);
  replaceNode(project, node(MAIN_CUTOUT_NODE_ID, "auto_cutout", current.asset.workingAssetId));
  setOpaqueFallback(project, true);
  return {
    project,
    asset: {
      ...current.asset,
      renderAssetId: current.asset.workingAssetId,
      allowOpaqueFallback: true,
    },
  };
}

export function isOpaqueFallbackAllowed(project: CanvasProjectState): boolean {
  const layer = project.layoutState.productLayers.find(
    (candidate) => candidate.id === MAIN_PRODUCT_LAYER_ID && candidate.skuId === null,
  );
  return layer?.allowOpaqueFallback === true;
}

export function resolveSkuReferenceAssetId(
  sku: Pick<ProjectSku, "referenceAssetId">,
  project: CanvasProjectState,
):
  | { assetId: string; source: "sku" | "main-product" }
  | { assetId: null; source: "missing" } {
  if (sku.referenceAssetId !== null) {
    return { assetId: sku.referenceAssetId, source: "sku" };
  }
  const main = project.layoutState.productLayers.find(
    (layer) => layer.skuId === null && layer.locked,
  );
  return main === undefined
    ? { assetId: null, source: "missing" }
    : { assetId: main.renderAssetId, source: "main-product" };
}
