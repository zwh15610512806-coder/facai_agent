import { describe, expect, test } from "vitest";

import type { ProjectSku } from "../api/client";
import { createEmptyProjectState } from "./types";
import {
  applyCutoutEvent,
  hydrateProjectedAsset,
  isOpaqueFallbackAllowed,
  previewContentUrl,
  projectUploadedAsset,
  resolveSkuReferenceAssetId,
  selectRectangularFallback,
  validateAssetFile,
  type AssetOperation,
  type AssetRecord,
  type UploadedAssetBundle,
} from "./assets";

function asset(
  id: string,
  assetType: AssetRecord["assetType"],
  overrides: Partial<AssetRecord> = {},
): AssetRecord {
  return {
    id,
    projectId: "project-a",
    assetType,
    originalFilename: "cake.webp",
    mimeType: assetType === "source" ? "image/webp" : "image/png",
    byteCount: 1_024,
    width: 800,
    height: 600,
    sha256: `${id}-sha256`,
    sourceAssetId: assetType === "source" ? null : "source-a",
    transparencyStatus: "opaque",
    processorVersion: null,
    metadata: {},
    ...overrides,
  };
}

function operation(
  status: AssetOperation["status"],
  outputAssetId: string | null = null,
): AssetOperation {
  return {
    id: "operation-a",
    projectId: "project-a",
    operationType: "cutout",
    status,
    attemptCount: status === "queued" ? 0 : 1,
    inputAssetId: "working-a",
    outputAssetId,
    safeError: null,
  };
}

function opaqueUpload(): UploadedAssetBundle {
  return {
    source: asset("source-a", "source"),
    working: asset("working-a", "working"),
    preview: asset("preview-a", "preview", {
      sourceAssetId: "working-a",
    }),
    operation: operation("queued"),
  };
}

describe("asset upload projection", () => {
  test("accepts JPG, PNG, and WebP while returning safe client feedback", () => {
    for (const type of ["image/jpeg", "image/png", "image/webp"]) {
      expect(validateAssetFile(new File(["image"], `product.${type.split("/")[1]}`, { type }))).toEqual({
        ok: true,
      });
    }

    expect(
      validateAssetFile(new File(["gif"], "product.gif", { type: "image/gif" })),
    ).toEqual({ ok: false, message: "请选择 JPG、PNG 或 WebP 图片" });
    expect(
      validateAssetFile(
        new File([new Uint8Array(12 * 1024 * 1024 + 1)], "large.png", {
          type: "image/png",
        }),
      ),
    ).toEqual({ ok: false, message: "图片不能超过 12 MB" });
  });

  test("stores only returned asset IDs and queues opaque cutout without an opt-in flag", () => {
    const result = projectUploadedAsset(createEmptyProjectState(), opaqueUpload());

    expect(result.asset).toMatchObject({
      sourceAssetId: "source-a",
      workingAssetId: "working-a",
      previewAssetId: "preview-a",
      renderAssetId: "working-a",
      cutoutStatus: "queued",
      allowOpaqueFallback: false,
    });
    expect(result.project.layoutState.productLayers).toEqual([
      expect.objectContaining({
        sourceAssetId: "working-a",
        renderAssetId: "working-a",
        skuId: null,
        locked: true,
      }),
    ]);
    expect(result.project.semanticState.edges).toContainEqual({
      id: "main-product-source-cutout",
      kind: "product_asset",
      sourceNodeId: "main-product-source",
      sourcePort: "product",
      targetNodeId: "main-product-cutout",
      targetPort: "reference",
      skuId: null,
    });
    const serialized = JSON.stringify(result.project);
    expect(serialized).not.toContain("cake.webp");
    expect(serialized).not.toContain("data:");
    expect(serialized).not.toContain("blob:");
  });

  test("marks transparent uploads ready immediately", () => {
    const upload = opaqueUpload();
    upload.working.transparencyStatus = "transparent";
    upload.operation = null;

    expect(projectUploadedAsset(createEmptyProjectState(), upload).asset).toMatchObject({
      cutoutStatus: "ready",
      renderAssetId: "working-a",
    });
  });

  test("keeps the working preview while running and swaps only after cutout success", () => {
    const initial = projectUploadedAsset(createEmptyProjectState(), opaqueUpload());
    const running = applyCutoutEvent(initial, operation("running"));
    const succeeded = applyCutoutEvent(running, operation("succeeded", "cutout-a"));

    expect(running.asset.renderAssetId).toBe("working-a");
    expect(running.project.layoutState.productLayers[0]?.renderAssetId).toBe("working-a");
    expect(succeeded.asset.renderAssetId).toBe("cutout-a");
    expect(succeeded.project.layoutState.productLayers[0]?.renderAssetId).toBe("cutout-a");
    expect(previewContentUrl("/api/canvas", "cutout-a")).toBe(
      "/api/canvas/assets/cutout-a/content?variant=preview",
    );
  });

  test("a SKU with no reference visibly resolves to the main locked asset, never its name", () => {
    const projected = projectUploadedAsset(createEmptyProjectState(), opaqueUpload());
    const sku: ProjectSku = {
      id: "sku-a",
      projectId: "project-a",
      name: "Invented package name",
      sortOrder: 0,
      referenceAssetId: null,
      prompt: "",
      config: {},
    };

    expect(resolveSkuReferenceAssetId(sku, projected.project)).toEqual({
      assetId: "working-a",
      source: "main-product",
    });
    expect(JSON.stringify(projected.project)).not.toContain(sku.name);
  });

  test("persists explicit rectangular fallback in project state across reload", () => {
    const projected = projectUploadedAsset(createEmptyProjectState(), opaqueUpload());
    const selected = selectRectangularFallback(projected);
    const reloadedProject = JSON.parse(JSON.stringify(selected.project));

    expect(selected.asset.allowOpaqueFallback).toBe(true);
    expect(selected.project.layoutState.productLayers[0]?.renderAssetId).toBe("working-a");
    expect(isOpaqueFallbackAllowed(reloadedProject)).toBe(true);
    expect(reloadedProject.layoutState.productLayers[0]).toMatchObject({
      allowOpaqueFallback: true,
    });
  });

  test("keeps an explicit rectangular fallback when an in-flight cutout later succeeds", () => {
    const uploaded = projectUploadedAsset(createEmptyProjectState(), opaqueUpload());
    const selected = selectRectangularFallback(uploaded);
    const succeeded = applyCutoutEvent(selected, operation("succeeded", "cutout-a"));

    expect(succeeded.asset).toMatchObject({
      renderAssetId: "working-a",
      cutoutAssetId: "cutout-a",
      cutoutStatus: "ready",
      allowOpaqueFallback: true,
    });
    expect(succeeded.project.layoutState.productLayers[0]?.renderAssetId).toBe("working-a");
    expect(isOpaqueFallbackAllowed(succeeded.project)).toBe(true);
  });

  test("reload preserves explicit fallback even after a successful cutout exists", () => {
    const uploaded = projectUploadedAsset(createEmptyProjectState(), opaqueUpload());
    const selected = selectRectangularFallback(uploaded);
    const assets = [
      asset("source-a", "source"),
      asset("working-a", "working"),
      asset("preview-a", "preview", { sourceAssetId: "working-a" }),
      asset("cutout-a", "cutout", { sourceAssetId: "working-a" }),
    ];

    const hydrated = hydrateProjectedAsset(
      JSON.parse(JSON.stringify(selected.project)),
      assets,
      [operation("succeeded", "cutout-a")],
    );

    if (hydrated === null) throw new Error("expected hydrated fallback asset");
    expect(hydrated.asset).toMatchObject({
      renderAssetId: "working-a",
      cutoutAssetId: "cutout-a",
      allowOpaqueFallback: true,
      cutoutStatus: "ready",
    });
    expect(hydrated.project.layoutState.productLayers[0]?.renderAssetId).toBe("working-a");
    expect(isOpaqueFallbackAllowed(hydrated.project)).toBe(true);

    const replayed = applyCutoutEvent(hydrated, operation("succeeded", "cutout-a"));
    expect(replayed.asset).toMatchObject({
      renderAssetId: "working-a",
      cutoutAssetId: "cutout-a",
      allowOpaqueFallback: true,
    });
    expect(replayed.project.layoutState.productLayers[0]?.renderAssetId).toBe("working-a");
    expect(isOpaqueFallbackAllowed(replayed.project)).toBe(true);
  });

  test("rehydrates cutout state from saved IDs plus authoritative asset and operation reads", () => {
    const uploaded = projectUploadedAsset(createEmptyProjectState(), opaqueUpload());
    const assets = [
      asset("source-a", "source"),
      asset("working-a", "working"),
      asset("preview-a", "preview", { sourceAssetId: "working-a" }),
    ];
    const hydrated = hydrateProjectedAsset(
      JSON.parse(JSON.stringify(uploaded.project)),
      assets,
      [operation("running")],
    );

    expect(hydrated?.asset).toMatchObject({
      sourceAssetId: "source-a",
      workingAssetId: "working-a",
      previewAssetId: "preview-a",
      renderAssetId: "working-a",
      cutoutStatus: "running",
    });
    if (hydrated === null) throw new Error("expected hydrated asset");
    const succeeded = applyCutoutEvent(hydrated, {
      id: "operation-a",
      projectId: "project-a",
      operationType: "cutout",
      status: "succeeded",
      outputAssetId: "cutout-a",
    });
    expect(succeeded.project.layoutState.productLayers[0]?.renderAssetId).toBe("cutout-a");
  });
});
