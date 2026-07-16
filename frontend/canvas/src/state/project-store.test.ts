import { describe, expect, test } from "vitest";

import {
  createEmptyProjectState,
  type CanvasNode,
  type ProjectAction,
  type TypedEdge,
} from "../domain/types";
import {
  parseProjectState,
  serializeProjectState,
} from "../domain/validation";
import projectStateFixture from "../../test/fixtures/project-state-v1.json?raw";
import {
  compositionLayoutHash,
  DEFAULT_COMPOSITION_LAYOUT,
} from "../domain/composition";
import { mountCanvas } from "../main";
import { createPresentationPlan } from "../canvas/object-factory";
import {
  createProjectViews,
  isCompleteSetTopologyRepresentable,
  selectCompleteSetForm,
} from "./complete-set-projection";
import {
  createProjectStore,
  reduceProjectState,
} from "./project-store";

function node(
  id: string,
  kind: CanvasNode["kind"],
  managedBy: CanvasNode["managedBy"] = null,
): CanvasNode {
  return {
    id,
    kind,
    managedBy,
    skuId: null,
    assetId: null,
    modelProfileId: null,
    prompt: null,
    compositionGroupId: null,
    textSnapshotId: null,
    outputBoardId: null,
    parameters: {},
  } as CanvasNode;
}

function permitResultAsset(
  store: ReturnType<typeof createProjectStore>,
  boardId: string,
  assetId: string,
): void {
  const current = store.getState().runtime.allowedResultAssetIds[boardId] ?? [];
  store.dispatch({
    type: "runtime/setAllowedResultAssets",
    boardId,
    assetIds: [...current, assetId],
  });
}

describe("canvas project store", () => {
  test("an empty project has no selected output or output board", () => {
    const store = createProjectStore();

    expect(store.getState().project.semanticState.completeSet.selectedOutputTypes).toEqual(
      [],
    );
    expect(store.getState().project.semanticState.outputBoards).toEqual([]);
  });

  test("creates one deterministic shared composition group from the locked main product", () => {
    const project = createEmptyProjectState();
    project.layoutState.productLayers.push({
      id: "main-product",
      sourceAssetId: "working-product",
      renderAssetId: "cutout-product",
      allowOpaqueFallback: false,
      skuId: null,
      compositionGroupId: null,
      transformId: "main-product-transform",
      locked: true,
    });
    project.layoutState.objectTransforms["main-product-transform"] = {
      x: 0.5, y: 0.5, scale: 1, rotation: 0,
    };
    const store = createProjectStore(project);

    expect(store.dispatch({
      type: "composition/create",
      skuProducts: [
        { skuId: "sku-b", sourceAssetId: "sku-b-working", renderAssetId: "sku-b-cutout", allowOpaqueFallback: false },
        { skuId: "sku-a", sourceAssetId: "sku-a-working", renderAssetId: "sku-a-cutout", allowOpaqueFallback: false },
        { skuId: "sku-a", sourceAssetId: "ignored", renderAssetId: "ignored", allowOpaqueFallback: false },
      ],
    }).applied).toBe(true);
    expect(store.getState().project.semanticState.compositionGroups).toEqual([
      expect.objectContaining({
        id: "composition-group-1",
        skuIds: ["sku-b", "sku-a"],
        productLayerIds: [
          "main-product",
          "composition-group-1:sku:sku-b",
          "composition-group-1:sku:sku-a",
        ],
        layoutHash: compositionLayoutHash(DEFAULT_COMPOSITION_LAYOUT),
      }),
    ]);
    expect(store.getState().project.layoutState.productLayers).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: "main-product", compositionGroupId: "composition-group-1" }),
      expect.objectContaining({ id: "composition-group-1:sku:sku-b", skuId: "sku-b", compositionGroupId: "composition-group-1", sourceAssetId: "sku-b-working" }),
      expect.objectContaining({ id: "composition-group-1:sku:sku-a", skuId: "sku-a", compositionGroupId: "composition-group-1", sourceAssetId: "sku-a-working" }),
    ]));
    expect(store.getState().project.layoutState.objectTransforms["main-product-transform"])
      .toEqual({ x: 0.5, y: 0.9, scale: 0.8, rotation: 0 });
    expect(store.dispatch({ type: "composition/create", skuProducts: [] }).applied).toBe(false);
  });

  test("projects a configured composition group onto every complete-set output board", () => {
    const project = createEmptyProjectState();
    project.layoutState.productLayers.push({
      id: "main-product",
      sourceAssetId: "working-product",
      renderAssetId: "cutout-product",
      allowOpaqueFallback: false,
      skuId: null,
      compositionGroupId: null,
      transformId: "main-product-transform",
      locked: true,
    });
    project.layoutState.objectTransforms["main-product-transform"] = {
      x: 0.5, y: 0.5, scale: 1, rotation: 0,
    };
    const store = createProjectStore(project);
    store.dispatch({ type: "composition/create", skuProducts: [] });
    store.dispatch({ type: "output/enable", outputType: "main" });
    store.dispatch({ type: "output/setQuantity", outputType: "main", quantity: 2 });
    store.dispatch({
      type: "output/configure",
      outputType: "main",
      skuId: null,
      patch: { compositionGroupId: "composition-group-1" },
    });

    expect(store.getState().project.semanticState.outputBoards).toHaveLength(2);
    expect(store.getState().project.semanticState.outputBoards.map((board) => (
      store.getState().project.semanticState.nodes.find((node) => node.id === board.outputNodeId)?.compositionGroupId
    ))).toEqual(["composition-group-1", "composition-group-1"]);
    expect(isCompleteSetTopologyRepresentable(store.getState().project)).toBe(true);
  });

  test("enabling an output creates its managed group but leaves quantity unset", () => {
    const store = createProjectStore();

    const result = store.dispatch({ type: "output/enable", outputType: "main" });
    const project = store.getState().project;

    expect(result.applied).toBe(true);
    expect(project.semanticState.completeSet.selectedOutputTypes).toEqual(["main"]);
    expect(project.semanticState.completeSet.outputs).toMatchObject([
      { outputType: "main", skuId: null, quantity: null },
    ]);
    expect(
      project.semanticState.nodes.filter(
        (node) => node.managedBy === "complete-set",
      ),
    ).toHaveLength(3);
    expect(project.semanticState.outputBoards).toEqual([]);
  });

  test("main and detail quantities keep stable IDs and append only", () => {
    const store = createProjectStore();
    store.dispatch({ type: "output/enable", outputType: "main" });
    store.dispatch({ type: "output/setQuantity", outputType: "main", quantity: 2 });

    const firstIds = store
      .getState()
      .project.semanticState.outputBoards.map((board) => board.id);
    expect(firstIds).toEqual([
      "complete-set:board:main:1",
      "complete-set:board:main:2",
    ]);

    store.dispatch({ type: "output/setQuantity", outputType: "main", quantity: 2 });
    expect(
      store.getState().project.semanticState.outputBoards.map((board) => board.id),
    ).toEqual(firstIds);

    store.dispatch({ type: "output/enable", outputType: "detail" });
    store.dispatch({
      type: "output/setQuantity",
      outputType: "detail",
      quantity: 1,
    });
    store.dispatch({ type: "output/setQuantity", outputType: "main", quantity: 3 });

    expect(
      store.getState().project.semanticState.outputBoards.map((board) => board.id),
    ).toEqual([
      ...firstIds,
      "complete-set:board:detail:1",
      "complete-set:board:main:3",
    ]);
    expect(
      store.getState().project.semanticState.outputBoards.map(
        (board) => board.sortOrder,
      ),
    ).toEqual([0, 1, 2, 3]);
  });

  test("SKU boards use each SKU quantity and stable SKU-scoped ordinals", () => {
    const store = createProjectStore();
    store.dispatch({ type: "output/enable", outputType: "sku" });
    store.dispatch({ type: "sku/setOutputQuantity", skuId: "sku-a", quantity: 2 });
    store.dispatch({ type: "sku/setOutputQuantity", skuId: "sku-b", quantity: 1 });

    expect(
      store.getState().project.semanticState.completeSet.outputs.map((output) => ({
        skuId: output.skuId,
        quantity: output.quantity,
      })),
    ).toEqual([
      { skuId: "sku-a", quantity: 2 },
      { skuId: "sku-b", quantity: 1 },
    ]);
    expect(
      store.getState().project.semanticState.outputBoards.map((board) => board.id),
    ).toEqual([
      "complete-set:board:sku:sku-a:1",
      "complete-set:board:sku:sku-a:2",
      "complete-set:board:sku:sku-b:1",
    ]);
    expect(store.getState().project.semanticState.outputBoards.map((board) => (
      store.getState().project.semanticState.nodes.find((node) => node.id === board.outputNodeId)?.skuId
    ))).toEqual(["sku-a", "sku-a", "sku-b"]);
    expect(isCompleteSetTopologyRepresentable(store.getState().project)).toBe(true);
  });

  test("quantity reduction returns a deterministic diff and waits for confirmation", () => {
    const store = createProjectStore();
    store.dispatch({ type: "output/enable", outputType: "main" });
    store.dispatch({ type: "output/setQuantity", outputType: "main", quantity: 3 });
    permitResultAsset(store, "complete-set:board:main:2", "asset-confirmation-impact");
    store.dispatch({
      type: "board/selectResult",
      boardId: "complete-set:board:main:2",
      assetId: "asset-confirmation-impact",
    });

    const first = store.dispatch({
      type: "output/setQuantity",
      outputType: "main",
      quantity: 1,
    });
    const repeated = store.dispatch({
      type: "output/setQuantity",
      outputType: "main",
      quantity: 1,
    });

    expect(first.applied).toBe(false);
    expect(first.confirmation?.diff.removedBoardIds).toEqual([
      "complete-set:board:main:2",
      "complete-set:board:main:3",
    ]);
    expect(repeated.confirmation?.token).toBe(first.confirmation?.token);
    expect(store.getState().project.semanticState.outputBoards).toHaveLength(3);

    const accepted = store.dispatch({
      type: "output/setQuantity",
      outputType: "main",
      quantity: 1,
      acceptedDiffId: first.confirmation?.token,
    });
    expect(accepted.applied).toBe(true);
    expect(
      store.getState().project.semanticState.outputBoards.map((board) => board.id),
    ).toEqual(["complete-set:board:main:1"]);
  });

  test("unlinking an impacted board preserves selected and immutable task results", () => {
    const store = createProjectStore();
    store.dispatch({ type: "output/enable", outputType: "main" });
    store.dispatch({ type: "output/setQuantity", outputType: "main", quantity: 2 });
    permitResultAsset(store, "complete-set:board:main:2", "asset-selected");
    store.dispatch({
      type: "board/selectResult",
      boardId: "complete-set:board:main:2",
      assetId: "asset-selected",
    });
    store.dispatch({
      type: "task/statusReceived",
      task: {
        id: "task-1",
        boardId: "complete-set:board:main:2",
        status: "succeeded",
        results: [
          {
            id: "result-1",
            taskId: "task-1",
            boardId: "complete-set:board:main:2",
            assetId: "asset-result-1",
          },
        ],
      },
    });

    const pending = store.dispatch({
      type: "output/setQuantity",
      outputType: "main",
      quantity: 1,
    });
    expect(pending.confirmation?.diff.selectedResultAssetIds).toEqual([
      "asset-selected",
    ]);
    expect(pending.confirmation?.diff.taskIds).toEqual(["task-1"]);
    expect(pending.confirmation?.diff.historyResultIds).toEqual(["result-1"]);

    store.dispatch({
      type: "output/setQuantity",
      outputType: "main",
      quantity: 1,
      acceptedDiffId: pending.confirmation?.token,
    });

    expect(store.getState().runtime.taskSnapshots["task-1"]?.results).toHaveLength(1);
    expect(store.getState().runtime.resultHistory.map((result) => result.id)).toContain(
      "result-1",
    );
    expect(store.getState().runtime.unlinkedBoards).toMatchObject([
      {
        boardId: "complete-set:board:main:2",
        selectedResultAssetId: "asset-selected",
        taskIds: ["task-1"],
        resultIds: ["result-1"],
      },
    ]);
  });

  test("undo restores an unlinked board while runtime tasks survive, and redo rearchives it", () => {
    const store = createProjectStore();
    const boardId = "complete-set:board:main:2";
    store.dispatch({ type: "output/enable", outputType: "main" });
    store.dispatch({ type: "output/setQuantity", outputType: "main", quantity: 2 });
    permitResultAsset(store, boardId, "asset-undo-runtime");
    store.dispatch({
      type: "board/selectResult",
      boardId,
      assetId: "asset-undo-runtime",
    });
    store.dispatch({
      type: "task/statusReceived",
      task: {
        id: "task-undo-runtime",
        boardId,
        status: "succeeded",
        results: [
          {
            id: "result-undo-runtime",
            taskId: "task-undo-runtime",
            boardId,
            assetId: "asset-result-undo-runtime",
          },
        ],
      },
    });
    const pending = store.dispatch({
      type: "output/setQuantity",
      outputType: "main",
      quantity: 1,
    });
    store.dispatch({
      type: "output/setQuantity",
      outputType: "main",
      quantity: 1,
      acceptedDiffId: pending.confirmation?.token,
    });

    expect(store.getState().runtime.unlinkedBoards).toHaveLength(1);
    expect(store.undo()).toBe(true);
    expect(
      store.getState().project.semanticState.outputBoards.find(
        (board) => board.id === boardId,
      )?.selectedResultAssetId,
    ).toBe("asset-undo-runtime");
    expect(store.getState().runtime.unlinkedBoards).toEqual([]);
    expect(store.getState().runtime.taskSnapshots["task-undo-runtime"]).toBeDefined();
    expect(store.getState().runtime.resultHistory.map((result) => result.id)).toEqual([
      "result-undo-runtime",
    ]);

    expect(store.redo()).toBe(true);
    expect(
      store.getState().project.semanticState.outputBoards.some(
        (board) => board.id === boardId,
      ),
    ).toBe(false);
    expect(store.getState().runtime.unlinkedBoards).toEqual([
      {
        boardId,
        selectedResultAssetId: "asset-undo-runtime",
        taskIds: ["task-undo-runtime"],
        resultIds: ["result-undo-runtime"],
      },
    ]);
  });

  test("re-shrinking after undo overwrites an archive with the current board snapshot", () => {
    const store = createProjectStore();
    const boardId = "complete-set:board:main:2";
    store.dispatch({ type: "output/enable", outputType: "main" });
    store.dispatch({ type: "output/setQuantity", outputType: "main", quantity: 2 });
    permitResultAsset(store, boardId, "asset-a");
    store.dispatch({ type: "board/selectResult", boardId, assetId: "asset-a" });
    const first = store.dispatch({
      type: "output/setQuantity",
      outputType: "main",
      quantity: 1,
    });
    store.dispatch({
      type: "output/setQuantity",
      outputType: "main",
      quantity: 1,
      acceptedDiffId: first.confirmation?.token,
    });

    expect(store.undo()).toBe(true);
    expect(store.getState().runtime.unlinkedBoards).toEqual([]);
    permitResultAsset(store, boardId, "asset-b");
    store.dispatch({ type: "board/selectResult", boardId, assetId: "asset-b" });
    const second = store.dispatch({
      type: "output/setQuantity",
      outputType: "main",
      quantity: 1,
    });
    store.dispatch({
      type: "output/setQuantity",
      outputType: "main",
      quantity: 1,
      acceptedDiffId: second.confirmation?.token,
    });

    expect(store.getState().runtime.unlinkedBoards).toEqual([
      {
        boardId,
        selectedResultAssetId: "asset-b",
        taskIds: [],
        resultIds: [],
      },
    ]);
  });

  test("disabling requires confirmation and removes only that managed subgraph", () => {
    const store = createProjectStore();
    store.dispatch({ type: "output/enable", outputType: "main" });
    store.dispatch({ type: "output/enable", outputType: "detail" });
    store.dispatch({ type: "output/setQuantity", outputType: "main", quantity: 1 });
    store.dispatch({
      type: "output/setQuantity",
      outputType: "detail",
      quantity: 1,
    });
    permitResultAsset(store, "complete-set:board:main:1", "asset-disable-impact");
    store.dispatch({
      type: "board/selectResult",
      boardId: "complete-set:board:main:1",
      assetId: "asset-disable-impact",
    });

    const pending = store.dispatch({ type: "output/disable", outputType: "main" });
    expect(pending.applied).toBe(false);
    expect(pending.confirmation?.diff.removedNodeIds).toHaveLength(4);
    expect(
      store.getState().project.semanticState.completeSet.selectedOutputTypes,
    ).toEqual(["main", "detail"]);

    store.dispatch({
      type: "output/disable",
      outputType: "main",
      acceptedDiffId: pending.confirmation?.token,
    });

    const project = store.getState().project;
    expect(project.semanticState.completeSet.selectedOutputTypes).toEqual(["detail"]);
    expect(project.semanticState.outputBoards.map((board) => board.outputType)).toEqual([
      "detail",
    ]);
    expect(
      project.semanticState.nodes.filter(
        (node) => node.id.startsWith("complete-set:detail:"),
      ),
    ).toHaveLength(4);
    expect(
      project.semanticState.nodes.some((node) =>
        node.id.startsWith("complete-set:main:"),
      ),
    ).toBe(false);
  });

  test("disable confirms and removes every custom edge incident to removed managed nodes", () => {
    const store = createProjectStore();
    store.dispatch({ type: "output/enable", outputType: "main" });
    store.dispatch({ type: "node/add", node: node("custom-text", "text_layer") });
    store.dispatch({
      type: "edge/connect",
      edge: {
        id: "custom-managed-cross-edge",
        kind: "text_layer",
        sourceNodeId: "custom-text",
        sourcePort: "text",
        targetNodeId: "complete-set:main:output",
        targetPort: "text",
        skuId: null,
      },
    });
    store.dispatch({
      type: "task/statusReceived",
      task: {
        id: "task-custom-result",
        boardId: null,
        status: "succeeded",
        results: [
          {
            id: "result-custom-preserved",
            taskId: "task-custom-result",
            boardId: null,
            assetId: "asset-custom-preserved",
          },
        ],
      },
    });

    const pending = store.dispatch({ type: "output/disable", outputType: "main" });
    expect(pending.applied).toBe(false);
    expect(pending.confirmation?.diff.removedEdgeIds).toContain(
      "custom-managed-cross-edge",
    );

    expect(
      store.dispatch({
        type: "output/disable",
        outputType: "main",
        acceptedDiffId: pending.confirmation?.token,
      }).applied,
    ).toBe(true);
    const state = store.getState();
    expect(state.project.semanticState.edges.map((edge) => edge.id)).not.toContain(
      "custom-managed-cross-edge",
    );
    expect(state.project.semanticState.nodes.map((candidate) => candidate.id)).toContain(
      "custom-text",
    );
    expect(state.runtime.resultHistory.map((result) => result.id)).toContain(
      "result-custom-preserved",
    );
  });

  test("complete-set and advanced views share one store and project expressible edits", () => {
    const store = createProjectStore();
    const views = createProjectViews(store);

    expect(views.completeSet.store).toBe(store);
    expect(views.advanced.store).toBe(store);
    views.completeSet.dispatch({ type: "output/enable", outputType: "main" });
    views.advanced.dispatch({ type: "mode/set", mode: "advanced" });
    views.advanced.dispatch({
      type: "node/update",
      nodeId: "complete-set:main:output",
      patch: {
        prompt: "advanced studio prompt",
        modelProfileId: "model-advanced",
        parameters: { strength: 0.75 },
      },
    });

    expect(views.advanced.getState().project.semanticState.mode).toBe("advanced");
    expect(views.completeSet.getForm()).toMatchObject({
      readOnly: false,
      advancedCustomized: false,
      outputs: [
        {
          outputType: "main",
          prompt: "advanced studio prompt",
          modelProfileId: "model-advanced",
          modelParameters: { strength: 0.75 },
        },
      ],
    });
  });

  test("an unrepresentable advanced topology marks the form read-only", () => {
    const store = createProjectStore();
    store.dispatch({ type: "output/enable", outputType: "main" });
    store.dispatch({ type: "node/add", node: node("custom-text", "text_layer") });
    store.dispatch({
      type: "edge/connect",
      edge: {
        id: "custom-cross-edge",
        kind: "text_layer",
        sourceNodeId: "custom-text",
        sourcePort: "text",
        targetNodeId: "complete-set:main:output",
        targetPort: "text",
        skuId: null,
      },
    });

    const project = store.getState().project;
    expect(project.semanticState.advancedCustomized).toBe(true);
    expect(selectCompleteSetForm(project)).toMatchObject({
      readOnly: true,
      advancedCustomized: true,
    });
  });

  test("managed board representability checks output type, SKU, and sort order", () => {
    const store = createProjectStore();
    store.dispatch({ type: "output/enable", outputType: "main" });
    store.dispatch({ type: "output/setQuantity", outputType: "main", quantity: 1 });
    const baseline = store.getState().project;
    expect(isCompleteSetTopologyRepresentable(baseline)).toBe(true);

    const wrongOutputType = structuredClone(baseline);
    const wrongTypeBoard = wrongOutputType.semanticState.outputBoards[0];
    if (wrongTypeBoard === undefined) throw new Error("expected managed board");
    wrongTypeBoard.outputType = "detail";
    expect(isCompleteSetTopologyRepresentable(wrongOutputType)).toBe(false);

    const wrongSku = structuredClone(baseline);
    const wrongSkuBoard = wrongSku.semanticState.outputBoards[0];
    if (wrongSkuBoard === undefined) throw new Error("expected managed board");
    wrongSkuBoard.skuId = "sku-forged";
    expect(isCompleteSetTopologyRepresentable(wrongSku)).toBe(false);

    const wrongSortOrder = structuredClone(baseline);
    const wrongOrderBoard = wrongSortOrder.semanticState.outputBoards[0];
    if (wrongOrderBoard === undefined) throw new Error("expected managed board");
    wrongOrderBoard.sortOrder = 99;
    expect(isCompleteSetTopologyRepresentable(wrongSortOrder)).toBe(false);
  });

  test("each complete-set board owns a stable distinct output node", () => {
    const store = createProjectStore();
    store.dispatch({ type: "output/enable", outputType: "main" });
    store.dispatch({ type: "output/setQuantity", outputType: "main", quantity: 2 });

    const project = store.getState().project;
    const boards = project.semanticState.outputBoards;
    expect(boards.map((board) => board.outputNodeId)).toEqual([
      "complete-set:main:output:complete-set:board:main:1",
      "complete-set:main:output:complete-set:board:main:2",
    ]);
    expect(
      boards.map((board) => project.semanticState.nodes.find((node) => node.id === board.outputNodeId)?.outputBoardId),
    ).toEqual(boards.map((board) => board.id));
    expect(isCompleteSetTopologyRepresentable(project)).toBe(true);
  });

  test("output configuration keeps each selected output model and prompt independent", () => {
    const store = createProjectStore();
    store.dispatch({ type: "output/enable", outputType: "main" });
    store.dispatch({ type: "output/enable", outputType: "detail" });
    store.dispatch({
      type: "output/configure",
      outputType: "main",
      skuId: null,
      patch: { modelProfileId: "model-main", prompt: "clean studio", width: 1024, height: 1024, aspectRatio: "1:1" },
    } as ProjectAction);

    const [main, detail] = store.getState().project.semanticState.completeSet.outputs;
    expect(main).toMatchObject({ modelProfileId: "model-main", prompt: "clean studio" });
    expect(detail).toMatchObject({ modelProfileId: null, prompt: "" });
  });

  test("an extra board attached to a managed output node makes the form read-only", () => {
    const seeded = createProjectStore();
    seeded.dispatch({ type: "output/enable", outputType: "main" });
    seeded.dispatch({
      type: "output/setQuantity",
      outputType: "main",
      quantity: 1,
    });
    const project = seeded.getState().project;
    project.semanticState.outputBoards.push({
      id: "custom-attached-board",
      outputNodeId: "complete-set:main:output:complete-set:board:main:1",
      outputType: "main",
      skuId: null,
      sortOrder: 1,
      selectedResultAssetId: null,
    });

    expect(isCompleteSetTopologyRepresentable(project)).toBe(false);
    const store = createProjectStore(project);
    store.dispatch({ type: "node/add", node: node("projection-probe", "export") });
    expect(store.getState().project.semanticState.advancedCustomized).toBe(true);
    expect(selectCompleteSetForm(store.getState().project).readOnly).toBe(true);
  });

  test("a board attached to a custom output node is not managed by ID prefix", () => {
    const project = createEmptyProjectState();
    project.semanticState.nodes.push(node("custom-output-node", "main_output"));
    project.semanticState.outputBoards.push({
      id: "complete-set:board:main:custom",
      outputNodeId: "custom-output-node",
      outputType: "main",
      skuId: null,
      sortOrder: 0,
      selectedResultAssetId: null,
    });

    expect(isCompleteSetTopologyRepresentable(project)).toBe(true);
    const store = createProjectStore(project);
    store.dispatch({
      type: "node/add",
      node: node("custom-projection-probe", "export"),
    });
    expect(store.getState().project.semanticState.advancedCustomized).toBe(false);
    expect(selectCompleteSetForm(store.getState().project).readOnly).toBe(false);
  });

  test("rebuild confirms a managed-only replacement and preserves custom nodes and results", () => {
    const store = createProjectStore();
    store.dispatch({ type: "output/enable", outputType: "main" });
    store.dispatch({ type: "output/setQuantity", outputType: "main", quantity: 1 });
    store.dispatch({
      type: "task/statusReceived",
      task: {
        id: "task-rebuild",
        boardId: "complete-set:board:main:1",
        status: "succeeded",
        results: [
          {
            id: "result-rebuild",
            taskId: "task-rebuild",
            boardId: "complete-set:board:main:1",
            assetId: "asset-rebuild",
          },
        ],
      },
    });
    store.dispatch({ type: "node/add", node: node("custom-prompt", "prompt") });
    store.dispatch({
      type: "node/add",
      node: node("custom-generation", "model_generation"),
    });
    store.dispatch({ type: "node/add", node: node("custom-text", "text_layer") });
    store.dispatch({
      type: "edge/connect",
      edge: {
        id: "custom-independent-edge",
        kind: "prompt",
        sourceNodeId: "custom-prompt",
        sourcePort: "prompt",
        targetNodeId: "custom-generation",
        targetPort: "prompt",
        skuId: null,
      },
    });
    store.dispatch({
      type: "edge/connect",
      edge: {
        id: "custom-cross-edge",
        kind: "text_layer",
        sourceNodeId: "custom-text",
        sourcePort: "text",
        targetNodeId: "complete-set:main:output",
        targetPort: "text",
        skuId: null,
      },
    });

    const pending = store.dispatch({ type: "completeSet/rebuild" });
    expect(pending.applied).toBe(false);
    expect(pending.confirmation?.diff.preservedCustomNodeIds).toEqual([
      "custom-prompt",
      "custom-generation",
      "custom-text",
    ]);
    expect(pending.confirmation?.diff.removedBoardIds).toEqual([
      "complete-set:board:main:1",
    ]);

    store.dispatch({
      type: "completeSet/rebuild",
      acceptedDiffId: pending.confirmation?.token,
    });

    const state = store.getState();
    expect(state.project.semanticState.nodes.map((candidate) => candidate.id)).toEqual(
      expect.arrayContaining(["custom-prompt", "custom-generation"]),
    );
    expect(
      state.project.semanticState.edges.map((edge) => edge.id),
    ).toContain("custom-independent-edge");
    expect(state.project.semanticState.edges.map((edge) => edge.id)).toContain(
      "custom-cross-edge",
    );
    expect(
      state.project.semanticState.nodes.filter(
        (candidate) => candidate.managedBy === "complete-set",
      ),
    ).toHaveLength(4);
    expect(state.runtime.resultHistory.map((result) => result.id)).toContain(
      "result-rebuild",
    );
    expect(selectCompleteSetForm(state.project).readOnly).toBe(true);
  });

  test("disable preserves canonical-prefix custom topology not owned by complete-set", () => {
    const project = createEmptyProjectState();
    project.semanticState.nodes.push(
      node("complete-set:main:custom-prompt", "prompt"),
      node("complete-set:main:custom-generation", "model_generation"),
      node("complete-set:main:custom-output", "main_output"),
    );
    project.semanticState.edges.push({
      id: "complete-set:main:edge:custom",
      kind: "prompt",
      sourceNodeId: "complete-set:main:custom-prompt",
      sourcePort: "prompt",
      targetNodeId: "complete-set:main:custom-generation",
      targetPort: "prompt",
      skuId: null,
    });
    project.semanticState.outputBoards.push({
      id: "complete-set:board:main:custom",
      outputNodeId: "complete-set:main:custom-output",
      outputType: "main",
      skuId: null,
      sortOrder: 0,
      selectedResultAssetId: null,
    });
    const store = createProjectStore(project);
    store.dispatch({ type: "output/enable", outputType: "main" });

    expect(store.dispatch({ type: "output/disable", outputType: "main" })).toEqual({
      applied: true,
    });
    const after = store.getState().project.semanticState;
    expect(after.nodes.map((candidate) => candidate.id)).toEqual([
      "complete-set:main:custom-prompt",
      "complete-set:main:custom-generation",
      "complete-set:main:custom-output",
    ]);
    expect(after.edges.map((edge) => edge.id)).toEqual([
      "complete-set:main:edge:custom",
    ]);
    expect(after.outputBoards.map((board) => board.id)).toEqual([
      "complete-set:board:main:custom",
    ]);
  });

  test("quantity shrink preserves a custom board that only shares output metadata", () => {
    const project = createEmptyProjectState();
    project.semanticState.nodes.push(node("custom-main-output", "main_output"));
    project.semanticState.outputBoards.push({
      id: "custom-main-board",
      outputNodeId: "custom-main-output",
      outputType: "main",
      skuId: null,
      sortOrder: 0,
      selectedResultAssetId: null,
    });
    const store = createProjectStore(project);
    store.dispatch({ type: "output/enable", outputType: "main" });
    store.dispatch({ type: "output/setQuantity", outputType: "main", quantity: 2 });

    expect(
      store.dispatch({
        type: "output/setQuantity",
        outputType: "main",
        quantity: 1,
      }),
    ).toEqual({ applied: true });
    expect(
      store.getState().project.semanticState.outputBoards.map((board) => board.id),
    ).toEqual(["custom-main-board", "complete-set:board:main:1"]);
  });

  test("rebuild preserves canonical-prefix custom edges and boards", () => {
    const project = createEmptyProjectState();
    project.semanticState.nodes.push(
      node("complete-set:main:custom-prompt", "prompt"),
      node("complete-set:main:custom-generation", "model_generation"),
      node("complete-set:main:custom-output", "main_output"),
    );
    project.semanticState.edges.push({
      id: "complete-set:main:edge:custom",
      kind: "prompt",
      sourceNodeId: "complete-set:main:custom-prompt",
      sourcePort: "prompt",
      targetNodeId: "complete-set:main:custom-generation",
      targetPort: "prompt",
      skuId: null,
    });
    project.semanticState.outputBoards.push({
      id: "complete-set:board:main:custom",
      outputNodeId: "complete-set:main:custom-output",
      outputType: "main",
      skuId: null,
      sortOrder: 0,
      selectedResultAssetId: null,
    });
    const store = createProjectStore(project);
    store.dispatch({ type: "output/enable", outputType: "main" });
    const pending = store.dispatch({ type: "completeSet/rebuild" });

    expect(
      store.dispatch({
        type: "completeSet/rebuild",
        acceptedDiffId: pending.confirmation?.token,
      }).applied,
    ).toBe(true);
    const after = store.getState().project.semanticState;
    expect(after.nodes.map((candidate) => candidate.id)).toEqual(
      expect.arrayContaining([
        "complete-set:main:custom-prompt",
        "complete-set:main:custom-generation",
        "complete-set:main:custom-output",
      ]),
    );
    expect(after.edges.map((edge) => edge.id)).toContain(
      "complete-set:main:edge:custom",
    );
    expect(after.outputBoards.map((board) => board.id)).toContain(
      "complete-set:board:main:custom",
    );
  });

  test("undo and redo cover graph, layout, text, and composition changes", () => {
    const project = createEmptyProjectState();
    project.semanticState.nodes.push(node("text-node", "text_layer"));
    project.layoutState.textSnapshots.push({
      id: "text-1",
      nodeId: "text-node",
      content: "before",
      fontAssetId: null,
      fontFamily: "Noto Sans CJK SC",
      fontVersion: "sha256:2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b",
      boxWidth: 0.5,
      lines: [{ text: "before", x: 10, y: 20, width: 100 }],
      fontSize: 16,
      color: "#111111",
      letterSpacing: 0,
      lineHeight: 1.2,
      align: "left",
      baseline: "alphabetic",
      zBand: "above-product",
      sortOrder: 0,
    });
    const beforeLayout = structuredClone(DEFAULT_COMPOSITION_LAYOUT);
    project.semanticState.compositionGroups.push({
      id: "group-1",
      skuIds: [],
      productLayerIds: [],
      layoutHash: compositionLayoutHash(beforeLayout),
      layout: beforeLayout,
    });
    const store = createProjectStore(project);

    store.dispatch({ type: "node/add", node: node("custom-node", "text_layer") });
    store.dispatch({
      type: "node/move",
      nodeId: "custom-node",
      position: { x: 0.25, y: 0.75 },
    });
    store.dispatch({
      type: "text/update",
      layerId: "text-1",
      patch: { content: "after", fontSize: 24 },
    });
    const afterLayout = { ...structuredClone(beforeLayout), baseline: 0.7 };
    store.dispatch({
      type: "composition/update",
      groupId: "group-1",
      layout: afterLayout,
    });

    expect(store.canUndo()).toBe(true);
    expect(store.undo()).toBe(true);
    expect(
      store.getState().project.semanticState.compositionGroups[0]?.layoutHash,
    ).toBe(compositionLayoutHash(beforeLayout));
    expect(store.undo()).toBe(true);
    expect(store.getState().project.layoutState.textSnapshots[0]?.content).toBe(
      "before",
    );
    expect(store.undo()).toBe(true);
    expect(store.getState().project.layoutState.nodePositions["custom-node"]).toBe(
      undefined,
    );
    expect(store.undo()).toBe(true);
    expect(
      store
        .getState()
        .project.semanticState.nodes.some((candidate) => candidate.id === "custom-node"),
    ).toBe(false);
    expect(store.canUndo()).toBe(false);

    expect(store.redo()).toBe(true);
    expect(store.redo()).toBe(true);
    expect(store.redo()).toBe(true);
    expect(store.redo()).toBe(true);
    expect(store.getState().project.layoutState.nodePositions["custom-node"]).toEqual({
      x: 0.25,
      y: 0.75,
    });
    expect(store.getState().project.layoutState.textSnapshots[0]).toMatchObject({
      content: "after",
      fontSize: 24,
      lines: [{ text: "after", x: 10, y: 20, width: 100 }],
    });
    expect(
      store.getState().project.semanticState.compositionGroups[0]?.layoutHash,
    ).toBe(compositionLayoutHash(afterLayout));
    expect(store.canRedo()).toBe(false);
  });

  test("text patches keep content and explicit lines consistent or reject new auto-layout", () => {
    const project = createEmptyProjectState();
    project.semanticState.nodes.push(node("text-node", "text_layer"));
    project.layoutState.textSnapshots.push({
      id: "text-1",
      nodeId: "text-node",
      content: "first\nsecond",
      fontAssetId: null,
      fontFamily: "Noto Sans CJK SC",
      fontVersion: "sha256:2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b",
      boxWidth: 240,
      lines: [
        { text: "first", x: 10, y: 20, width: 100 },
        { text: "second", x: 10, y: 50, width: 120 },
      ],
      fontSize: 16,
      color: "#111111",
      letterSpacing: 0,
      lineHeight: 1.2,
      align: "left",
      baseline: "alphabetic",
      zBand: "above-product",
      sortOrder: 0,
    });
    const store = createProjectStore(project);

    store.dispatch({
      type: "text/update",
      layerId: "text-1",
      patch: { lines: [
        { text: "甲", x: 10, y: 20, width: 100 },
        { text: "乙", x: 10, y: 50, width: 120 },
      ] },
    });
    expect(store.getState().project.layoutState.textSnapshots[0]?.content).toBe("甲\n乙");
    expect(() => store.dispatch({
      type: "text/update",
      layerId: "text-1",
      patch: { content: "only one line" },
    })).toThrowError("文字行数变化需要逐行设置位置和宽度");
  });

  test("lineHeight edits persist deterministic y positions used by projection", () => {
    const project = createEmptyProjectState();
    project.semanticState.nodes.push(node("text-node", "text_layer"));
    project.layoutState.textSnapshots.push({
      id: "text-1",
      nodeId: "text-node",
      content: "one\ntwo\nthree",
      fontAssetId: null,
      fontFamily: "Noto Sans CJK SC",
      fontVersion: "sha256:2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b",
      boxWidth: 240,
      lines: [
        { text: "one", x: 10, y: 20, width: 100 },
        { text: "two", x: 10, y: 80, width: 100 },
        { text: "three", x: 10, y: 140, width: 100 },
      ],
      fontSize: 20,
      color: "#111111",
      letterSpacing: 0,
      lineHeight: 1,
      align: "left",
      baseline: "top",
      zBand: "above-product",
      sortOrder: 0,
    });
    const store = createProjectStore(project);
    store.dispatch({ type: "text/update", layerId: "text-1", patch: { lineHeight: 1.5 } });
    const updated = store.getState().project.layoutState.textSnapshots[0];
    expect(updated?.lines.map((line) => line.y)).toEqual([20, 50, 80]);
    expect(
      createPresentationPlan(store.getState().project).descriptors
        .filter((descriptor) => descriptor.role === "text")
        .map((descriptor) => descriptor.properties.top),
    ).toEqual([20, 50, 80]);
  });

  test("upload, paid generation, and server task actions never enter undo history", () => {
    const store = createProjectStore();

    store.dispatch({ type: "upload/record", uploadId: "upload-1" });
    store.dispatch({
      type: "generation/paidRequested",
      requestId: "paid-request-1",
    });
    store.dispatch({
      type: "task/statusReceived",
      task: {
        id: "task-server",
        boardId: null,
        status: "running",
        results: [],
      },
    });

    expect(store.canUndo()).toBe(false);
    expect(store.getState().runtime.uploadIds).toEqual(["upload-1"]);
    expect(store.getState().runtime.paidGenerationRequestIds).toEqual([
      "paid-request-1",
    ]);
    expect(store.getState().runtime.taskSnapshots["task-server"]?.status).toBe(
      "running",
    );
  });

  test("repeating an identical immutable task result is an idempotent no-op", () => {
    const store = createProjectStore();
    const action = {
      type: "task/statusReceived" as const,
      task: {
        id: "task-idempotent",
        boardId: null,
        status: "succeeded" as const,
        results: [
          {
            id: "result-idempotent",
            taskId: "task-idempotent",
            boardId: null,
            assetId: "asset-idempotent",
          },
        ],
      },
    };

    expect(store.dispatch(action)).toEqual({ applied: true });
    const beforeReplay = store.getState();
    expect(store.dispatch(structuredClone(action))).toEqual({ applied: false });
    expect(store.getState()).toEqual(beforeReplay);
  });

  test("an immutable result ID rejects different contents without changing state", () => {
    const store = createProjectStore();
    store.dispatch({
      type: "task/statusReceived",
      task: {
        id: "task-result-owner",
        boardId: null,
        status: "succeeded",
        results: [
          {
            id: "result-immutable",
            taskId: "task-result-owner",
            boardId: null,
            assetId: "asset-original",
          },
        ],
      },
    });
    const beforeConflict = store.getState();

    expect(() =>
      store.dispatch({
        type: "task/statusReceived",
        task: {
          id: "task-result-owner",
          boardId: null,
          status: "succeeded",
          results: [
            {
              id: "result-immutable",
              taskId: "task-result-owner",
              boardId: null,
              assetId: "asset-forged",
            },
          ],
        },
      }),
    ).toThrowError(/immutable result id conflict result-immutable/);
    expect(store.getState()).toEqual(beforeConflict);
  });

  test("project replacement clears history and runtime selection", () => {
    const store = createProjectStore();
    store.dispatch({ type: "node/add", node: node("selected-node", "prompt") });
    store.dispatch({
      type: "runtime/select",
      nodeId: "selected-node",
      boardId: null,
    });
    expect(store.canUndo()).toBe(true);
    expect(store.getState().runtime.selectedNodeId).toBe("selected-node");

    store.replaceProject(createEmptyProjectState());

    expect(store.canUndo()).toBe(false);
    expect(store.canRedo()).toBe(false);
    expect(store.getState().runtime.selectedNodeId).toBeNull();
    expect(store.getState().runtime.selectedBoardId).toBeNull();
  });

  test("the shared Python fixture validates and round-trips without wire drift", () => {
    const fixture: unknown = JSON.parse(projectStateFixture);

    const parsed = parseProjectState(fixture);
    const serialized = serializeProjectState(parsed);

    expect(parsed).toEqual(fixture);
    expect(JSON.parse(serialized)).toEqual(fixture);
    expect(serialized).toContain('"semanticState"');
    expect(serialized).not.toContain("semantic_state");
  });

  test("runtime validation rejects unknown, snake_case, and Fabric-shaped state", () => {
    const parsed = parseProjectState(JSON.parse(projectStateFixture));
    const snakeCaseWire = {
      schemaVersion: parsed.schemaVersion,
      semantic_state: parsed.semanticState,
      layoutState: parsed.layoutState,
    };
    expect(() => parseProjectState(snakeCaseWire)).toThrow(/unknown key.*semantic_state/i);

    const unknownWire = { ...parsed, runtime: { selectedNodeId: null } };
    expect(() => parseProjectState(unknownWire)).toThrow(/unknown key.*runtime/i);

    const fabricWire = structuredClone(parsed);
    const firstNode = fabricWire.semanticState.nodes[0];
    if (firstNode === undefined) {
      throw new Error("fixture must contain a node");
    }
    firstNode.parameters = { objects: [] };
    expect(() => parseProjectState(fabricWire)).toThrow(/Fabric marker.*objects/i);
  });

  test("runtime validation rejects fractional fonts, multiline rows, drift, and unsafe spacing", () => {
    const candidate = (): any => JSON.parse(projectStateFixture);
    const mutations: Array<(value: any) => void> = [
      (value) => { value.layoutState.textSnapshots[0].fontSize = 32.5; },
      (value) => { value.layoutState.textSnapshots[0].fontSize = true; },
      (value) => { value.layoutState.textSnapshots[0].lines[0].text = "bad\nrow"; },
      (value) => { value.layoutState.textSnapshots[0].content = "different"; },
      (value) => {
        value.layoutState.textSnapshots[0].content = "e\u0301";
        value.layoutState.textSnapshots[0].lines[0].text = "e\u0301";
        value.layoutState.textSnapshots[0].letterSpacing = 1;
      },
    ];
    for (const mutate of mutations) {
      const value = candidate();
      mutate(value);
      expect(() => parseProjectState(value)).toThrow();
    }
  });

  test("runtime validation rejects every dangling internal project reference", () => {
    const cases: Array<{
      label: string;
      mutate(project: ReturnType<typeof parseProjectState>): void;
    }> = [
      {
        label: "edge source node",
        mutate: (project) => {
          const edge = project.semanticState.edges[0];
          if (edge !== undefined) edge.sourceNodeId = "missing-node";
        },
      },
      {
        label: "edge target node",
        mutate: (project) => {
          const edge = project.semanticState.edges[0];
          if (edge !== undefined) edge.targetNodeId = "missing-node";
        },
      },
      {
        label: "output board node",
        mutate: (project) => {
          const board = project.semanticState.outputBoards[0];
          if (board !== undefined) board.outputNodeId = "missing-node";
        },
      },
      {
        label: "node output board",
        mutate: (project) => {
          const candidate = project.semanticState.nodes[0];
          if (candidate !== undefined) candidate.outputBoardId = "missing-board";
        },
      },
      {
        label: "node text snapshot",
        mutate: (project) => {
          const candidate = project.semanticState.nodes[0];
          if (candidate !== undefined) candidate.textSnapshotId = "missing-text";
        },
      },
      {
        label: "text snapshot node",
        mutate: (project) => {
          const snapshot = project.layoutState.textSnapshots[0];
          if (snapshot !== undefined) snapshot.nodeId = "missing-node";
        },
      },
      {
        label: "node composition group",
        mutate: (project) => {
          const candidate = project.semanticState.nodes[0];
          if (candidate !== undefined) {
            candidate.compositionGroupId = "missing-composition";
          }
        },
      },
      {
        label: "complete-set output composition group",
        mutate: (project) => {
          const output = project.semanticState.completeSet.outputs[0];
          if (output !== undefined) {
            output.compositionGroupId = "missing-composition";
          }
        },
      },
      {
        label: "composition product layer",
        mutate: (project) => {
          const group = project.semanticState.compositionGroups[0];
          if (group !== undefined) group.productLayerIds = ["missing-layer"];
        },
      },
      {
        label: "product layer composition group",
        mutate: (project) => {
          const layer = project.layoutState.productLayers[0];
          if (layer !== undefined) {
            layer.compositionGroupId = "missing-composition";
          }
        },
      },
      {
        label: "product layer transform",
        mutate: (project) => {
          const layer = project.layoutState.productLayers[0];
          if (layer !== undefined) layer.transformId = "missing-transform";
        },
      },
      {
        label: "node position",
        mutate: (project) => {
          project.layoutState.nodePositions["missing-node"] = { x: 0, y: 0 };
        },
      },
    ];

    for (const referenceCase of cases) {
      const candidate = parseProjectState(JSON.parse(projectStateFixture));
      referenceCase.mutate(candidate);
      expect(
        () => parseProjectState(candidate),
        referenceCase.label,
      ).toThrowError(/references unknown/i);
    }
  });

  test("typed ports are validated before an edge can mutate the reducer", () => {
    const store = createProjectStore();
    store.dispatch({ type: "node/add", node: node("source-prompt", "prompt") });
    store.dispatch({
      type: "node/add",
      node: node("target-generation", "model_generation"),
    });
    const invalidEdge = {
      id: "invalid-ports",
      kind: "prompt",
      sourceNodeId: "source-prompt",
      sourcePort: "output",
      targetNodeId: "target-generation",
      targetPort: "input",
      skuId: null,
    } as unknown as TypedEdge;

    expect(() =>
      store.dispatch({ type: "edge/connect", edge: invalidEdge }),
    ).toThrow(/invalid ports for prompt/i);
    expect(
      store
        .getState()
        .project.semanticState.edges.some((edge) => edge.id === "invalid-ports"),
    ).toBe(false);
  });

  test("incompatible node kinds cannot connect even when their raw ports look valid", () => {
    const store = createProjectStore();
    store.dispatch({ type: "node/add", node: node("source-product", "product_source") });
    store.dispatch({ type: "node/add", node: node("target-output", "detail_output") });

    expect(() => store.dispatch({
      type: "edge/connect",
      edge: {
        id: "invalid-product-to-output",
        kind: "product_asset",
        sourceNodeId: "source-product",
        sourcePort: "product",
        targetNodeId: "target-output",
        targetPort: "reference",
        skuId: null,
      },
    })).toThrow(/incompatible node connection/i);
  });

  test("node parameter patches merge dimensions without deleting existing generation settings", () => {
    const store = createProjectStore();
    const generation = node("advanced-generation", "model_generation");
    generation.parameters = { strength: 0.7, width: 1024 };
    store.dispatch({ type: "node/add", node: generation });

    store.dispatch({
      type: "node/update",
      nodeId: generation.id,
      patch: { parameters: { height: 1536 } },
    });

    expect(store.getState().project.semanticState.nodes.find((item) => item.id === generation.id)?.parameters).toEqual({
      strength: 0.7,
      width: 1024,
      height: 1536,
    });
  });

  test("only server-permitted result versions can be selected and runtime permissions stay out of project serialization", () => {
    const store = createProjectStore();
    store.dispatch({ type: "output/enable", outputType: "main" });
    store.dispatch({ type: "output/setQuantity", outputType: "main", quantity: 1 });
    const boardId = "complete-set:board:main:1";
    const before = serializeProjectState(store.getState().project);
    store.dispatch({
      type: "runtime/setAllowedResultAssets",
      boardId,
      assetIds: ["asset-approved"],
    });

    expect(serializeProjectState(store.getState().project)).toBe(before);
    expect(() => store.dispatch({
      type: "board/selectResult", boardId, assetId: "asset-forged",
    })).toThrow(/not a permitted result version/i);
    store.dispatch({ type: "board/selectResult", boardId, assetId: "asset-approved" });
    expect(store.getState().project.semanticState.outputBoards[0]?.selectedResultAssetId).toBe("asset-approved");
  });

  test("result selections reject non-null assets until the board result whitelist has loaded", () => {
    const store = createProjectStore();
    store.dispatch({ type: "output/enable", outputType: "main" });
    store.dispatch({ type: "output/setQuantity", outputType: "main", quantity: 1 });
    const boardId = "complete-set:board:main:1";

    expect(() => store.dispatch({
      type: "board/selectResult", boardId, assetId: "asset-before-result-load",
    })).toThrow(/permitted result version/i);
    expect(() => store.dispatch({
      type: "board/selectResult", boardId, assetId: null,
    })).not.toThrow();
  });

  test("system cutout nodes cannot be user-added or patched", () => {
    const store = createProjectStore();
    const systemCutout = node("main-product-cutout", "auto_cutout");
    systemCutout.assetId = "cutout-a";

    expect(() => store.dispatch({ type: "node/add", node: systemCutout })).toThrow(/auto cutout.*projected/i);
    const projected = createEmptyProjectState();
    const systemSource = node("main-product-source", "product_source");
    systemSource.assetId = "source-a";
    projected.semanticState.nodes.push(systemSource, systemCutout);
    projected.semanticState.edges.push({
      id: "main-product-source-cutout", kind: "product_asset",
      sourceNodeId: systemSource.id, sourcePort: "product",
      targetNodeId: systemCutout.id, targetPort: "reference", skuId: null,
    });
    projected.layoutState.objectTransforms["main-product"] = { x: 0.5, y: 0.5, scale: 1, rotation: 0 };
    projected.layoutState.productLayers.push({
      id: "main-product", sourceAssetId: "source-a", renderAssetId: "cutout-a",
      allowOpaqueFallback: false, skuId: null, compositionGroupId: null,
      transformId: "main-product", locked: true,
    });
    const projectedStore = createProjectStore(projected);
    expect(() => projectedStore.dispatch({
      type: "node/update", nodeId: "main-product-cutout", patch: { assetId: "forged" },
    })).toThrow(/system product pipeline/i);
    expect(() => projectedStore.dispatch({
      type: "node/move", nodeId: "main-product-cutout", position: { x: 1, y: 2 },
    })).toThrow(/system product pipeline/i);
    expect(() => projectedStore.dispatch({
      type: "edge/connect",
      edge: {
        id: "forged-system-route", kind: "product_asset",
        sourceNodeId: "main-product-source", sourcePort: "product",
        targetNodeId: "main-product-cutout", targetPort: "reference", skuId: null,
      },
    })).toThrow(/system product pipeline/i);
  });

  test("rejects duplicate singleton graph inputs before they can become first-wins", () => {
    const projected = createEmptyProjectState();
    const prompt = node("prompt", "prompt");
    const generation = node("generation", "model_generation");
    projected.semanticState.nodes.push(prompt, generation);
    const store = createProjectStore(projected);
    const first = {
      id: "prompt-route-one", kind: "prompt" as const,
      sourceNodeId: prompt.id, sourcePort: "prompt" as const,
      targetNodeId: generation.id, targetPort: "prompt" as const, skuId: null,
    };
    store.dispatch({ type: "edge/connect", edge: first });
    expect(() => store.dispatch({
      type: "edge/connect", edge: { ...first, id: "prompt-route-two" },
    })).toThrow(/duplicate singleton input/i);
  });

  test("persisted graphs reject a product source that bypasses auto cutout", () => {
    const persisted = JSON.parse(projectStateFixture);
    persisted.semanticState.edges[0] = {
      ...persisted.semanticState.edges[0],
      kind: "product_asset",
      sourceNodeId: "node-product-1",
      sourcePort: "product",
      targetPort: "reference",
    };

    expect(() => parseProjectState(persisted)).toThrow(/incompatible node connection/i);
  });

  test("persisted advanced graphs require every auto cutout to retain its product route", () => {
    const persisted = JSON.parse(projectStateFixture);
    persisted.semanticState.mode = "advanced";
    persisted.semanticState.nodes.push({
      id: "advanced-cutout", kind: "auto_cutout", managedBy: null, skuId: null,
      assetId: "cutout-asset", modelProfileId: null, prompt: null, compositionGroupId: null,
      textSnapshotId: null, outputBoardId: null, parameters: {},
    });

    expect(() => parseProjectState(persisted)).toThrow(/auto cutout.*product route/i);
  });

  test("the exported reducer is pure and uses deterministic managed IDs", () => {
    const current = createProjectStore().getState();
    const before = structuredClone(current);

    const reduction = reduceProjectState(current, {
      type: "output/enable",
      outputType: "main",
    });

    expect(current).toEqual(before);
    expect(reduction.state).not.toBe(current);
    expect(reduction.state.project.semanticState.nodes.map((item) => item.id)).toEqual([
      "complete-set:main:prompt",
      "complete-set:main:generation",
      "complete-set:main:output",
    ]);
  });

  test("store construction and replacement revalidate persisted project wire", () => {
    const invalid = parseProjectState(JSON.parse(projectStateFixture));
    const firstNode = invalid.semanticState.nodes[0];
    if (firstNode === undefined) {
      throw new Error("fixture must contain a node");
    }
    firstNode.parameters = { version: "fabric-blob" };

    expect(() => createProjectStore(invalid)).toThrow(/Fabric marker.*version/i);

    const store = createProjectStore();
    expect(() => store.replaceProject(invalid)).toThrow(/Fabric marker.*version/i);
    expect(store.getState().project).toEqual(createEmptyProjectState());
  });

  test("main only wires and returns the supplied shared project store", () => {
    document.body.innerHTML = '<div id="canvas-app"></div>';
    const store = createProjectStore();

    const mounted = mountCanvas(store);

    expect(mounted).toBe(store);
    expect(document.querySelector("#canvas-app")?.innerHTML).toContain(
      "Loading Product Canvas",
    );
  });

  test("project actions cannot inject invalid persisted wire", () => {
    const store = createProjectStore();
    const invalidNode = node("unsafe-node", "prompt");
    invalidNode.parameters = { objects: [] };

    expect(() =>
      store.dispatch({ type: "node/add", node: invalidNode }),
    ).toThrow(/Fabric marker.*objects/i);
    expect(
      store
        .getState()
        .project.semanticState.nodes.some((candidate) => candidate.id === "unsafe-node"),
    ).toBe(false);
    expect(store.canUndo()).toBe(false);
  });

  test("confirmation challenges distinguish the reviewer's real FNV collision", () => {
    const challengeForAsset = (assetId: string): string => {
      const store = createProjectStore(createEmptyProjectState(), {
        projectId: "project-collision",
        revision: 7,
      });
      store.dispatch({ type: "output/enable", outputType: "main" });
      store.dispatch({
        type: "output/setQuantity",
        outputType: "main",
        quantity: 2,
      });
      permitResultAsset(store, "complete-set:board:main:2", assetId);
      store.dispatch({
        type: "board/selectResult",
        boardId: "complete-set:board:main:2",
        assetId,
      });
      const pending = store.dispatch({
        type: "output/setQuantity",
        outputType: "main",
        quantity: 1,
      });
      const token = pending.confirmation?.token;
      if (token === undefined) {
        throw new Error("expected a confirmation challenge");
      }
      expect(store.getState().runtime.pendingConfirmation?.token).toBe(token);
      return token;
    };

    const first = challengeForAsset("asset-2e793102-0377d0ee");
    const second = challengeForAsset("asset-b86be824-688e58f3");

    expect(first).not.toBe(second);
    expect(first).not.toBe("canvas-diff:4485d054");
    expect(second).not.toBe("canvas-diff:4485d054");
  });

  test("a consumed challenge cannot replay after quantity is restored", () => {
    const store = createProjectStore(createEmptyProjectState(), {
      projectId: "project-replay",
      revision: 3,
    });
    store.dispatch({ type: "output/enable", outputType: "main" });
    store.dispatch({ type: "output/setQuantity", outputType: "main", quantity: 2 });
    permitResultAsset(store, "complete-set:board:main:2", "asset-replay");
    store.dispatch({
      type: "board/selectResult",
      boardId: "complete-set:board:main:2",
      assetId: "asset-replay",
    });
    const pending = store.dispatch({
      type: "output/setQuantity",
      outputType: "main",
      quantity: 1,
    });
    const token = pending.confirmation?.token;
    if (token === undefined) {
      throw new Error("expected a confirmation challenge");
    }
    expect(
      store.dispatch({
        type: "output/setQuantity",
        outputType: "main",
        quantity: 1,
        acceptedDiffId: token,
      }).applied,
    ).toBe(true);
    expect(store.getState().runtime.pendingConfirmation).toBeNull();
    store.dispatch({ type: "output/setQuantity", outputType: "main", quantity: 2 });
    permitResultAsset(store, "complete-set:board:main:2", "asset-replay-restored");
    store.dispatch({
      type: "board/selectResult",
      boardId: "complete-set:board:main:2",
      assetId: "asset-replay-restored",
    });
    const beforeReplay = store.getState();

    const replay = store.dispatch({
      type: "output/setQuantity",
      outputType: "main",
      quantity: 1,
      acceptedDiffId: token,
    });

    expect(replay.applied).toBe(false);
    expect(replay.confirmation).toBeUndefined();
    expect(store.getState()).toEqual(beforeReplay);
  });

  test("a challenge is bound to project identity, revision, and base state", () => {
    const project = createEmptyProjectState();
    const source = createProjectStore(project, {
      projectId: "project-a",
      revision: 11,
    });
    source.dispatch({ type: "output/enable", outputType: "main" });
    source.dispatch({ type: "output/setQuantity", outputType: "main", quantity: 2 });
    permitResultAsset(source, "complete-set:board:main:2", "asset-project-a");
    source.dispatch({
      type: "board/selectResult",
      boardId: "complete-set:board:main:2",
      assetId: "asset-project-a",
    });
    const sourcePending = source.dispatch({
      type: "output/setQuantity",
      outputType: "main",
      quantity: 1,
    });
    const token = sourcePending.confirmation?.token;
    if (token === undefined) {
      throw new Error("expected a confirmation challenge");
    }

    const other = createProjectStore(project, {
      projectId: "project-b",
      revision: 12,
    });
    other.dispatch({ type: "output/enable", outputType: "main" });
    other.dispatch({ type: "output/setQuantity", outputType: "main", quantity: 2 });
    permitResultAsset(other, "complete-set:board:main:2", "asset-project-b");
    other.dispatch({
      type: "board/selectResult",
      boardId: "complete-set:board:main:2",
      assetId: "asset-project-b",
    });
    const otherBefore = other.getState();
    expect(
      other.dispatch({
        type: "output/setQuantity",
        outputType: "main",
        quantity: 1,
        acceptedDiffId: token,
      }),
    ).toEqual({ applied: false });
    expect(other.getState()).toEqual(otherBefore);

    source.dispatch({ type: "mode/set", mode: "advanced" });
    const staleBefore = source.getState();
    expect(source.getState().runtime.pendingConfirmation).toBeNull();
    expect(
      source.dispatch({
        type: "output/setQuantity",
        outputType: "main",
        quantity: 1,
        acceptedDiffId: token,
      }),
    ).toEqual({ applied: false });
    expect(source.getState()).toEqual(staleBefore);
  });

  test("a challenge only accepts its exact destructive action payload", () => {
    const store = createProjectStore(createEmptyProjectState(), {
      projectId: "project-action",
      revision: 5,
    });
    store.dispatch({ type: "output/enable", outputType: "main" });
    store.dispatch({ type: "output/setQuantity", outputType: "main", quantity: 3 });
    permitResultAsset(store, "complete-set:board:main:3", "asset-exact-action");
    store.dispatch({
      type: "board/selectResult",
      boardId: "complete-set:board:main:3",
      assetId: "asset-exact-action",
    });
    const pending = store.dispatch({
      type: "output/setQuantity",
      outputType: "main",
      quantity: 1,
    });
    const token = pending.confirmation?.token;
    if (token === undefined) {
      throw new Error("expected a confirmation challenge");
    }
    const beforeWrongAction = store.getState();

    const wrongQuantity = store.dispatch({
      type: "output/setQuantity",
      outputType: "main",
      quantity: 2,
      acceptedDiffId: token,
    });

    expect(wrongQuantity).toEqual({ applied: false });
    expect(store.getState()).toEqual(beforeWrongAction);
    expect(store.getState().runtime.pendingConfirmation?.token).toBe(token);
  });

  test("getState returns a deep snapshot that cannot mutate store or history", () => {
    const store = createProjectStore();
    store.dispatch({ type: "output/enable", outputType: "main" });
    store.dispatch({ type: "output/setQuantity", outputType: "main", quantity: 1 });
    const exposed = store.getState();
    const exposedAgain = store.getState();

    expect(exposedAgain).not.toBe(exposed);
    expect(exposedAgain.project).not.toBe(exposed.project);
    const exposedNode = exposed.project.semanticState.nodes[0];
    const exposedOutput = exposed.project.semanticState.completeSet.outputs[0];
    if (exposedNode === undefined || exposedOutput === undefined) {
      throw new Error("expected managed project state");
    }
    exposedNode.parameters = { objects: [] };
    exposed.project.semanticState.nodes.push(structuredClone(exposedNode));
    exposedOutput.quantity = 99;
    exposed.runtime.uploadIds.push("external-upload");

    const internal = store.getState();
    expect(internal.project.semanticState.nodes).toHaveLength(4);
    expect(internal.project.semanticState.nodes[0]?.parameters).toEqual({});
    expect(internal.project.semanticState.completeSet.outputs[0]?.quantity).toBe(1);
    expect(internal.runtime.uploadIds).toEqual([]);
    expect(store.canUndo()).toBe(true);
    expect(store.undo()).toBe(true);
    expect(store.getState().project.semanticState.outputBoards).toEqual([]);
  });

  test("confirmation results cannot mutate the stored pending challenge", () => {
    const store = createProjectStore();
    store.dispatch({ type: "output/enable", outputType: "main" });
    store.dispatch({ type: "output/setQuantity", outputType: "main", quantity: 2 });
    permitResultAsset(store, "complete-set:board:main:2", "asset-pending");
    store.dispatch({
      type: "board/selectResult",
      boardId: "complete-set:board:main:2",
      assetId: "asset-pending",
    });
    const pending = store.dispatch({
      type: "output/setQuantity",
      outputType: "main",
      quantity: 1,
    });
    const confirmation = pending.confirmation;
    if (confirmation === undefined) {
      throw new Error("expected confirmation");
    }

    confirmation.diff.removedBoardIds.push("forged-board");
    confirmation.diff.selectedResultAssetIds.push("forged-asset");

    expect(
      store.getState().runtime.pendingConfirmation?.diff.removedBoardIds,
    ).toEqual(["complete-set:board:main:2"]);
    expect(
      store.getState().runtime.pendingConfirmation?.diff.selectedResultAssetIds,
    ).toEqual(["asset-pending"]);
  });

  test("persisted wire rejects duplicate IDs within every ID domain", () => {
    const cases: Array<{
      label: string;
      mutate(project: ReturnType<typeof parseProjectState>): void;
    }> = [
      {
        label: "node",
        mutate: (project) => {
          const value = project.semanticState.nodes[0];
          if (value !== undefined) project.semanticState.nodes.push(structuredClone(value));
        },
      },
      {
        label: "edge",
        mutate: (project) => {
          const value = project.semanticState.edges[0];
          if (value !== undefined) project.semanticState.edges.push(structuredClone(value));
        },
      },
      {
        label: "output board",
        mutate: (project) => {
          const value = project.semanticState.outputBoards[0];
          if (value !== undefined)
            project.semanticState.outputBoards.push(structuredClone(value));
        },
      },
      {
        label: "composition group",
        mutate: (project) => {
          const value = project.semanticState.compositionGroups[0];
          if (value !== undefined)
            project.semanticState.compositionGroups.push(structuredClone(value));
        },
      },
      {
        label: "product layer",
        mutate: (project) => {
          const value = project.layoutState.productLayers[0];
          if (value !== undefined)
            project.layoutState.productLayers.push(structuredClone(value));
        },
      },
      {
        label: "text snapshot",
        mutate: (project) => {
          const value = project.layoutState.textSnapshots[0];
          if (value !== undefined)
            project.layoutState.textSnapshots.push(structuredClone(value));
        },
      },
    ];

    for (const duplicateCase of cases) {
      const candidate = parseProjectState(JSON.parse(projectStateFixture));
      duplicateCase.mutate(candidate);
      expect(
        () => createProjectStore(candidate),
        `expected duplicate ${duplicateCase.label} rejection`,
      ).toThrow(new RegExp(`duplicate ${duplicateCase.label} id`, "i"));
    }
  });

  test("enable rejects canonical node and edge IDs owned by custom topology", () => {
    const nodeCollision = createProjectStore();
    nodeCollision.dispatch({
      type: "node/add",
      node: node("complete-set:main:prompt", "prompt"),
    });
    const nodeBefore = nodeCollision.getState();
    const nodeCanUndo = nodeCollision.canUndo();
    expect(() =>
      nodeCollision.dispatch({ type: "output/enable", outputType: "main" }),
    ).toThrow(/duplicate node id.*complete-set:main:prompt/i);
    expect(nodeCollision.getState()).toEqual(nodeBefore);
    expect(nodeCollision.canUndo()).toBe(nodeCanUndo);

    const edgeCollision = createProjectStore();
    edgeCollision.dispatch({ type: "node/add", node: node("custom-prompt", "prompt") });
    edgeCollision.dispatch({
      type: "node/add",
      node: node("custom-generation", "model_generation"),
    });
    edgeCollision.dispatch({
      type: "edge/connect",
      edge: {
        id: "complete-set:main:edge:prompt",
        kind: "prompt",
        sourceNodeId: "custom-prompt",
        sourcePort: "prompt",
        targetNodeId: "custom-generation",
        targetPort: "prompt",
        skuId: null,
      },
    });
    const edgeBefore = edgeCollision.getState();
    const edgeCanUndo = edgeCollision.canUndo();
    expect(() =>
      edgeCollision.dispatch({ type: "output/enable", outputType: "main" }),
    ).toThrow(/duplicate edge id.*complete-set:main:edge:prompt/i);
    expect(edgeCollision.getState()).toEqual(edgeBefore);
    expect(edgeCollision.canUndo()).toBe(edgeCanUndo);
  });

  test("quantity rejects a canonical board ID already owned by a custom board", () => {
    const project = createEmptyProjectState();
    project.semanticState.nodes.push(node("custom-output", "main_output"));
    project.semanticState.outputBoards.push({
      id: "complete-set:board:main:1",
      outputNodeId: "custom-output",
      outputType: "main",
      skuId: null,
      sortOrder: 0,
      selectedResultAssetId: null,
    });
    const store = createProjectStore(project);
    store.dispatch({ type: "output/enable", outputType: "main" });
    const before = store.getState();
    const canUndo = store.canUndo();

    expect(() =>
      store.dispatch({
        type: "output/setQuantity",
        outputType: "main",
        quantity: 1,
      }),
    ).toThrow(/managed board id collision.*complete-set:board:main:1/i);
    expect(store.getState()).toEqual(before);
    expect(store.canUndo()).toBe(canUndo);
  });

  test("rebuild rejects canonical managed IDs retained by custom topology", () => {
    const seeded = createProjectStore();
    seeded.dispatch({ type: "output/enable", outputType: "main" });
    const project = seeded.getState().project;
    const collidingNode = project.semanticState.nodes.find(
      (candidate) => candidate.id === "complete-set:main:prompt",
    );
    if (collidingNode === undefined) {
      throw new Error("expected canonical prompt node");
    }
    collidingNode.managedBy = null;
    const store = createProjectStore(project);
    const before = store.getState();

    expect(() => store.dispatch({ type: "completeSet/rebuild" })).toThrow(
      /canonical managed node id collision.*complete-set:main:prompt/i,
    );
    expect(store.getState()).toEqual(before);
    expect(store.canUndo()).toBe(false);
  });

  test("empty main and detail boards shrink immediately without confirmation", () => {
    const store = createProjectStore();
    store.dispatch({ type: "output/enable", outputType: "main" });
    store.dispatch({ type: "output/setQuantity", outputType: "main", quantity: 3 });
    store.dispatch({ type: "output/enable", outputType: "detail" });
    store.dispatch({
      type: "output/setQuantity",
      outputType: "detail",
      quantity: 2,
    });

    const mainShrink = store.dispatch({
      type: "output/setQuantity",
      outputType: "main",
      quantity: 1,
    });
    const detailShrink = store.dispatch({
      type: "output/setQuantity",
      outputType: "detail",
      quantity: 1,
    });

    expect(mainShrink).toEqual({ applied: true });
    expect(detailShrink).toEqual({ applied: true });
    expect(store.getState().runtime.pendingConfirmation).toBeNull();
    expect(store.getState().runtime.unlinkedBoards).toEqual([]);
    expect(
      store.getState().project.semanticState.outputBoards.map((board) => board.id),
    ).toEqual([
      "complete-set:board:main:1",
      "complete-set:board:detail:1",
    ]);
  });

  test("empty SKU boards shrink immediately using that SKU's quantity", () => {
    const store = createProjectStore();
    store.dispatch({ type: "output/enable", outputType: "sku" });
    store.dispatch({ type: "sku/setOutputQuantity", skuId: "sku-a", quantity: 3 });
    store.dispatch({ type: "sku/setOutputQuantity", skuId: "sku-b", quantity: 1 });

    const result = store.dispatch({
      type: "sku/setOutputQuantity",
      skuId: "sku-a",
      quantity: 1,
    });

    expect(result).toEqual({ applied: true });
    expect(store.getState().runtime.pendingConfirmation).toBeNull();
    expect(store.getState().runtime.unlinkedBoards).toEqual([]);
    expect(
      store.getState().project.semanticState.outputBoards.map((board) => board.id),
    ).toEqual([
      "complete-set:board:sku:sku-a:1",
      "complete-set:board:sku:sku-b:1",
    ]);
  });

  test("disable removes an empty managed output immediately", () => {
    const store = createProjectStore();
    store.dispatch({ type: "output/enable", outputType: "main" });
    store.dispatch({ type: "output/setQuantity", outputType: "main", quantity: 1 });
    const result = store.dispatch({ type: "output/disable", outputType: "main" });

    expect(result).toEqual({ applied: true });
    expect(store.getState().runtime.pendingConfirmation).toBeNull();
    expect(store.getState().runtime.unlinkedBoards).toEqual([]);
    expect(store.getState().project.semanticState.nodes).toEqual([]);
    expect(store.getState().project.semanticState.outputBoards).toEqual([]);
  });

  test("disable clears layout positions owned by removed managed nodes", () => {
    const store = createProjectStore();
    store.dispatch({ type: "output/enable", outputType: "main" });
    store.dispatch({
      type: "node/move",
      nodeId: "complete-set:main:generation",
      position: { x: 0.2, y: 0.4 },
    });

    expect(store.dispatch({ type: "output/disable", outputType: "main" })).toEqual({
      applied: true,
    });
    expect(store.getState().project.layoutState.nodePositions).toEqual({});
  });

  test("a bound task or history result independently requires confirmation", () => {
    const taskStore = createProjectStore();
    taskStore.dispatch({ type: "output/enable", outputType: "main" });
    taskStore.dispatch({
      type: "output/setQuantity",
      outputType: "main",
      quantity: 2,
    });
    taskStore.dispatch({
      type: "task/statusReceived",
      task: {
        id: "task-only",
        boardId: "complete-set:board:main:2",
        status: "running",
        results: [],
      },
    });
    expect(
      taskStore.dispatch({
        type: "output/setQuantity",
        outputType: "main",
        quantity: 1,
      }).confirmation?.diff.taskIds,
    ).toEqual(["task-only"]);

    const historyStore = createProjectStore();
    historyStore.dispatch({ type: "output/enable", outputType: "main" });
    historyStore.dispatch({
      type: "output/setQuantity",
      outputType: "main",
      quantity: 2,
    });
    historyStore.dispatch({
      type: "task/statusReceived",
      task: {
        id: "history-source-task",
        boardId: null,
        status: "succeeded",
        results: [
          {
            id: "history-only-result",
            taskId: "history-source-task",
            boardId: "complete-set:board:main:2",
            assetId: "history-only-asset",
          },
        ],
      },
    });
    const historyPending = historyStore.dispatch({
      type: "output/setQuantity",
      outputType: "main",
      quantity: 1,
    });
    expect(historyPending.confirmation?.diff.taskIds).toEqual([]);
    expect(historyPending.confirmation?.diff.historyResultIds).toEqual([
      "history-only-result",
    ]);
  });

  test("subscribers observe edits and revision acknowledgement preserves undo history", () => {
    const store = createProjectStore(createEmptyProjectState(), {
      projectId: "project-a",
      revision: 1,
    });
    const revisions: number[] = [];
    const unsubscribe = store.subscribe(() => {
      revisions.push(store.getState().runtime.revision);
    });

    store.dispatch({ type: "mode/set", mode: "advanced" });
    store.acknowledgeRevision(2);

    expect(revisions).toEqual([1, 2]);
    expect(store.canUndo()).toBe(true);
    expect(store.getState().runtime.revision).toBe(2);

    unsubscribe();
    store.acknowledgeRevision(3);
    expect(revisions).toEqual([1, 2]);
  });

  test("persists viewport changes without polluting semantic undo history", () => {
    const store = createProjectStore();

    expect(
      store.dispatch({
        type: "viewport/set",
        viewport: { x: 2_000, y: -3_000, zoom: 2.5 },
      }),
    ).toEqual({ applied: true });

    expect(store.getState().project.layoutState.viewport).toEqual({
      x: 2_000,
      y: -3_000,
      zoom: 2.5,
    });
    expect(store.canUndo()).toBe(false);
  });
});
