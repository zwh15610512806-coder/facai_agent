import { expect, test, vi } from "vitest";

import type { CanvasGenerationCreate } from "../domain/generation";
import { createGenerationsApi, loadAllResultVersions, type ResultVersion } from "./generations";

const request: CanvasGenerationCreate = {
  revision: 2,
  mode: "complete-set",
  items: [{
    outputType: "main", skuId: null, boardId: "board-1", nodeId: "node-1", boardOrder: 0,
    modelProfileId: "model-1", prompt: "studio", width: 1024, height: 1024, ratio: "1:1",
    compositionGroupId: "group-1", layoutHash: `sha256:${"a".repeat(64)}`,
    inputs: [{ assetId: "asset-1", inputRole: "product", ordinal: 0 }], textSnapshotIds: [],
  }],
};

test("generation API submits the canonical request with a caller-owned idempotency key", async () => {
  const fetcher = vi.fn(async () => new Response(JSON.stringify({ id: "generation-1" }), {
    status: 201, headers: { "Content-Type": "application/json" },
  }));
  const api = createGenerationsApi({ apiBase: "/api/canvas", fetcher });

  await expect(api.create("project-1", request, "canvas:key-123456789")).resolves.toEqual({
    ok: true, value: { id: "generation-1" },
  });
  expect(fetcher).toHaveBeenCalledWith(
    "/api/canvas/projects/project-1/generations",
    expect.objectContaining({
      method: "POST",
      headers: expect.objectContaining({ "Idempotency-Key": "canvas:key-123456789" }),
      body: JSON.stringify(request),
    }),
  );
});

test("generation API exposes no access-token or unlock surface", () => {
  const fetcher = vi.fn();
  const api = createGenerationsApi({ apiBase: "/api/canvas", fetcher });

  expect("accessStatus" in api).toBe(false);
  expect("unlock" in api).toBe(false);
  expect(fetcher).not.toHaveBeenCalled();
});

test("result versions load every cursor page before a board can choose a prior retry", async () => {
  const version = (id: string) => ({
    versionId: id, generationId: "generation", itemId: "item", attemptId: `attempt-${id}`,
    boardId: "board", outputType: "main" as const, skuId: null,
    backgroundAssetId: `background-${id}`, backgroundPreviewAssetId: `background-preview-${id}`,
    composedAssetId: `composed-${id}`, composedPreviewAssetId: `composed-preview-${id}`,
    width: 1024, height: 1024, modelProfileId: "model", modelDisplayName: "Seedream",
    modelConfigVersion: 1, createdAt: "2026-07-15T00:00:00Z",
  }) satisfies ResultVersion;
  const listResultVersions = vi.fn(async (_projectId: string, _boardId?: string, cursor?: string | null) =>
    cursor === null || cursor === undefined
      ? { ok: true as const, value: { items: [version("first")], nextCursor: "page-2" } }
      : { ok: true as const, value: { items: [version("retry")], nextCursor: null } },
  );

  await expect(loadAllResultVersions({ listResultVersions }, "project-a")).resolves.toEqual({
    ok: true,
    value: [version("first"), version("retry")],
  });
  expect(listResultVersions).toHaveBeenNthCalledWith(1, "project-a", undefined, null);
  expect(listResultVersions).toHaveBeenNthCalledWith(2, "project-a", undefined, "page-2");
});
