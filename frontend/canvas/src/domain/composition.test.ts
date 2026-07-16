import { describe, expect, test } from "vitest";

import vectorsFixture from "../../test/fixtures/composition-vectors.json";
import { createProjectStore } from "../state/project-store";
import {
  canonicalLayoutJson,
  compositionLayoutHash,
  mapProductToBoard,
} from "./composition";
import {
  createEmptyProjectState,
  type CanvasProjectState,
  type CompositionLayout,
} from "./types";
import { parseProjectState } from "./validation";

interface SharedVector {
  name: string;
  layout: CompositionLayout;
  sourceSize: { width: number; height: number };
  outputSize: { width: number; height: number };
  outputRatio: { width: number; height: number };
  expectedCanonical: string;
  expectedHash: string;
  expectedPlacement: {
    x: number;
    y: number;
    width: number;
    height: number;
    rotation: number;
  };
}

const vectors = vectorsFixture.vectors as SharedVector[];

function projectWithComposition(): CanvasProjectState {
  const project = createEmptyProjectState();
  const layout = structuredClone(vectors[0].layout);
  const layoutHash = compositionLayoutHash(layout);
  project.semanticState.compositionGroups.push({
    id: "group-a",
    skuIds: ["sku-a"],
    productLayerIds: ["main-layer", "sku-layer"],
    layout,
    layoutHash,
  });
  project.layoutState.objectTransforms = {
    "main-transform": { x: 0.5, y: 0.9, scale: 0.68, rotation: 0 },
    "sku-transform": { x: 0.5, y: 0.9, scale: 0.68, rotation: 0 },
  };
  project.layoutState.productLayers = [
    {
      id: "main-layer",
      sourceAssetId: "working-main",
      renderAssetId: "cutout-main",
      allowOpaqueFallback: false,
      skuId: null,
      compositionGroupId: "group-a",
      transformId: "main-transform",
      locked: true,
    },
    {
      id: "sku-layer",
      sourceAssetId: "working-main",
      renderAssetId: "cutout-main",
      allowOpaqueFallback: false,
      skuId: "sku-a",
      compositionGroupId: "group-a",
      transformId: "sku-transform",
      locked: true,
    },
  ];
  return project;
}

describe("shared composition contract", () => {
  test("TypeScript directly consumes the same camelCase v1 canonical vectors", () => {
    expect(vectorsFixture.schemaVersion).toBe(1);
    for (const vector of vectors) {
      expect(canonicalLayoutJson(vector.layout)).toBe(vector.expectedCanonical);
      expect(compositionLayoutHash(vector.layout)).toBe(vector.expectedHash);
      const placement = mapProductToBoard(vector.layout, {
        sourceSize: vector.sourceSize,
        outputSize: vector.outputSize,
      });
      expect(placement).toEqual(vector.expectedPlacement);
      expect(placement.width / placement.height).toBeCloseTo(
        vector.sourceSize.width / vector.sourceSize.height,
        2,
      );
      const angle = (placement.rotation * Math.PI) / 180;
      const rotatedWidth =
        Math.abs(placement.width * Math.cos(angle)) +
        Math.abs(placement.height * Math.sin(angle));
      const rotatedHeight =
        Math.abs(placement.width * Math.sin(angle)) +
        Math.abs(placement.height * Math.cos(angle));
      const centerX = placement.x + placement.width / 2;
      const centerY = placement.y + placement.height / 2;
      expect(centerX - rotatedWidth / 2).toBeGreaterThanOrEqual(
        vector.layout.slot.x * vector.outputSize.width - 1e-6,
      );
      expect(centerX + rotatedWidth / 2).toBeLessThanOrEqual(
        (vector.layout.slot.x + vector.layout.slot.width) * vector.outputSize.width + 1e-6,
      );
      expect(centerY - rotatedHeight / 2).toBeGreaterThanOrEqual(
        vector.layout.slot.y * vector.outputSize.height - 1e-6,
      );
      expect(centerY + rotatedHeight / 2).toBeLessThanOrEqual(
        (vector.layout.slot.y + vector.layout.slot.height) * vector.outputSize.height + 1e-6,
      );
    }
  });

  test("group hash excludes board ratio, source size, and independent scene controls", () => {
    const layout = vectors[0].layout;
    const left = {
      layout,
      outputRatio: { width: 1, height: 1 },
      sourceSize: { width: 1200, height: 600 },
      background: "studio",
      model: "person-a",
      lighting: "soft",
      color: "warm",
      decoration: "flowers",
    };
    const right = {
      ...left,
      outputRatio: { width: 3, height: 4 },
      sourceSize: { width: 800, height: 1200 },
      background: "street",
      model: "person-b",
      lighting: "hard",
      color: "cool",
      decoration: "none",
    };
    expect(compositionLayoutHash(left.layout)).toBe(compositionLayoutHash(right.layout));
  });

  test("one Store composition action updates every SKU projection and hash", () => {
    const store = createProjectStore(projectWithComposition());
    const nextLayout: CompositionLayout = {
      ...structuredClone(vectors[0].layout),
      baseline: 0.72,
      relativeProductFraction: 0.55,
      rotation: 30,
    };

    expect(
      store.dispatch({ type: "composition/update", groupId: "group-a", layout: nextLayout }),
    ).toEqual({ applied: true });
    const state = store.getState().project;
    expect(state.semanticState.compositionGroups[0]).toMatchObject({
      layout: nextLayout,
      layoutHash: compositionLayoutHash(nextLayout),
    });
    expect(Object.values(state.layoutState.objectTransforms)).toEqual([
      { x: 0.5, y: 0.72, scale: 0.55, rotation: 30 },
      { x: 0.5, y: 0.72, scale: 0.55, rotation: 30 },
    ]);
    expect(state.layoutState.productLayers[1]).toMatchObject({
      sourceAssetId: "working-main",
      renderAssetId: "cutout-main",
      locked: true,
    });
  });

  test("strict project validation rejects stale hashes and mismatched group projections", () => {
    const stale = projectWithComposition();
    stale.semanticState.compositionGroups[0].layoutHash = `sha256:${"0".repeat(64)}`;
    expect(() => parseProjectState(stale)).toThrow(/layout hash/i);

    const wrongGroup = projectWithComposition();
    wrongGroup.layoutState.productLayers[1].compositionGroupId = "group-b";
    expect(() => parseProjectState(wrongGroup)).toThrow(/composition group/i);

    const stretched = projectWithComposition();
    stretched.layoutState.objectTransforms["sku-transform"].scale = 0.2;
    expect(() => parseProjectState(stretched)).toThrow(/projection/i);
  });

  test("schemaVersion 1 migrates the saved node fallback into ProductLayer", () => {
    const legacy = projectWithComposition() as unknown as Record<string, unknown>;
    const semantic = (legacy.semanticState as CanvasProjectState["semanticState"]);
    semantic.nodes.push({
      id: "main-product-source",
      kind: "product_source",
      managedBy: null,
      skuId: null,
      assetId: "working-main",
      modelProfileId: null,
      prompt: null,
      compositionGroupId: null,
      textSnapshotId: null,
      outputBoardId: null,
      parameters: { allowOpaqueFallback: true },
    });
    const layout = legacy.layoutState as CanvasProjectState["layoutState"];
    layout.productLayers[0].renderAssetId = "working-main";
    delete (layout.productLayers[0] as Partial<(typeof layout.productLayers)[number]>).allowOpaqueFallback;

    const parsed = parseProjectState(legacy);
    expect(parsed.layoutState.productLayers[0].allowOpaqueFallback).toBe(true);
    expect(parsed.semanticState.nodes.at(-1)?.parameters).not.toHaveProperty(
      "allowOpaqueFallback",
    );
  });

  test("schemaVersion 1 migrates legacy group transforms into the shared layout", () => {
    const legacy = projectWithComposition() as unknown as Record<string, unknown>;
    const semantic = legacy.semanticState as CanvasProjectState["semanticState"];
    const group = semantic.compositionGroups[0] as unknown as Record<string, unknown>;
    delete group.layout;
    group.layoutHash = "legacy-transform";

    const parsed = parseProjectState(legacy);
    const migrated = parsed.semanticState.compositionGroups[0];
    expect(migrated.layout).toMatchObject({
      baseline: 0.9,
      relativeProductFraction: 0.68,
      rotation: 0,
    });
    expect(migrated.layoutHash).toBe(compositionLayoutHash(migrated.layout));
  });
});
