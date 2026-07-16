import { expect, test, vi } from "vitest";

import type { AssetsApi } from "../api/assets";
import type { CompositionsApi } from "../api/compositions";
import type { CanvasProjectEvent } from "../api/events";
import type { CanvasAdapter } from "../canvas/canvas-adapter";
import type { ProjectController, ProjectControllerState } from "../controllers/project-controller";
import type { AssetRecord } from "../domain/assets";
import { createProjectStore } from "../state/project-store";
import { mountWorkspace } from "./workspace";

const background: AssetRecord = {
  id: "background-a",
  projectId: "project-a",
  assetType: "generated_background",
  originalFilename: "background.png",
  mimeType: "image/png",
  byteCount: 100,
  width: 1024,
  height: 1024,
  sha256: "a".repeat(64),
  sourceAssetId: null,
  transparencyStatus: "opaque",
  processorVersion: null,
  metadata: {},
};

test("workspace flushes before compose, blocks failed flush, and previews SSE output", async () => {
  document.body.innerHTML = '<div id="canvas-app"></div>';
  const root = document.querySelector<HTMLElement>("#canvas-app");
  if (root === null) throw new Error("missing root");
  const store = createProjectStore(undefined, { projectId: "project-a", revision: 4 });
  store.dispatch({ type: "output/enable", outputType: "main" });
  store.dispatch({ type: "output/setQuantity", outputType: "main", quantity: 1 });
  const boardId = store.getState().project.semanticState.outputBoards[0]?.id;
  if (boardId === undefined) throw new Error("missing board");
  const state: ProjectControllerState = {
    pendingSwitch: null,
    projects: [],
    query: "",
    includeArchived: false,
    activeProjectId: "project-a",
    deleteCandidateId: null,
    loading: false,
    error: null,
    save: { status: "dirty", dirty: true, message: null, currentRevision: null },
    remoteSync: { status: "idle", pendingRevision: null, message: null },
  };
  let flushSucceeds = false;
  let controllerListener: ((next: ProjectControllerState) => void) | null = null;
  const flushSave = vi.fn(async () => flushSucceeds
    ? { ok: true as const }
    : { ok: false as const, kind: "offline" as const, message: "offline" });
  const controller = {
    getState: () => state,
    getActiveSnapshot: () => null,
    subscribe: vi.fn((listener: (next: ProjectControllerState) => void) => {
      controllerListener = listener;
      return vi.fn();
    }),
    flushSave,
    retrySave: vi.fn(),
    retryRemoteSync: vi.fn(),
    adoptMutationSnapshot: vi.fn(),
    searchProjects: vi.fn(),
    dispose: vi.fn(),
  } as unknown as ProjectController;
  const adapter = {
    mount: vi.fn(),
    project: vi.fn(),
    setMode: vi.fn(),
    focusBoard: vi.fn(),
    cancelPendingLoads: vi.fn(),
    dispose: vi.fn(),
  } satisfies CanvasAdapter;
  const assetsApi = {
    previewUrl: (assetId: string) => `/api/canvas/assets/${assetId}/content?variant=preview`,
    listAssets: vi.fn(async () => ({ ok: true as const, value: [background] })),
    listOperations: vi.fn(async () => ({ ok: true as const, value: [] })),
  } as unknown as AssetsApi;
  type ComposeResult = Awaited<ReturnType<CompositionsApi["enqueueCompose"]>>;
  const composeResolvers: Array<(result: ComposeResult) => void> = [];
  const enqueueCompose = vi.fn(() => new Promise<ComposeResult>((resolve) => {
    composeResolvers.push(resolve);
  }));
  const queued = (id: string, projectId = "project-a"): ComposeResult => ({
    ok: true as const,
    value: {
      id,
      projectId,
      operationType: "compose" as const,
      status: "queued" as const,
      attemptCount: 0,
      inputAssetId: background.id,
      outputAssetId: null,
      safeError: null,
    },
  });
  const compositionsApi = { enqueueCompose } satisfies CompositionsApi;
  let eventListener: ((event: CanvasProjectEvent) => void) | null = null;
  const mounted = mountWorkspace({
    root,
    controller,
    store,
    adapter,
    assetsApi,
    compositionsApi,
    subscribeEvents: (listener) => {
      eventListener = listener;
      return vi.fn();
    },
  });
  await vi.waitFor(() => {
    expect(
      root.querySelector<HTMLButtonElement>('[data-testid="canvas-compose-submit"]')?.disabled,
    ).toBe(false);
  });
  const board = root.querySelector<HTMLSelectElement>('[data-testid="canvas-compose-board"]');
  const selectedBackground = root.querySelector<HTMLSelectElement>(
    '[data-testid="canvas-compose-background"]',
  );
  const submit = root.querySelector<HTMLButtonElement>('[data-testid="canvas-compose-submit"]');
  if (board === null || selectedBackground === null || submit === null) {
    throw new Error("missing compose controls");
  }
  board.value = boardId;
  selectedBackground.value = background.id;
  submit.click();
  await vi.waitFor(() => expect(flushSave).toHaveBeenCalledTimes(1));
  expect(enqueueCompose).not.toHaveBeenCalled();

  flushSucceeds = true;
  submit.click();
  await vi.waitFor(() => expect(enqueueCompose).toHaveBeenCalledTimes(1));
  expect(enqueueCompose).toHaveBeenCalledWith(expect.objectContaining({
    projectId: "project-a",
    revision: 4,
    boardId,
    backgroundAssetId: background.id,
  }));

  const succeededListener = eventListener as ((event: CanvasProjectEvent) => void) | null;
  if (succeededListener === null) throw new Error("missing event listener");
  succeededListener({
    type: "operation.succeeded",
    projectId: "project-a",
    operation: {
      id: "unrelated-compose-operation",
      projectId: "project-a",
      operationType: "compose",
      status: "succeeded",
      attemptCount: 1,
      inputAssetId: background.id,
      outputAssetId: "must-not-preview",
    },
  });
  expect(root.querySelector('[data-testid="canvas-compose-preview"]')).toBeNull();
  succeededListener({
    type: "operation.succeeded",
    projectId: "project-a",
    operation: {
      id: "compose-operation",
      projectId: "project-a",
      operationType: "compose",
      status: "succeeded",
      attemptCount: 1,
      inputAssetId: background.id,
      outputAssetId: "composed-a",
    },
  });
  expect(root.querySelector('[data-testid="canvas-compose-preview"]')).toBeNull();
  composeResolvers[0]?.(queued("compose-operation"));
  await vi.waitFor(() => {
    expect(root.querySelector<HTMLImageElement>('[data-testid="canvas-compose-preview"]')?.src)
      .toContain("/api/canvas/assets/composed-a/content?variant=preview");
  });

  submit.click();
  await vi.waitFor(() => expect(enqueueCompose).toHaveBeenCalledTimes(2));
  const composeCalls = enqueueCompose.mock.calls as unknown as Array<[
    Parameters<CompositionsApi["enqueueCompose"]>[0],
  ]>;
  const oldRequestSignal = composeCalls[1]?.[0].signal;
  state.activeProjectId = "project-b";
  const notifyController = controllerListener as ((next: ProjectControllerState) => void) | null;
  if (notifyController === null) throw new Error("missing controller listener");
  notifyController(state);
  expect(oldRequestSignal?.aborted).toBe(true);
  composeResolvers[1]?.(queued("old-project-operation"));
  succeededListener({
    type: "operation.succeeded",
    projectId: "project-a",
    operation: {
      id: "old-project-operation",
      projectId: "project-a",
      operationType: "compose",
      status: "succeeded",
      attemptCount: 1,
      outputAssetId: "old-project-output",
    },
  });
  await Promise.resolve();
  expect(root.querySelector('[data-testid="canvas-compose-preview"]')).toBeNull();
  expect(root.querySelector('[data-testid="canvas-compose-feedback"]')?.textContent)
    .not.toBe("合成任务已进入队列");
  mounted.dispose();
});
