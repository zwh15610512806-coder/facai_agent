import { expect, test, vi } from "vitest";

import type { CanvasApi, ProjectSnapshot } from "./api/client";
import type { AssetsApi } from "./api/assets";
import type { ProjectEventStream } from "./api/events";
import type { SkusApi } from "./api/skus";
import type { CanvasAdapter } from "./canvas/canvas-adapter";
import { createEmptyProjectState } from "./domain/types";
import { mountCanvas, startCanvasApplication } from "./main";

function snapshot(): ProjectSnapshot {
  const state = createEmptyProjectState();
  return {
    project: {
      id: "project-a",
      name: "Project A",
      status: "active",
      schemaVersion: 1,
      revision: 1,
      createdAt: null,
      updatedAt: null,
      archivedAt: null,
      semanticState: state.semanticState,
      layoutState: state.layoutState,
    },
    skus: [],
    revision: 1,
  };
}

function dependencies() {
  const api = {
    getProject: vi.fn(async () => ({ ok: true as const, value: snapshot() })),
    listProjects: vi.fn(async () => ({
      ok: true as const,
      value: [snapshot().project],
    })),
    saveProjectState: vi.fn(),
  } as unknown as CanvasApi;
  const adapter = {
    mount: vi.fn(),
    project: vi.fn(),
    setMode: vi.fn(),
    focusBoard: vi.fn(),
    cancelPendingLoads: vi.fn(),
    dispose: vi.fn(),
  } satisfies CanvasAdapter;
  const stream = { close: vi.fn() } satisfies ProjectEventStream;
  const assetsApi = {
    previewUrl: (id: string) => `/api/canvas/assets/${id}/content?variant=preview`,
    listAssets: vi.fn(async () => ({ ok: true as const, value: [] })),
    listOperations: vi.fn(async () => ({ ok: true as const, value: [] })),
  } as unknown as AssetsApi;
  const skusApi = {
    createSku: vi.fn(),
    updateSku: vi.fn(),
    deleteSku: vi.fn(),
  } as unknown as SkusApi;
  const loadFont = vi.fn(async () => undefined);
  return { api, adapter, stream, assetsApi, skusApi, loadFont };
}

test("mounts a deterministic loading shell in #canvas-app", () => {
  document.body.innerHTML = '<div id="canvas-app"></div>';

  mountCanvas();

  expect(document.querySelector("#canvas-app")?.innerHTML).toBe(
    '<main class="canvas-shell" data-canvas-state="loading" aria-busy="true"><p>Loading Product Canvas...</p></main>',
  );
});

test("requires the #canvas-app mount point", () => {
  expect(() => mountCanvas()).toThrowError(
    'Product Canvas mount point "#canvas-app" was not found.',
  );
});

test("application verifies the pinned font before mount or project loading and permits remount", async () => {
  document.body.innerHTML = '<div id="canvas-app"></div>';
  const root = document.querySelector<HTMLElement>("#canvas-app");
  if (root === null) throw new Error("missing root");
  const first = dependencies();

  const application = startCanvasApplication({
    root,
    bootstrap: { apiBase: "/api/canvas", projectId: "project-a" },
    api: first.api,
    assetsApi: first.assetsApi,
    skusApi: first.skusApi,
    adapter: first.adapter,
    openEvents: () => first.stream,
    syncUrl: vi.fn(),
    loadFont: first.loadFont,
  });
  expect(first.adapter.mount).not.toHaveBeenCalled();
  expect(first.api.getProject).not.toHaveBeenCalled();
  await application.ready;

  expect(first.loadFont).toHaveBeenCalledTimes(1);
  expect(first.loadFont.mock.invocationCallOrder[0]).toBeLessThan(
    first.adapter.mount.mock.invocationCallOrder[0] ?? Number.MAX_SAFE_INTEGER,
  );
  expect(first.adapter.mount.mock.invocationCallOrder[0]).toBeLessThan(
    vi.mocked(first.api.getProject).mock.invocationCallOrder[0] ?? Number.MAX_SAFE_INTEGER,
  );
  expect(application.store.getState().runtime.projectId).toBe("project-a");
  expect(root.querySelector('[data-testid="canvas-workspace"]')).not.toBeNull();
  expect(root.querySelector('[data-testid="canvas-asset-uploader"]')).not.toBeNull();
  expect(root.querySelector('[data-testid="canvas-asset-inspector"]')).not.toBeNull();
  expect(root.querySelector('[data-testid="canvas-sku-editor"]')).not.toBeNull();
  expect(first.assetsApi.listAssets).toHaveBeenCalledWith("project-a", expect.any(AbortSignal));
  expect(first.api.listProjects).toHaveBeenCalled();
  application.dispose();
  application.dispose();
  expect(first.stream.close).toHaveBeenCalledTimes(1);
  expect(first.adapter.dispose).toHaveBeenCalledTimes(1);

  const second = dependencies();
  const remounted = startCanvasApplication({
    root,
    bootstrap: { apiBase: "/api/canvas", projectId: null },
    api: second.api,
    adapter: second.adapter,
    openEvents: () => second.stream,
    syncUrl: vi.fn(),
    loadFont: second.loadFont,
  });
  await remounted.ready;
  expect(second.adapter.mount).toHaveBeenCalledTimes(1);
  remounted.dispose();
});

test("font verification failure blocks every canvas render and shows a safe fatal error", async () => {
  document.body.innerHTML = '<div id="canvas-app"></div>';
  const root = document.querySelector<HTMLElement>("#canvas-app");
  if (root === null) throw new Error("missing root");
  const deps = dependencies();
  deps.loadFont.mockRejectedValueOnce(new Error("固定画布字体校验失败"));

  const application = startCanvasApplication({
    root,
    bootstrap: { apiBase: "/api/canvas", projectId: "project-a" },
    api: deps.api,
    assetsApi: deps.assetsApi,
    skusApi: deps.skusApi,
    adapter: deps.adapter,
    openEvents: () => deps.stream,
    syncUrl: vi.fn(),
    loadFont: deps.loadFont,
  });

  await expect(application.ready).rejects.toThrowError("固定画布字体校验失败");
  expect(deps.adapter.mount).not.toHaveBeenCalled();
  expect(deps.api.getProject).not.toHaveBeenCalled();
  expect(root.querySelector('[role="alert"]')?.textContent).toBe("固定画布字体校验失败");
  application.dispose();
});
