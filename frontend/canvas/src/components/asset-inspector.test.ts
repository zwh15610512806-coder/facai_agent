import { expect, test, vi } from "vitest";

import type { AssetsApi } from "../api/assets";
import type { ProjectedAsset } from "../domain/assets";
import { createAssetInspector } from "./asset-inspector";

function projected(overrides: Partial<ProjectedAsset> = {}): ProjectedAsset {
  return {
    projectId: "project-a",
    sourceAssetId: "source-a",
    workingAssetId: "working-a",
    previewAssetId: "preview-a",
    renderAssetId: "working-a",
    cutoutAssetId: null,
    operationId: "operation-a",
    cutoutStatus: "failed",
    allowOpaqueFallback: false,
    error: { code: "cutout_failed", message: "抠图失败", retryable: true },
    ...overrides,
  };
}

async function settle(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
}

test("inspector compares preview proxies and offers explicit retry and rectangular fallback", async () => {
  const retryCutout = vi.fn<AssetsApi["retryCutout"]>(async () => ({
    ok: true,
    value: {
      id: "operation-a",
      projectId: "project-a",
      operationType: "cutout",
      status: "queued",
      attemptCount: 2,
      inputAssetId: "working-a",
      outputAssetId: null,
      safeError: null,
    },
  }));
  const api = {
    retryCutout,
    previewUrl: (assetId: string) => `/api/canvas/assets/${assetId}/content?variant=preview`,
  } as unknown as AssetsApi;
  const onOperation = vi.fn();
  const onFallback = vi.fn();
  const inspector = createAssetInspector({
    api,
    onOperation,
    onFallback,
    createRequestId: () => "request-a",
  });
  document.body.append(inspector.element);
  const failed = projected();
  inspector.update(failed);

  expect(inspector.element.querySelectorAll(".canvas-checkerboard")).toHaveLength(2);
  const source = inspector.element.querySelector<HTMLImageElement>('img[alt="原图预览"]');
  if (source === null) throw new Error("missing source preview");
  expect(source.src).toContain("/assets/working-a/content?variant=preview");
  expect(source.src).not.toContain("/assets/source-a/content");
  expect(inspector.element.querySelector('input[type="checkbox"]')).toBeNull();

  const fallback = [...inspector.element.querySelectorAll<HTMLButtonElement>("button")].find(
    (button) => button.textContent === "使用原图矩形继续",
  );
  const retry = [...inspector.element.querySelectorAll<HTMLButtonElement>("button")].find(
    (button) => button.textContent === "重新抠图",
  );
  if (fallback === undefined || retry === undefined) throw new Error("missing inspector actions");
  fallback.click();
  expect(onFallback).toHaveBeenCalledWith(failed);
  retry.click();
  await settle();
  expect(retryCutout).toHaveBeenCalledWith("working-a", "request-a");
  expect(onOperation).toHaveBeenCalledWith(expect.objectContaining({ status: "queued" }));

  inspector.update(projected({
    cutoutAssetId: "cutout-a",
    renderAssetId: "cutout-a",
    cutoutStatus: "ready",
    error: null,
  }));
  const cutout = inspector.element.querySelector<HTMLImageElement>('img[alt="抠图预览"]');
  if (cutout === null) throw new Error("missing cutout preview");
  expect(cutout.src).toContain("/assets/cutout-a/content?variant=preview");
  inspector.dispose();
});

test("inspector explains that transparent ready assets do not need cutout", () => {
  const api = {
    previewUrl: (assetId: string) => `/api/canvas/assets/${assetId}/content?variant=preview`,
  } as unknown as AssetsApi;
  const inspector = createAssetInspector({
    api,
    onOperation: vi.fn(),
    onFallback: vi.fn(),
  });
  inspector.update(projected({
    operationId: null,
    cutoutStatus: "ready",
    error: null,
  }));

  expect(inspector.element.textContent).toContain("原图已含透明通道，无需抠图");
  expect(inspector.element.textContent).not.toContain("等待抠图结果");
  inspector.dispose();
});
