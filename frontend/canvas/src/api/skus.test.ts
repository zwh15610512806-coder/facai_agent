import { describe, expect, test, vi } from "vitest";

import { createEmptyProjectState } from "../domain/types";
import { createSkusApi } from "./skus";

function snapshot(revision: number, skus: unknown[] = []): Record<string, unknown> {
  const state = createEmptyProjectState();
  return {
    project: {
      id: "project-a",
      name: "Project A",
      status: "active",
      schemaVersion: 1,
      revision,
      createdAt: null,
      updatedAt: null,
      archivedAt: null,
      semanticState: state.semanticState,
      layoutState: state.layoutState,
    },
    skus,
    revision,
  };
}

function sku(id: string, name: string, sortOrder: number): Record<string, unknown> {
  return {
    id,
    projectId: "project-a",
    name,
    sortOrder,
    referenceAssetId: null,
    prompt: "",
    config: {},
  };
}

describe("Canvas SKU API", () => {
  test("create, rename/reorder/prompt/reference, and delete use revisioned JSON calls", async () => {
    const responses = [
      snapshot(2, [sku("sku-a", "Red", 0)]),
      snapshot(3, [{ ...sku("sku-a", "Blue", 1), referenceAssetId: "working-b", prompt: "front" }]),
      snapshot(4, []),
    ];
    const fetcher = vi.fn(async () => new Response(JSON.stringify(responses.shift()), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }));
    const api = createSkusApi({ apiBase: "/api/canvas", fetcher });

    const created = await api.createSku("project-a", 1, { name: "Red" });
    const updated = await api.updateSku("project-a", "sku-a", 2, {
      name: "Blue",
      sortOrder: 1,
      prompt: "front",
      referenceAssetId: "working-b",
    });
    const deleted = await api.deleteSku("project-a", "sku-a", 3);

    expect(created.ok && created.snapshot.revision).toBe(2);
    expect(updated.ok && updated.snapshot.skus[0]).toMatchObject({
      name: "Blue",
      sortOrder: 1,
      prompt: "front",
      referenceAssetId: "working-b",
    });
    expect(deleted.ok && deleted.snapshot.revision).toBe(4);
    expect(fetcher.mock.calls).toEqual([
      ["/api/canvas/projects/project-a/skus", expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ revision: 1, name: "Red", referenceAssetId: null, prompt: "", config: {} }),
      })],
      ["/api/canvas/projects/project-a/skus/sku-a", expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ revision: 2, name: "Blue", sortOrder: 1, prompt: "front", referenceAssetId: "working-b" }),
      })],
      ["/api/canvas/projects/project-a/skus/sku-a", expect.objectContaining({
        method: "DELETE",
        body: JSON.stringify({ revision: 3 }),
      })],
    ]);
  });

  test("returns the autosave conflict shape without adopting the server revision", async () => {
    const api = createSkusApi({
      apiBase: "/api/canvas",
      fetcher: async () => new Response(JSON.stringify({
        detail: "Canvas project revision conflict",
        code: "canvas_revision_conflict",
        currentRevision: 9,
      }), { status: 409, headers: { "Content-Type": "application/json" } }),
    });

    await expect(api.updateSku("project-a", "sku-a", 3, { name: "Local name" })).resolves.toEqual({
      ok: false,
      kind: "conflict",
      currentRevision: 9,
    });
  });
});
