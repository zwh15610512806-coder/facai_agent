import { expect, test, vi } from "vitest";

import type { AssetsApi } from "../api/assets";
import type { CanvasProjectEvent } from "../api/events";
import type { ProjectSku, ProjectSnapshot, ProjectSummary } from "../api/client";
import type { SkusApi } from "../api/skus";
import type { CanvasAdapter } from "../canvas/canvas-adapter";
import type { ProjectController, ProjectControllerState } from "../controllers/project-controller";
import { projectUploadedAsset, type UploadedAssetBundle } from "../domain/assets";
import { createEmptyProjectState } from "../domain/types";
import { createProjectStore } from "../state/project-store";
import { mountWorkspace } from "./workspace";

function summary(): ProjectSummary {
  return {
    id: "project-a",
    name: "Project A",
    status: "active",
    schemaVersion: 1,
    revision: 1,
    createdAt: null,
    updatedAt: null,
    archivedAt: null,
  };
}

function sku(): ProjectSku {
  return {
    id: "sku-a",
    projectId: "project-a",
    name: "No image SKU",
    sortOrder: 0,
    referenceAssetId: null,
    prompt: "",
    config: {},
  };
}

function snapshot(): ProjectSnapshot {
  const project = createEmptyProjectState();
  return {
    project: { ...summary(), semanticState: project.semanticState, layoutState: project.layoutState },
    skus: [sku()],
    revision: 1,
  };
}

async function settle(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
}

test("workspace integrates upload, saved fallback, SKU fallback, SSE cutout swap, and status", async () => {
  document.body.innerHTML = '<div id="canvas-app"></div>';
  const root = document.querySelector<HTMLElement>("#canvas-app");
  if (root === null) throw new Error("missing root");
  const controllerState: ProjectControllerState = {
    pendingSwitch: null,
    projects: [summary()],
    query: "",
    includeArchived: false,
    activeProjectId: "project-a",
    deleteCandidateId: null,
    loading: false,
    error: null,
    save: { status: "saved", dirty: false, message: null, currentRevision: null },
    remoteSync: { status: "idle", pendingRevision: null, message: null },
  };
  const adoptMutationSnapshot = vi.fn();
  let controllerListener: ((state: ProjectControllerState) => void) | null = null;
  const controller = {
    initialize: vi.fn(),
    getState: () => controllerState,
    getActiveSnapshot: () => snapshot(),
    adoptMutationSnapshot,
    subscribe: vi.fn((listener: (state: ProjectControllerState) => void) => {
      controllerListener = listener;
      return vi.fn();
    }),
    searchProjects: vi.fn(),
    createProject: vi.fn(),
    switchProject: vi.fn(),
    renameActiveProject: vi.fn(),
    archiveProject: vi.fn(),
    restoreProject: vi.fn(),
    requestDeleteProject: vi.fn(),
    cancelDeleteProject: vi.fn(),
    confirmDeleteProject: vi.fn(),
    retrySwitch: vi.fn(),
    stayOnProject: vi.fn(),
    discardAndSwitch: vi.fn(),
    retrySave: vi.fn(),
    retryRemoteSync: vi.fn(),
    dispose: vi.fn(),
  } as unknown as ProjectController;
  const store = createProjectStore(createEmptyProjectState(), { projectId: "project-a", revision: 1 });
  const adapter = {
    mount: vi.fn(),
    project: vi.fn(),
    setMode: vi.fn(),
    focusBoard: vi.fn(),
    cancelPendingLoads: vi.fn(),
    dispose: vi.fn(),
  } satisfies CanvasAdapter;
  const uploadValue = {
      source: {
        id: "source-a", projectId: "project-a", assetType: "source", originalFilename: "p.png",
        mimeType: "image/png", byteCount: 3, width: 1, height: 1, sha256: "source-sha",
        sourceAssetId: null, transparencyStatus: "opaque", processorVersion: null, metadata: {},
      },
      working: {
        id: "working-a", projectId: "project-a", assetType: "working", originalFilename: "p.png",
        mimeType: "image/png", byteCount: 3, width: 1, height: 1, sha256: "working-sha",
        sourceAssetId: "source-a", transparencyStatus: "opaque", processorVersion: null, metadata: {},
      },
      preview: {
        id: "preview-a", projectId: "project-a", assetType: "preview", originalFilename: "p.png",
        mimeType: "image/png", byteCount: 3, width: 1, height: 1, sha256: "preview-sha",
        sourceAssetId: "working-a", transparencyStatus: "unknown", processorVersion: null, metadata: {},
      },
      operation: {
        id: "operation-a", projectId: "project-a", operationType: "cutout", status: "queued",
        attemptCount: 0, inputAssetId: "working-a", outputAssetId: null, safeError: null,
      },
    } satisfies UploadedAssetBundle;
  const uploadAsset = vi.fn<AssetsApi["uploadAsset"]>(async () => ({
    ok: true,
    value: structuredClone(uploadValue),
  }));
  const retryCutout = vi.fn();
  const listAssets = vi.fn(async () => ({ ok: true as const, value: [] }));
  const assetsApi = {
    previewUrl: (id: string) => `/api/canvas/assets/${id}/content?variant=preview`,
    uploadAsset,
    listAssets,
    listOperations: vi.fn(async () => ({ ok: true as const, value: [] })),
    retryCutout,
  } as unknown as AssetsApi;
  const skusApi = {
    createSku: vi.fn(),
    updateSku: vi.fn(),
    deleteSku: vi.fn(),
  } as unknown as SkusApi;
  let eventListener: ((event: CanvasProjectEvent) => void) | null = null;
  const mounted = mountWorkspace({
    root,
    controller,
    store,
    adapter,
    assetsApi,
    skusApi,
    subscribeEvents: (listener) => {
      eventListener = listener;
      return vi.fn();
    },
  });
  await settle();

  const file = root.querySelector<HTMLInputElement>('input[aria-label="上传主商品图片"]');
  if (file === null) throw new Error("missing upload input");
  Object.defineProperty(file, "files", {
    configurable: true,
    value: [new File(["png"], "p.png", { type: "image/png" })],
  });
  file.dispatchEvent(new Event("change", { bubbles: true }));
  await settle();

  expect(uploadAsset).toHaveBeenCalledTimes(1);
  expect(store.getState().project.layoutState.productLayers[0]).toMatchObject({
    sourceAssetId: "working-a",
    renderAssetId: "working-a",
    locked: true,
  });
  expect(root.textContent).toContain("沿用主商品素材 working-a");
  expect(root.textContent).toContain("自动抠图已排队");
  const fallback = [...root.querySelectorAll<HTMLButtonElement>("button")].find(
    (button) => button.textContent === "使用原图矩形继续",
  );
  if (fallback === undefined) throw new Error("missing fallback button");
  fallback.click();
  expect(store.getState().project.layoutState.productLayers[0]).toMatchObject({
    allowOpaqueFallback: true,
  });

  const mode = root.querySelector<HTMLSelectElement>('select[aria-label="画布模式"]');
  if (mode === null) throw new Error("missing mode");
  mode.value = "advanced";
  mode.dispatchEvent(new Event("change", { bubbles: true }));
  expect(uploadAsset).toHaveBeenCalledTimes(1);
  expect(retryCutout).not.toHaveBeenCalled();

  const listener = eventListener as ((event: CanvasProjectEvent) => void) | null;
  listener?.({
    type: "operation.succeeded",
    projectId: "project-a",
    operation: {
      id: "operation-a",
      projectId: "project-a",
      operationType: "cutout",
      status: "succeeded",
      attemptCount: 1,
      outputAssetId: "cutout-a",
    },
  });
  expect(store.getState().project.semanticState.mode).toBe("advanced");
  expect(store.getState().project.layoutState.productLayers[0]?.renderAssetId).toBe("working-a");
  expect(root.textContent).toContain("素材已就绪");
  expect(adapter.project).toHaveBeenLastCalledWith(
    expect.anything(),
    expect.objectContaining({
      layoutState: expect.objectContaining({
        productLayers: [expect.objectContaining({ renderAssetId: "working-a" })],
      }),
    }),
  );
  expect(store.getState().project.layoutState.productLayers[0]).toMatchObject({
    allowOpaqueFallback: true,
  });

  const secondUpload = structuredClone(uploadValue);
  secondUpload.source.id = "source-b";
  secondUpload.working.id = "working-b";
  secondUpload.working.sourceAssetId = "source-b";
  secondUpload.preview.id = "preview-b";
  secondUpload.preview.sourceAssetId = "working-b";
  if (secondUpload.operation === null) throw new Error("expected queued cutout");
  secondUpload.operation.id = "operation-b";
  secondUpload.operation.inputAssetId = "working-b";
  let resolveSecondUpload!: (result: Awaited<ReturnType<AssetsApi["uploadAsset"]>>) => void;
  uploadAsset.mockImplementationOnce(() => new Promise((resolve) => {
    resolveSecondUpload = resolve;
  }));
  Object.defineProperty(file, "files", {
    configurable: true,
    value: [new File(["png-b"], "p-b.png", { type: "image/png" })],
  });
  file.dispatchEvent(new Event("change", { bubbles: true }));
  listener?.({
    type: "operation.succeeded",
    projectId: "project-a",
    operation: {
      id: "operation-b",
      projectId: "project-a",
      operationType: "cutout",
      status: "succeeded",
      attemptCount: 1,
      outputAssetId: "cutout-b",
    },
  });
  resolveSecondUpload({ ok: true, value: secondUpload });
  await settle();
  expect(store.getState().project.layoutState.productLayers[0]).toMatchObject({
    sourceAssetId: "working-b",
    renderAssetId: "cutout-b",
  });
  expect(root.textContent).toContain("素材已就绪");

  const remoteUpload = structuredClone(uploadValue);
  remoteUpload.source.id = "source-remote";
  remoteUpload.working.id = "working-remote";
  remoteUpload.working.sourceAssetId = "source-remote";
  remoteUpload.preview.id = "preview-remote";
  remoteUpload.preview.sourceAssetId = "working-remote";
  if (remoteUpload.operation === null) throw new Error("expected queued cutout");
  remoteUpload.operation.id = "operation-remote";
  remoteUpload.operation.inputAssetId = "working-remote";
  const remoteProject = projectUploadedAsset(createEmptyProjectState(), remoteUpload).project;
  store.replaceProject(remoteProject, { projectId: "project-a", revision: 7 });
  const notifyController = controllerListener as ((state: ProjectControllerState) => void) | null;
  notifyController?.(controllerState);
  listener?.({
    type: "operation.succeeded",
    projectId: "project-a",
    operation: {
      id: "operation-b",
      projectId: "project-a",
      operationType: "cutout",
      status: "succeeded",
      attemptCount: 1,
      outputAssetId: "cutout-stale",
    },
  });
  expect(store.getState().project.layoutState.productLayers[0]).toMatchObject({
    sourceAssetId: "working-remote",
    renderAssetId: "working-remote",
  });

  listAssets.mockRejectedValueOnce(new DOMException("project switched", "AbortError"));
  listener?.({
    type: "asset.uploaded",
    projectId: "project-a",
    sourceAssetId: "source-new",
    workingAssetId: "working-new",
    previewAssetId: "preview-new",
    transparencyStatus: "opaque",
  });
  await settle();
  expect(listAssets).toHaveBeenCalledTimes(3);

  mounted.dispose();
});
