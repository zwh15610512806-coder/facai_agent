import type { ModelProfile } from "./providers";
import type {
  CanvasNode,
  CanvasProjectState,
  CompleteSetOutput,
  OutputType,
  TypedEdge,
} from "./types";

export interface CanvasGenerationInput {
  assetId: string;
  inputRole: "product" | "reference";
  ordinal: number;
}

export interface CanvasGenerationItem {
  outputType: OutputType;
  skuId: string | null;
  boardId: string;
  nodeId: string;
  boardOrder: number;
  modelProfileId: string;
  prompt: string;
  width: number;
  height: number;
  ratio: string;
  compositionGroupId: string | null;
  layoutHash: string;
  inputs: CanvasGenerationInput[];
  textSnapshotIds: string[];
}

export interface CanvasGenerationCreate {
  revision: number;
  mode: "complete-set" | "advanced";
  items: CanvasGenerationItem[];
}

export interface ValidationReason {
  code:
    | "no_output_selected"
    | "output_configuration_missing"
    | "invalid_quantity"
    | "invalid_dimensions"
    | "model_unavailable"
    | "product_missing"
    | "composition_missing"
    | "board_count_mismatch"
    | "output_binding_missing"
    | "too_many_items"
    | "advanced_graph_invalid"
    | "model_capability_invalid"
    | "revision_pending";
  outputType?: OutputType;
  message: string;
}

export type GenerationRequestResult =
  | { ok: true; request: CanvasGenerationCreate }
  | { ok: false; reasons: ValidationReason[] };

const OUTPUT_KIND: Record<OutputType, CanvasNode["kind"]> = {
  main: "main_output",
  sku: "sku_output",
  detail: "detail_output",
};

const OUTPUT_LABEL: Record<OutputType, string> = {
  main: "主图",
  sku: "SKU图",
  detail: "详情图",
};

function reason(
  code: ValidationReason["code"],
  message: string,
  outputType?: OutputType,
): GenerationRequestResult {
  return { ok: false, reasons: [{ code, message, ...(outputType === undefined ? {} : { outputType }) }] };
}

function ratioFor(width: number, height: number): string {
  const gcd = (left: number, right: number): number =>
    right === 0 ? left : gcd(right, left % right);
  const divisor = gcd(width, height);
  return `${width / divisor}:${height / divisor}`;
}

function outputKey(output: Pick<CompleteSetOutput, "outputType" | "skuId">): string {
  return `${output.outputType}:${output.skuId ?? "main"}`;
}

function expectedOutputCount(output: CompleteSetOutput): number {
  return output.quantity ?? 0;
}

function usableModel(catalog: ModelProfile[], id: string | null): ModelProfile | null {
  if (id === null) return null;
  const model = catalog.find((candidate) => candidate.id === id);
  return model !== undefined && model.enabled && model.availability === "available"
    ? model
    : null;
}

function modelCapabilityReason(
  model: ModelProfile,
  width: number,
  height: number,
  referenceCount: number,
  label: string,
  outputType: OutputType,
): GenerationRequestResult | null {
  const capabilities = model.capabilities;
  if (!capabilities.textToImage || capabilities.maxQuantity < 1) {
    return reason(
      "model_capability_invalid",
      `${label}所选模型不能生成单张图`,
      outputType,
    );
  }
  if (
    referenceCount > 0 &&
    (!capabilities.imageToImage ||
      capabilities.maxReferenceImages < referenceCount ||
      capabilities.referenceTransfer === "none")
  ) {
    return reason(
      "model_capability_invalid",
      `${label}所选模型不支持产品参考图`,
      outputType,
    );
  }
  const ratio = ratioFor(width, height);
  if (
    (capabilities.allowedRatios.length > 0 && !capabilities.allowedRatios.includes(ratio)) ||
    (capabilities.allowedSizes.length > 0 && !capabilities.allowedSizes.includes(`${width}x${height}`)) ||
    (capabilities.minWidth !== null && width < capabilities.minWidth) ||
    (capabilities.maxWidth !== null && width > capabilities.maxWidth) ||
    (capabilities.minHeight !== null && height < capabilities.minHeight) ||
    (capabilities.maxHeight !== null && height > capabilities.maxHeight)
  ) {
    return reason(
      "model_capability_invalid",
      `${label}尺寸不受所选模型支持`,
      outputType,
    );
  }
  return null;
}

function mainLockedProductAsset(project: CanvasProjectState): string | null {
  return project.layoutState.productLayers.find(
    (layer) => layer.skuId === null && layer.locked,
  )?.sourceAssetId ?? null;
}

function completeSetProductAsset(
  project: CanvasProjectState,
  output: CompleteSetOutput,
): string | null {
  const ownLayer = project.layoutState.productLayers.find(
    (layer) => layer.skuId === output.skuId && layer.locked,
  );
  if (output.outputType !== "sku") {
    return output.referenceAssetId ?? ownLayer?.sourceAssetId ?? null;
  }
  const mainAsset = mainLockedProductAsset(project);
  if (ownLayer !== undefined) {
    if (output.referenceAssetId === null || output.referenceAssetId === ownLayer.sourceAssetId) {
      return ownLayer.sourceAssetId;
    }
    return output.referenceAssetId === mainAsset ? mainAsset : null;
  }
  return output.referenceAssetId !== null && output.referenceAssetId === mainAsset
    ? mainAsset
    : null;
}

function advancedProductAsset(
  project: CanvasProjectState,
  generationId: string,
  skuId: string | null,
): string | null {
  // The product material in an advanced request is never a free-form node
  // input.  It is the immutable projection created by the upload/cutout
  // pipeline.  SKU boards deliberately reuse this canonical main product
  // route until a dedicated SKU pipeline exists.
  void skuId;
  const mainLayer = project.layoutState.productLayers.find(
    (layer) => layer.skuId === null && layer.locked,
  );
  if (mainLayer === undefined) return null;
  const source = project.semanticState.nodes.find((node) => node.id === "main-product-source");
  const cutout = project.semanticState.nodes.find((node) => node.id === "main-product-cutout");
  if (
    source?.kind !== "product_source" ||
    source.skuId !== null ||
    source.assetId !== mainLayer.sourceAssetId ||
    cutout?.kind !== "auto_cutout" ||
    cutout.skuId !== null ||
    cutout.assetId !== mainLayer.renderAssetId
  ) return null;
  const productRoutes = project.semanticState.edges.filter(
    (edge) =>
      edge.kind === "product_asset" &&
      edge.targetNodeId === cutout.id,
  );
  if (
    productRoutes.length !== 1 ||
    productRoutes[0]?.sourceNodeId !== source.id
  ) return null;
  const cutoutRoutes = project.semanticState.edges.filter(
    (edge) =>
      edge.kind === "cutout_asset" &&
      edge.targetNodeId === generationId,
  );
  return cutoutRoutes.length === 1 && cutoutRoutes[0]?.sourceNodeId === cutout.id
    ? cutout.assetId
    : null;
}

function advancedGraphReason(message: string, outputType?: OutputType): GenerationRequestResult {
  return reason("advanced_graph_invalid", message, outputType);
}

function advancedDimensions(node: CanvasNode): { width: number; height: number; ratio: string } | null {
  const width = node.parameters.width;
  const height = node.parameters.height;
  if (
    typeof width !== "number" || !Number.isInteger(width) || width < 1 ||
    typeof height !== "number" || !Number.isInteger(height) || height < 1
  ) return null;
  return { width, height, ratio: ratioFor(width, height) };
}

function singleAdvancedEdge(
  project: CanvasProjectState,
  kind: TypedEdge["kind"],
  targetNodeId: string,
): TypedEdge | null {
  const edges = project.semanticState.edges.filter(
    (edge) => edge.kind === kind && edge.targetNodeId === targetNodeId,
  );
  return edges.length === 1 ? edges[0]! : null;
}

function advancedTextSnapshotIds(
  project: CanvasProjectState,
  outputNodeId: string,
): string[] | null {
  const snapshotIds: string[] = [];
  for (const edge of project.semanticState.edges) {
    if (edge.kind !== "text_layer" || edge.targetNodeId !== outputNodeId) continue;
    const source = project.semanticState.nodes.find((node) => node.id === edge.sourceNodeId);
    if (source?.kind !== "text_layer" || source.textSnapshotId === null) return null;
    snapshotIds.push(source.textSnapshotId);
  }
  if (new Set(snapshotIds).size !== snapshotIds.length) return null;
  const snapshots = snapshotIds.map((id) => project.layoutState.textSnapshots.find(
    (snapshot) => snapshot.id === id,
  ));
  if (snapshots.some((snapshot) => snapshot === undefined)) return null;
  return snapshots
    .sort((left, right) => (
      left!.sortOrder - right!.sortOrder || left!.id.localeCompare(right!.id)
    ))
    .map((snapshot) => snapshot!.id);
}

function buildAdvancedGenerationRequest(
  project: CanvasProjectState,
  catalog: ModelProfile[],
  revision: number,
): GenerationRequestResult {
  const items: CanvasGenerationItem[] = [];
  for (const board of project.semanticState.outputBoards) {
    const output = project.semanticState.nodes.find((node) => node.id === board.outputNodeId);
    if (output === undefined || output.outputBoardId !== board.id || output.kind !== OUTPUT_KIND[board.outputType]) {
      return advancedGraphReason("高级模式输出画板缺少绑定节点", board.outputType);
    }
    if (
      output.modelProfileId !== null ||
      output.prompt !== null ||
      output.compositionGroupId !== null
    ) {
      return advancedGraphReason("高级模式输出绑定必须通过连线表达", board.outputType);
    }
    if (project.semanticState.edges.some(
      (edge) => edge.kind === "background_image" && edge.targetNodeId === output.id,
    )) {
      return advancedGraphReason("高级模式暂不支持背景图连线", board.outputType);
    }
    const generationEdge = singleAdvancedEdge(project, "output_image", output.id);
    const generation = generationEdge === null
      ? undefined
      : project.semanticState.nodes.find((node) => node.id === generationEdge.sourceNodeId);
    if (generation?.kind !== "model_generation") {
      return advancedGraphReason("高级模式输出必须连接生成节点", board.outputType);
    }
    const promptEdge = singleAdvancedEdge(project, "prompt", generation.id);
    const prompt = promptEdge === null
      ? ""
      : project.semanticState.nodes.find((node) => node.id === promptEdge.sourceNodeId)?.prompt ?? "";
    if (prompt.trim() === "") return advancedGraphReason("高级模式生成节点缺少提示词", board.outputType);
    const model = usableModel(catalog, generation.modelProfileId);
    if (model === null) {
      return reason("model_unavailable", "高级模式需要选择可用模型", board.outputType);
    }
    const dimensions = advancedDimensions(generation);
    if (dimensions === null) return reason("invalid_dimensions", "高级模式生成节点需要有效宽高", board.outputType);
    const productAssetId = advancedProductAsset(project, generation.id, board.skuId);
    if (productAssetId === null) return reason("product_missing", "高级模式生成节点缺少产品参考图", board.outputType);
    const compositionEdge = singleAdvancedEdge(project, "composition", output.id);
    const compositionNode = compositionEdge === null
      ? undefined
      : project.semanticState.nodes.find((node) => node.id === compositionEdge.sourceNodeId);
    const groupId = compositionNode?.compositionGroupId ?? null;
    const group = groupId === null
      ? undefined
      : project.semanticState.compositionGroups.find((candidate) => candidate.id === groupId);
    if (group === undefined) return reason("composition_missing", "高级模式输出缺少构图组", board.outputType);
    const textSnapshotIds = advancedTextSnapshotIds(project, output.id);
    if (textSnapshotIds === null) {
      return advancedGraphReason("高级模式文字必须通过文字图层连线到输出画板", board.outputType);
    }
    const capability = modelCapabilityReason(
      model,
      dimensions.width,
      dimensions.height,
      1,
      OUTPUT_LABEL[board.outputType],
      board.outputType,
    );
    if (capability !== null) return capability;
    items.push({
      outputType: board.outputType,
      skuId: board.skuId,
      boardId: board.id,
      nodeId: output.id,
      boardOrder: board.sortOrder,
      modelProfileId: generation.modelProfileId as string,
      prompt: prompt.trim(),
      width: dimensions.width,
      height: dimensions.height,
      ratio: dimensions.ratio,
      compositionGroupId: group.id,
      layoutHash: group.layoutHash,
      inputs: [{ assetId: productAssetId, inputRole: "product", ordinal: 0 }],
      textSnapshotIds,
    });
  }
  if (items.length === 0) return advancedGraphReason("高级模式没有连接的输出画板");
  if (items.length > 50) return reason("too_many_items", "本次生成最多支持 50 张图");
  return { ok: true, request: { revision, mode: "advanced", items } };
}

export function buildGenerationRequest(
  project: CanvasProjectState,
  catalog: ModelProfile[],
  revision: number,
): GenerationRequestResult {
  if (!Number.isInteger(revision) || revision < 1) {
    throw new Error("generation revision must be a positive integer");
  }
  if (project.semanticState.mode === "advanced") {
    return buildAdvancedGenerationRequest(project, catalog, revision);
  }
  const selected = project.semanticState.completeSet.selectedOutputTypes;
  if (selected.length === 0) {
    return reason("no_output_selected", "至少选择一种输出类型");
  }
  const selectedSet = new Set(selected);
  const outputs = project.semanticState.completeSet.outputs.filter(
    (output) => selectedSet.has(output.outputType),
  );
  const expectedKeys = new Set(
    selected.flatMap((outputType) =>
      outputType === "sku"
        ? outputs.filter((output) => output.outputType === "sku").map(outputKey)
        : [outputKey({ outputType, skuId: null })],
    ),
  );
  if (outputs.length === 0 || expectedKeys.size !== outputs.length) {
    const missing = selected.find((outputType) =>
      outputType === "sku"
        ? !outputs.some((output) => output.outputType === "sku")
        : !outputs.some((output) => output.outputType === outputType && output.skuId === null),
    );
    return reason(
      "output_configuration_missing",
      `${OUTPUT_LABEL[missing ?? selected[0]]}缺少生成配置`,
      missing ?? selected[0],
    );
  }

  const items: CanvasGenerationItem[] = [];
  for (const output of outputs) {
    const label = OUTPUT_LABEL[output.outputType];
    const quantity = expectedOutputCount(output);
    if (!Number.isInteger(quantity) || quantity < 1 || quantity > 20) {
      return reason("invalid_quantity", `${label}数量必须为 1 到 20`, output.outputType);
    }
    if (
      !Number.isInteger(output.width) || !Number.isInteger(output.height) ||
      output.width === null || output.height === null || output.width < 1 || output.height < 1 ||
      output.aspectRatio === null || output.aspectRatio !== ratioFor(output.width, output.height)
    ) {
      return reason("invalid_dimensions", `${label}需要匹配的比例与尺寸`, output.outputType);
    }
    const model = usableModel(catalog, output.modelProfileId);
    if (model === null) {
      return reason("model_unavailable", `${label}需要选择可用模型`, output.outputType);
    }
    const productLayer = project.layoutState.productLayers.find(
      (layer) => layer.skuId === output.skuId && layer.locked,
    );
    const productAssetId = completeSetProductAsset(project, output);
    if (productAssetId === null) {
      return reason(
        "product_missing",
        output.outputType === "sku"
          ? "SKU图缺少自身产品参考图或明确的主产品复用"
          : `${label}缺少产品参考图`,
        output.outputType,
      );
    }
    const groupId = output.compositionGroupId ?? productLayer?.compositionGroupId ?? null;
    const group = groupId === null
      ? null
      : project.semanticState.compositionGroups.find((candidate) => candidate.id === groupId);
    if (group === undefined || group === null) {
      return reason("composition_missing", `${label}缺少构图组`, output.outputType);
    }
    const capability = modelCapabilityReason(
      model,
      output.width,
      output.height,
      1,
      label,
      output.outputType,
    );
    if (capability !== null) return capability;
    const boards = project.semanticState.outputBoards
      .filter((board) => board.outputType === output.outputType && board.skuId === output.skuId)
      .sort((left, right) => left.sortOrder - right.sortOrder || left.id.localeCompare(right.id));
    if (boards.length !== quantity) {
      return reason("board_count_mismatch", `${label}的画板数量与输出数量不一致`, output.outputType);
    }
    for (const board of boards) {
      const node = project.semanticState.nodes.find((candidate) => candidate.id === board.outputNodeId);
      if (
        node === undefined || node.kind !== OUTPUT_KIND[output.outputType] ||
        node.outputBoardId !== board.id
      ) {
        return reason("output_binding_missing", `${label}缺少独立输出节点`, output.outputType);
      }
      items.push({
        outputType: output.outputType,
        skuId: output.skuId,
        boardId: board.id,
        nodeId: node.id,
        boardOrder: board.sortOrder,
        modelProfileId: output.modelProfileId as string,
        prompt: output.prompt.trim(),
        width: output.width,
        height: output.height,
        ratio: output.aspectRatio,
        compositionGroupId: group.id,
        layoutHash: group.layoutHash,
        inputs: [{ assetId: productAssetId, inputRole: "product", ordinal: 0 }],
        textSnapshotIds: project.layoutState.textSnapshots.map((snapshot) => snapshot.id),
      });
    }
  }
  if (items.length > 50) {
    return reason("too_many_items", "本次生成最多支持 50 张图");
  }
  const ids = new Set(items.map((item) => item.boardId));
  const nodeIds = new Set(items.map((item) => item.nodeId));
  if (ids.size !== items.length || nodeIds.size !== items.length) {
    return reason("output_binding_missing", "每张生成图必须绑定独立画板和输出节点");
  }
  return {
    ok: true,
    request: { revision, mode: project.semanticState.mode, items },
  };
}

/** UI-only validation must tolerate the local revision before the first project load. */
export function previewGenerationRequest(
  project: CanvasProjectState,
  catalog: ModelProfile[],
  revision: number,
): GenerationRequestResult {
  if (!Number.isInteger(revision) || revision < 1) {
    return reason("revision_pending", "项目尚未保存，暂不能生成");
  }
  return buildGenerationRequest(project, catalog, revision);
}
