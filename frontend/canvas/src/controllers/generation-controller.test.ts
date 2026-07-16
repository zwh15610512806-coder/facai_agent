import { describe, expect, test, vi } from "vitest";

import type { AutosaveController } from "./autosave-controller";
import {
  createGenerationController,
  type GenerationApi,
} from "./generation-controller";
import type { CanvasGenerationCreate } from "../domain/generation";
import { createProjectStore } from "../state/project-store";

const request: CanvasGenerationCreate = {
  revision: 1,
  mode: "complete-set",
  items: [{
    outputType: "main",
    skuId: null,
    boardId: "board-1",
    nodeId: "node-1",
    boardOrder: 0,
    modelProfileId: "model-1",
    prompt: "studio",
    width: 1024,
    height: 1024,
    ratio: "1:1",
    compositionGroupId: "group-1",
    layoutHash: `sha256:${"a".repeat(64)}`,
    inputs: [{ assetId: "asset-1", inputRole: "product", ordinal: 0 }],
    textSnapshotIds: [],
  }],
};

describe("generation controller", () => {
  test("flushes autosave before one double-click-safe paid submission", async () => {
    const store = createProjectStore(undefined, { projectId: "project-1", revision: 1 });
    const flush = vi.fn(async () => ({ ok: true as const }));
    const autosave = { flush } as unknown as AutosaveController;
    type CreateResponse = Awaited<ReturnType<GenerationApi["create"]>>;
    let resolveRequest!: (response: CreateResponse) => void;
    const create = vi.fn(() => new Promise<CreateResponse>((resolve) => {
      resolveRequest = resolve;
    }));
    const api: GenerationApi = { create };
    const controller = createGenerationController({
      store,
      autosave,
      api,
      build: () => ({ ok: true, request }),
      randomId: () => "idempotency-1",
    });

    const first = controller.submit();
    const second = controller.submit();
    await Promise.resolve();
    expect(flush).toHaveBeenCalledTimes(1);
    expect(create).toHaveBeenCalledTimes(1);
    expect(create).toHaveBeenCalledWith("project-1", request, "canvas:idempotency-1");
    resolveRequest({ ok: true, value: { id: "generation-1" } });
    await expect(first).resolves.toEqual({ ok: true, generationId: "generation-1" });
    await expect(second).resolves.toEqual({ ok: true, generationId: "generation-1" });
  });

  test("never creates a paid request when autosave reports offline or conflict", async () => {
    const store = createProjectStore(undefined, { projectId: "project-1", revision: 1 });
    const api: GenerationApi = { create: vi.fn() };
    const offline = createGenerationController({
      store,
      autosave: { flush: async () => ({ ok: false, kind: "offline", message: "offline" }) } as AutosaveController,
      api,
      build: () => ({ ok: true, request }),
    });
    await expect(offline.submit()).resolves.toEqual({ ok: false, kind: "save_failed", message: "offline" });
    expect(api.create).not.toHaveBeenCalled();
  });
});
