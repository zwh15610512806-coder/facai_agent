import { expect, test } from "vitest";

import { createEmptyProjectState, type CanvasProjectState } from "../domain/types";
import { createProjectStore } from "./project-store";

function projectWithCutout(): CanvasProjectState {
  const project = createEmptyProjectState();
  project.semanticState.nodes.push({
    id: "main-product-source",
    kind: "product_source",
    managedBy: null,
    skuId: null,
    assetId: "working-a",
    modelProfileId: null,
    prompt: null,
    compositionGroupId: null,
    textSnapshotId: null,
    outputBoardId: null,
    parameters: { allowOpaqueFallback: false },
  });
  project.layoutState.objectTransforms["main-product"] = {
    x: 0.5,
    y: 0.5,
    scale: 1,
    rotation: 0,
  };
  project.layoutState.productLayers.push({
    id: "main-product",
    sourceAssetId: "working-a",
    renderAssetId: "cutout-a",
    allowOpaqueFallback: false,
    skuId: null,
    compositionGroupId: null,
    transformId: "main-product",
    locked: true,
  });
  return project;
}

test("explicit rectangular fallback is a saved Store action that swaps render to working", () => {
  const store = createProjectStore(projectWithCutout(), {
    projectId: "project-a",
    revision: 3,
  });

  const result = store.dispatch({
    type: "asset/useRectangularSource",
    workingAssetId: "working-a",
  });

  expect(result.applied).toBe(true);
  expect(store.getState().project.layoutState.productLayers[0]).toMatchObject({
    sourceAssetId: "working-a",
    renderAssetId: "working-a",
  });
  expect(store.getState().project.layoutState.productLayers[0]).toMatchObject({
    allowOpaqueFallback: true,
  });
  expect(store.canUndo()).toBe(true);
});
