import { describe, expect, test } from "vitest";

import { DEFAULT_COMPOSITION_LAYOUT, compositionLayoutHash } from "./composition";
import { buildGenerationRequest, previewGenerationRequest } from "./generation";
import type { ModelProfile } from "./providers";
import { createEmptyProjectState, type CanvasProjectState } from "./types";

const model: ModelProfile = {
  id: "model-1",
  providerId: "provider-1",
  modelId: "fake-image",
  displayName: "Fake Image",
  enabled: true,
  availability: "available",
  availabilityReason: null,
  configVersion: 1,
  capabilities: {
    textToImage: true,
    imageToImage: true,
    maskEdit: false,
    allowedRatios: ["1:1"],
    allowedSizes: ["1024x1024"],
    minWidth: 512,
    maxWidth: 2048,
    minHeight: 512,
    maxHeight: 2048,
    maxQuantity: 1,
    maxReferenceImages: 1,
    referenceTransfer: "public_url",
    protocol: "sync",
    supportsCancel: false,
    supportsIdempotency: false,
    supportsIdempotencyLookup: false,
    concurrencyLimit: 1,
    priceMetadata: null,
  },
  priceMetadata: null,
};

function projectWithOneMain(): CanvasProjectState {
  const project = createEmptyProjectState();
  const layout = structuredClone(DEFAULT_COMPOSITION_LAYOUT);
  project.semanticState.mode = "complete-set";
  project.semanticState.completeSet.selectedOutputTypes = ["main"];
  project.semanticState.completeSet.outputs = [{
    outputType: "main",
    skuId: null,
    quantity: 1,
    aspectRatio: "1:1",
    width: 1024,
    height: 1024,
    prompt: "clean studio background",
    modelProfileId: "model-1",
    modelParameters: {},
    referenceAssetId: "working-product",
    compositionGroupId: "group-main",
  }];
  project.semanticState.compositionGroups = [{
    id: "group-main",
    skuIds: [],
    productLayerIds: ["layer-main"],
    layout,
    layoutHash: compositionLayoutHash(layout),
  }];
  project.layoutState.productLayers = [{
    id: "layer-main",
    sourceAssetId: "working-product",
    renderAssetId: "working-product",
    allowOpaqueFallback: true,
    skuId: null,
    compositionGroupId: "group-main",
    transformId: "layer-main-transform",
    locked: true,
  }];
  project.semanticState.nodes = [{
    id: "board-main-node",
    kind: "main_output",
    managedBy: "complete-set",
    skuId: null,
    assetId: null,
    modelProfileId: "model-1",
    prompt: "clean studio background",
    compositionGroupId: "group-main",
    textSnapshotId: null,
    outputBoardId: "board-main",
    parameters: {},
  }];
  project.semanticState.outputBoards = [{
    id: "board-main",
    outputNodeId: "board-main-node",
    outputType: "main",
    skuId: null,
    sortOrder: 0,
    selectedResultAssetId: null,
  }];
  return project;
}

describe("complete-set generation projection", () => {
  test("all output types start unselected and generation gives an exact reason", () => {
    const result = buildGenerationRequest(createEmptyProjectState(), [model], 3);
    expect(result).toEqual({
      ok: false,
      reasons: [{ code: "no_output_selected", message: "至少选择一种输出类型" }],
    });
  });

  test("local UI preview defers generation validation until the first project revision exists", () => {
    expect(previewGenerationRequest(createEmptyProjectState(), [model], 0)).toEqual({
      ok: false,
      reasons: [{ code: "revision_pending", message: "项目尚未保存，暂不能生成" }],
    });
  });

  test("projects every selected board into one immutable backend item", () => {
    const result = buildGenerationRequest(projectWithOneMain(), [model], 3);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.request).toEqual({
      revision: 3,
      mode: "complete-set",
      items: [{
        outputType: "main",
        skuId: null,
        boardId: "board-main",
        nodeId: "board-main-node",
        boardOrder: 0,
        modelProfileId: "model-1",
        prompt: "clean studio background",
        width: 1024,
        height: 1024,
        ratio: "1:1",
        compositionGroupId: "group-main",
        layoutHash: compositionLayoutHash(DEFAULT_COMPOSITION_LAYOUT),
        inputs: [{ assetId: "working-product", inputRole: "product", ordinal: 0 }],
        textSnapshotIds: [],
      }],
    });
  });

  test("requires a unique board/output-node binding for every counted item", () => {
    const project = projectWithOneMain();
    project.semanticState.completeSet.outputs[0].quantity = 2;
    const result = buildGenerationRequest(project, [model], 3);
    expect(result).toEqual({
      ok: false,
      reasons: [{
        code: "board_count_mismatch",
        outputType: "main",
        message: "主图的画板数量与输出数量不一致",
      }],
    });
  });

  test("rejects a product-reference generation when the selected model cannot accept images", () => {
    const unavailableForReference = structuredClone(model);
    unavailableForReference.capabilities.imageToImage = false;
    unavailableForReference.capabilities.maxReferenceImages = 0;

    expect(buildGenerationRequest(projectWithOneMain(), [unavailableForReference], 3)).toEqual({
      ok: false,
      reasons: [{
        code: "model_capability_invalid",
        outputType: "main",
        message: "主图所选模型不支持产品参考图",
      }],
    });
  });

  test("disables a generation when the selected model cannot produce text prompts or a single item", () => {
    const unavailable = structuredClone(model);
    unavailable.capabilities.textToImage = false;
    unavailable.capabilities.maxQuantity = 0;

    expect(buildGenerationRequest(projectWithOneMain(), [unavailable], 3)).toEqual({
      ok: false,
      reasons: [{
        code: "model_capability_invalid",
        outputType: "main",
        message: "主图所选模型不能生成单张图",
      }],
    });
  });

  test("rejects a SKU that substitutes an arbitrary product asset instead of its own or explicit main fallback", () => {
    const project = projectWithOneMain();
    project.semanticState.completeSet.selectedOutputTypes = ["sku"];
    project.semanticState.completeSet.outputs[0] = {
      ...project.semanticState.completeSet.outputs[0]!,
      outputType: "sku",
      skuId: "sku-a",
      referenceAssetId: "unrelated-product",
    };
    project.semanticState.outputBoards[0] = {
      ...project.semanticState.outputBoards[0]!,
      id: "board-sku",
      outputNodeId: "board-sku-node",
      outputType: "sku",
      skuId: "sku-a",
    };
    project.semanticState.nodes[0] = {
      ...project.semanticState.nodes[0]!,
      id: "board-sku-node",
      kind: "sku_output",
      outputBoardId: "board-sku",
    };

    expect(buildGenerationRequest(project, [model], 3)).toEqual({
      ok: false,
      reasons: [{
        code: "product_missing",
        outputType: "sku",
        message: "SKU图缺少自身产品参考图或明确的主产品复用",
      }],
    });
  });

  test("projects a connected advanced graph into the same immutable generation request", () => {
    const project = projectWithOneMain();
    project.semanticState.mode = "advanced";
    project.semanticState.completeSet = { selectedOutputTypes: [], outputs: [] };
    project.semanticState.nodes = [
      {
        id: "main-product-source", kind: "product_source", managedBy: null, skuId: null, assetId: "working-product",
        modelProfileId: null, prompt: null, compositionGroupId: null, textSnapshotId: null, outputBoardId: null, parameters: {},
      },
      {
        id: "main-product-cutout", kind: "auto_cutout", managedBy: null, skuId: null, assetId: "working-product",
        modelProfileId: null, prompt: null, compositionGroupId: null, textSnapshotId: null, outputBoardId: null, parameters: {},
      },
      {
        id: "prompt", kind: "prompt", managedBy: null, skuId: null, assetId: null,
        modelProfileId: null, prompt: "clean studio background", compositionGroupId: null, textSnapshotId: null, outputBoardId: null, parameters: {},
      },
      {
        id: "generation", kind: "model_generation", managedBy: null, skuId: null, assetId: null,
        modelProfileId: "model-1", prompt: null, compositionGroupId: null, textSnapshotId: null, outputBoardId: null,
        parameters: { width: 1024, height: 1024 },
      },
      {
        id: "board-main-node", kind: "main_output", managedBy: null, skuId: null, assetId: null,
        modelProfileId: null, prompt: null, compositionGroupId: null, textSnapshotId: null, outputBoardId: "board-main", parameters: {},
      },
      {
        id: "composition", kind: "composition_group", managedBy: null, skuId: null, assetId: null,
        modelProfileId: null, prompt: null, compositionGroupId: "group-main", textSnapshotId: null, outputBoardId: null, parameters: {},
      },
      {
        id: "advanced-text-layer", kind: "text_layer", managedBy: null, skuId: null, assetId: null,
        modelProfileId: null, prompt: null, compositionGroupId: null, textSnapshotId: "advanced-text", outputBoardId: null, parameters: {},
      },
    ];
    project.semanticState.edges = [
      { id: "source-cutout-edge", kind: "product_asset", sourceNodeId: "main-product-source", sourcePort: "product", targetNodeId: "main-product-cutout", targetPort: "reference", skuId: null },
      { id: "cutout-edge", kind: "cutout_asset", sourceNodeId: "main-product-cutout", sourcePort: "cutout", targetNodeId: "generation", targetPort: "reference", skuId: null },
      { id: "prompt-edge", kind: "prompt", sourceNodeId: "prompt", sourcePort: "prompt", targetNodeId: "generation", targetPort: "prompt", skuId: null },
      { id: "output-edge", kind: "output_image", sourceNodeId: "generation", sourcePort: "output", targetNodeId: "board-main-node", targetPort: "input", skuId: null },
      { id: "composition-edge", kind: "composition", sourceNodeId: "composition", sourcePort: "composition", targetNodeId: "board-main-node", targetPort: "composition", skuId: null },
      { id: "text-edge", kind: "text_layer", sourceNodeId: "advanced-text-layer", sourcePort: "text", targetNodeId: "board-main-node", targetPort: "text", skuId: null },
    ];
    project.layoutState.textSnapshots = [
      {
        id: "advanced-text", nodeId: "advanced-text-layer", content: "已连线", fontAssetId: null,
        fontFamily: "Noto Sans CJK SC", fontVersion: "sha256:2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b",
        boxWidth: 100, lines: [{ text: "已连线", x: 0, y: 0, width: 100 }], fontSize: 16,
        color: "#0f172a", letterSpacing: 0, lineHeight: 1, align: "left", baseline: "alphabetic", zBand: "above-product", sortOrder: 0,
      },
      {
        id: "unwired-text", nodeId: "unwired-layer", content: "未连线", fontAssetId: null,
        fontFamily: "Noto Sans CJK SC", fontVersion: "sha256:2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b",
        boxWidth: 100, lines: [{ text: "未连线", x: 0, y: 0, width: 100 }], fontSize: 16,
        color: "#0f172a", letterSpacing: 0, lineHeight: 1, align: "left", baseline: "alphabetic", zBand: "above-product", sortOrder: 1,
      },
    ];

    const result = buildGenerationRequest(project, [model], 3);

    expect(result).toMatchObject({
      ok: true,
      request: {
        mode: "advanced",
        items: [expect.objectContaining({ boardId: "board-main", nodeId: "board-main-node", prompt: "clean studio background", modelProfileId: "model-1", textSnapshotIds: ["advanced-text"] })],
      },
    });
  });

  test("rejects an advanced graph that substitutes a fake auto-cutout node", () => {
    const project = projectWithOneMain();
    project.semanticState.mode = "advanced";
    project.semanticState.nodes = [
      { id: "main-product-source", kind: "product_source", managedBy: null, skuId: null, assetId: "working-product", modelProfileId: null, prompt: null, compositionGroupId: null, textSnapshotId: null, outputBoardId: null, parameters: {} },
      { id: "fake-cutout", kind: "auto_cutout", managedBy: null, skuId: null, assetId: "working-product", modelProfileId: null, prompt: null, compositionGroupId: null, textSnapshotId: null, outputBoardId: null, parameters: {} },
      { id: "prompt", kind: "prompt", managedBy: null, skuId: null, assetId: null, modelProfileId: null, prompt: "studio", compositionGroupId: null, textSnapshotId: null, outputBoardId: null, parameters: {} },
      { id: "generation", kind: "model_generation", managedBy: null, skuId: null, assetId: null, modelProfileId: "model-1", prompt: null, compositionGroupId: null, textSnapshotId: null, outputBoardId: null, parameters: { width: 1024, height: 1024 } },
      { id: "board-main-node", kind: "main_output", managedBy: "complete-set", skuId: null, assetId: null, modelProfileId: null, prompt: null, compositionGroupId: null, textSnapshotId: null, outputBoardId: "board-main", parameters: {} },
      { id: "composition", kind: "composition_group", managedBy: null, skuId: null, assetId: null, modelProfileId: null, prompt: null, compositionGroupId: "group-main", textSnapshotId: null, outputBoardId: null, parameters: {} },
    ];
    project.semanticState.edges = [
      { id: "source-cutout", kind: "product_asset", sourceNodeId: "main-product-source", sourcePort: "product", targetNodeId: "fake-cutout", targetPort: "reference", skuId: null },
      { id: "cutout-generation", kind: "cutout_asset", sourceNodeId: "fake-cutout", sourcePort: "cutout", targetNodeId: "generation", targetPort: "reference", skuId: null },
      { id: "prompt-generation", kind: "prompt", sourceNodeId: "prompt", sourcePort: "prompt", targetNodeId: "generation", targetPort: "prompt", skuId: null },
      { id: "generation-output", kind: "output_image", sourceNodeId: "generation", sourcePort: "output", targetNodeId: "board-main-node", targetPort: "input", skuId: null },
      { id: "composition-output", kind: "composition", sourceNodeId: "composition", sourcePort: "composition", targetNodeId: "board-main-node", targetPort: "composition", skuId: null },
    ];

    expect(buildGenerationRequest(project, [model], 3)).toEqual({
      ok: false,
      reasons: [{ code: "product_missing", outputType: "main", message: "高级模式生成节点缺少产品参考图" }],
    });
  });
});
