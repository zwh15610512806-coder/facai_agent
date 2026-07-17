import { expect, test, vi } from "vitest";

import type { ProjectSummary } from "../api/client";
import type { CanvasAdapter } from "../canvas/canvas-adapter";
import type {
  ProjectController,
  ProjectControllerState,
} from "../controllers/project-controller";
import {
  DEFAULT_COMPOSITION_LAYOUT,
  compositionTransform,
  compositionLayoutHash,
} from "../domain/composition";
import { projectUploadedAsset, type UploadedAssetBundle } from "../domain/assets";
import { createEmptyProjectState, type CanvasProjectState } from "../domain/types";
import type { ModelProfile } from "../domain/providers";
import { createProjectStore } from "../state/project-store";
import { mountWorkspace } from "./workspace";

function summary(
  id: string,
  status: ProjectSummary["status"],
  revision: number,
): ProjectSummary {
  return {
    id,
    name: `Project ${id.toUpperCase()}`,
    status,
    schemaVersion: 1,
    revision,
    createdAt: null,
    updatedAt: null,
    archivedAt: status === "archived" ? "2026-07-13T00:00:00" : null,
  };
}

function button(label: string): HTMLButtonElement {
  const match = [...document.querySelectorAll<HTMLButtonElement>("button")].find(
    (candidate) => candidate.textContent?.trim() === label,
  );
  if (match === undefined) {
    throw new Error(`missing button ${label}`);
  }
  return match;
}

function validAdvancedProject(): CanvasProjectState {
  const project = createEmptyProjectState();
  const layout = structuredClone(DEFAULT_COMPOSITION_LAYOUT);
  project.semanticState.mode = "advanced";
  project.semanticState.compositionGroups = [{
    id: "group-main", skuIds: [], productLayerIds: ["main-product"],
    layout, layoutHash: compositionLayoutHash(layout),
  }];
  project.layoutState.objectTransforms["main-product"] = compositionTransform(layout);
  project.layoutState.productLayers = [{
    id: "main-product", sourceAssetId: "working-main", renderAssetId: "cutout-main",
    allowOpaqueFallback: false, skuId: null, compositionGroupId: "group-main",
    transformId: "main-product", locked: true,
  }];
  project.semanticState.nodes = [
    { id: "main-product-source", kind: "product_source", managedBy: null, skuId: null, assetId: "working-main", modelProfileId: null, prompt: null, compositionGroupId: null, textSnapshotId: null, outputBoardId: null, parameters: {} },
    { id: "main-product-cutout", kind: "auto_cutout", managedBy: null, skuId: null, assetId: "cutout-main", modelProfileId: null, prompt: null, compositionGroupId: null, textSnapshotId: null, outputBoardId: null, parameters: {} },
    { id: "advanced-prompt", kind: "prompt", managedBy: null, skuId: null, assetId: null, modelProfileId: null, prompt: "clean studio", compositionGroupId: null, textSnapshotId: null, outputBoardId: null, parameters: {} },
    { id: "advanced-generation", kind: "model_generation", managedBy: null, skuId: null, assetId: null, modelProfileId: "model-a", prompt: null, compositionGroupId: null, textSnapshotId: null, outputBoardId: null, parameters: { width: 1024, height: 1024 } },
    { id: "advanced-output", kind: "main_output", managedBy: null, skuId: null, assetId: null, modelProfileId: null, prompt: null, compositionGroupId: null, textSnapshotId: null, outputBoardId: "board-main", parameters: {} },
    { id: "advanced-composition", kind: "composition_group", managedBy: null, skuId: null, assetId: null, modelProfileId: null, prompt: null, compositionGroupId: "group-main", textSnapshotId: null, outputBoardId: null, parameters: {} },
  ];
  project.semanticState.edges = [
    { id: "source-cutout", kind: "product_asset", sourceNodeId: "main-product-source", sourcePort: "product", targetNodeId: "main-product-cutout", targetPort: "reference", skuId: null },
    { id: "cutout-generation", kind: "cutout_asset", sourceNodeId: "main-product-cutout", sourcePort: "cutout", targetNodeId: "advanced-generation", targetPort: "reference", skuId: null },
    { id: "prompt-generation", kind: "prompt", sourceNodeId: "advanced-prompt", sourcePort: "prompt", targetNodeId: "advanced-generation", targetPort: "prompt", skuId: null },
    { id: "generation-output", kind: "output_image", sourceNodeId: "advanced-generation", sourcePort: "output", targetNodeId: "advanced-output", targetPort: "input", skuId: null },
    { id: "composition-output", kind: "composition", sourceNodeId: "advanced-composition", sourcePort: "composition", targetNodeId: "advanced-output", targetPort: "composition", skuId: null },
  ];
  project.semanticState.outputBoards = [{ id: "board-main", outputNodeId: "advanced-output", outputType: "main", skuId: null, sortOrder: 0, selectedResultAssetId: null }];
  return project;
}

const advancedModel: ModelProfile = {
  id: "model-a", providerId: "provider-a", modelId: "seedream", displayName: "Seedream 5.0 Pro",
  enabled: true, availability: "available", availabilityReason: null, configVersion: 1,
  capabilities: {
    textToImage: true, imageToImage: true, maskEdit: false, allowedRatios: ["1:1"], allowedSizes: ["1024x1024"],
    minWidth: 512, maxWidth: 2048, minHeight: 512, maxHeight: 2048, maxQuantity: 1,
    maxReferenceImages: 1, referenceTransfer: "public_url", protocol: "sync", supportsCancel: false,
    supportsIdempotency: false, supportsIdempotencyLookup: false, concurrencyLimit: 1, priceMetadata: null,
  },
  priceMetadata: null,
};

function projectedAdvancedProjectAwaitingCutoutConnection(): CanvasProjectState {
  const upload = {
    source: {
      id: "source-main", projectId: "a", assetType: "source", originalFilename: "main.png",
      mimeType: "image/png", byteCount: 3, width: 1024, height: 1024, sha256: "source-sha",
      sourceAssetId: null, transparencyStatus: "transparent", processorVersion: null, metadata: {},
    },
    working: {
      id: "working-main", projectId: "a", assetType: "working", originalFilename: "main.png",
      mimeType: "image/png", byteCount: 3, width: 1024, height: 1024, sha256: "working-sha",
      sourceAssetId: "source-main", transparencyStatus: "transparent", processorVersion: null, metadata: {},
    },
    preview: {
      id: "preview-main", projectId: "a", assetType: "preview", originalFilename: "main.png",
      mimeType: "image/png", byteCount: 3, width: 1024, height: 1024, sha256: "preview-sha",
      sourceAssetId: "working-main", transparencyStatus: "unknown", processorVersion: null, metadata: {},
    },
    operation: null,
  } satisfies UploadedAssetBundle;
  const project = projectUploadedAsset(createEmptyProjectState(), upload).project;
  const layout = structuredClone(DEFAULT_COMPOSITION_LAYOUT);
  project.semanticState.mode = "advanced";
  project.semanticState.compositionGroups = [{
    id: "group-main", skuIds: [], productLayerIds: ["main-product"],
    layout, layoutHash: compositionLayoutHash(layout),
  }];
  project.layoutState.objectTransforms["main-product"] = compositionTransform(layout);
  project.layoutState.productLayers[0] = {
    ...project.layoutState.productLayers[0]!, compositionGroupId: "group-main",
  };
  project.semanticState.nodes.push(
    { id: "advanced-prompt", kind: "prompt", managedBy: null, skuId: null, assetId: null, modelProfileId: null, prompt: "clean studio", compositionGroupId: null, textSnapshotId: null, outputBoardId: null, parameters: {} },
    { id: "advanced-generation", kind: "model_generation", managedBy: null, skuId: null, assetId: null, modelProfileId: null, prompt: null, compositionGroupId: null, textSnapshotId: null, outputBoardId: null, parameters: { width: 1024, height: 1024 } },
    { id: "advanced-output", kind: "main_output", managedBy: null, skuId: null, assetId: null, modelProfileId: null, prompt: null, compositionGroupId: null, textSnapshotId: null, outputBoardId: "board-main", parameters: {} },
    { id: "advanced-composition", kind: "composition_group", managedBy: null, skuId: null, assetId: null, modelProfileId: null, prompt: null, compositionGroupId: "group-main", textSnapshotId: null, outputBoardId: null, parameters: {} },
  );
  project.semanticState.edges.push(
    { id: "prompt-generation", kind: "prompt", sourceNodeId: "advanced-prompt", sourcePort: "prompt", targetNodeId: "advanced-generation", targetPort: "prompt", skuId: null },
    { id: "generation-output", kind: "output_image", sourceNodeId: "advanced-generation", sourcePort: "output", targetNodeId: "advanced-output", targetPort: "input", skuId: null },
    { id: "composition-output", kind: "composition", sourceNodeId: "advanced-composition", sourcePort: "composition", targetNodeId: "advanced-output", targetPort: "composition", skuId: null },
  );
  project.semanticState.outputBoards = [{
    id: "board-main", outputNodeId: "advanced-output", outputType: "main", skuId: null,
    sortOrder: 0, selectedResultAssetId: null,
  }];
  return project;
}

test("workspace enables advanced generation for a valid wired system graph after loading the model catalog", async () => {
  document.body.innerHTML = '<div id="canvas-app"></div>';
  const root = document.querySelector<HTMLElement>("#canvas-app");
  if (root === null) throw new Error("missing root");
  const state: ProjectControllerState = {
    pendingSwitch: null, projects: [summary("a", "active", 1)], query: "", includeArchived: false,
    activeProjectId: "a", deleteCandidateId: null, loading: false, error: null,
    save: { status: "saved", dirty: false, message: null, currentRevision: 1 },
    remoteSync: { status: "idle", pendingRevision: null, message: null },
  };
  const controller = {
    getState: () => state,
    subscribe: vi.fn(() => vi.fn()),
    flushSave: vi.fn(async () => undefined),
    dispose: vi.fn(),
  } as unknown as ProjectController;
  const store = createProjectStore(validAdvancedProject(), { projectId: "a", revision: 1 });
  const adapter = {
    mount: vi.fn(), project: vi.fn(), setMode: vi.fn(), focusBoard: vi.fn(), cancelPendingLoads: vi.fn(), dispose: vi.fn(),
  } satisfies CanvasAdapter;
  const mounted = mountWorkspace({
    root, controller, store, adapter,
    providersApi: { loadCatalog: vi.fn(async () => ({ ok: true as const, value: [advancedModel] })) },
  });

  await Promise.resolve();
  const generate = root.querySelector<HTMLButtonElement>('[data-testid="canvas-generate-advanced"]');
  expect(generate?.textContent).toBe("生成高级画布");
  expect(generate?.disabled).toBe(false);
  mounted.dispose();
});

test("workspace connects the projected system cutout through the inspector and enables advanced generation", async () => {
  document.body.innerHTML = '<div id="canvas-app"></div>';
  const root = document.querySelector<HTMLElement>("#canvas-app");
  if (root === null) throw new Error("missing root");
  const state: ProjectControllerState = {
    pendingSwitch: null, projects: [summary("a", "active", 1)], query: "", includeArchived: false,
    activeProjectId: "a", deleteCandidateId: null, loading: false, error: null,
    save: { status: "saved", dirty: false, message: null, currentRevision: 1 },
    remoteSync: { status: "idle", pendingRevision: null, message: null },
  };
  const controller = {
    getState: () => state, subscribe: vi.fn(() => vi.fn()), flushSave: vi.fn(async () => undefined), dispose: vi.fn(),
  } as unknown as ProjectController;
  const store = createProjectStore(projectedAdvancedProjectAwaitingCutoutConnection(), { projectId: "a", revision: 1 });
  const adapter = {
    mount: vi.fn(), project: vi.fn(), setMode: vi.fn(), focusBoard: vi.fn(), cancelPendingLoads: vi.fn(), dispose: vi.fn(),
  } satisfies CanvasAdapter;
  const mounted = mountWorkspace({
    root, controller, store, adapter,
    providersApi: { loadCatalog: vi.fn(async () => ({ ok: true as const, value: [advancedModel] })) },
  });

  await Promise.resolve();
  const selected = root.querySelector<HTMLSelectElement>('select[aria-label="选择高级节点"]');
  if (selected === null) throw new Error("missing node selector");
  selected.value = "advanced-generation";
  selected.dispatchEvent(new Event("change", { bubbles: true }));
  const model = root.querySelector<HTMLSelectElement>('select[aria-label="节点模型"]');
  if (model === null) throw new Error("missing model selector");
  model.value = "model-a";
  model.dispatchEvent(new Event("change", { bubbles: true }));

  const source = root.querySelector<HTMLSelectElement>('select[aria-label="连线来源"]');
  const target = root.querySelector<HTMLSelectElement>('select[aria-label="连线目标"]');
  const connect = button("连接节点");
  if (source === null || target === null) throw new Error("missing connection selectors");
  source.value = "main-product-cutout";
  source.dispatchEvent(new Event("change", { bubbles: true }));
  target.value = "advanced-generation";
  target.dispatchEvent(new Event("change", { bubbles: true }));
  expect(connect.disabled).toBe(false);
  connect.click();

  expect(store.getState().project.semanticState.edges).toContainEqual(expect.objectContaining({
    kind: "cutout_asset", sourceNodeId: "main-product-cutout", targetNodeId: "advanced-generation",
  }));
  const generate = root.querySelector<HTMLButtonElement>('[data-testid="canvas-generate-advanced"]');
  expect(generate?.textContent).toBe("生成高级画布");
  expect(generate?.disabled).toBe(false);
  mounted.dispose();
});

test("workspace renders accessible project actions and wires toolbar, status and disposer", async () => {
  document.body.innerHTML = '<div id="canvas-app"></div>';
  const root = document.querySelector<HTMLElement>("#canvas-app");
  if (root === null) throw new Error("missing root");

  let state: ProjectControllerState = {
    pendingSwitch: null,
    projects: [summary("a", "active", 1), summary("b", "archived", 2)],
    query: "",
    includeArchived: false,
    activeProjectId: "a",
    deleteCandidateId: null,
    loading: false,
    error: null,
    save: {
      status: "offline",
      dirty: true,
      message: "Network unavailable",
      currentRevision: null,
    },
    remoteSync: {
      status: "idle",
      pendingRevision: null,
      message: null,
    },
  };
  let controllerListener: ((next: ProjectControllerState) => void) | null = null;
  const controller = {
    getState: () => state,
    subscribe: vi.fn((listener: (next: ProjectControllerState) => void) => {
      controllerListener = listener;
      return vi.fn();
    }),
    searchProjects: vi.fn(async () => undefined),
    createProject: vi.fn(async () => ({ ok: true as const })),
    switchProject: vi.fn(async () => ({ ok: true as const })),
    renameActiveProject: vi.fn(async () => ({ ok: false as const, kind: "server" as const, message: "stop" })),
    archiveProject: vi.fn(async () => ({ ok: false as const, kind: "server" as const, message: "stop" })),
    restoreProject: vi.fn(async () => ({ ok: false as const, kind: "server" as const, message: "stop" })),
    requestDeleteProject: vi.fn(),
    cancelDeleteProject: vi.fn(),
    confirmDeleteProject: vi.fn(async () => ({ ok: false as const, kind: "server" as const, message: "stop" })),
    retrySwitch: vi.fn(async () => ({ ok: true as const })),
    stayOnProject: vi.fn(),
    discardAndSwitch: vi.fn(async () => ({ ok: true as const })),
    retrySave: vi.fn(async () => ({ ok: true as const })),
    retryRemoteSync: vi.fn(async () => undefined),
    dispose: vi.fn(),
  } as unknown as ProjectController;
  const store = createProjectStore(createEmptyProjectState(), {
    projectId: "a",
    revision: 1,
  });
  let adapterDispatch: ((action: Parameters<typeof store.dispatch>[0]) => void) | null = null;
  const adapter = {
    mount: vi.fn((_element, dispatch) => {
      adapterDispatch = dispatch;
    }),
    project: vi.fn(),
    setMode: vi.fn(),
    focusBoard: vi.fn(),
    cancelPendingLoads: vi.fn(),
    dispose: vi.fn(),
  } satisfies CanvasAdapter;

  const mounted = mountWorkspace({ root, controller, store, adapter });

  expect(root.querySelector('[data-testid="canvas-project-sidebar"]')).not.toBeNull();
  expect(root.querySelector('.canvas-project-sidebar-header')).not.toBeNull();
  expect(root.querySelector('[data-testid="canvas-project-count"]')?.textContent).toBe("2 个项目");
  expect(root.querySelector('.canvas-project-create-section')).not.toBeNull();
  expect(root.querySelector('.canvas-project-filter-section')).not.toBeNull();
  expect(root.querySelector('input[aria-label="搜索项目"]')).not.toBeNull();
  expect(root.querySelector('[data-testid="canvas-project-search"]')).not.toBeNull();
  expect(root.querySelector('input[aria-label="新建项目名称"]')).not.toBeNull();
  expect(root.querySelector('[data-testid="canvas-project-create"]')).not.toBeNull();
  expect(
    root.querySelector('[data-testid="canvas-project-row"][data-project-id="a"]'),
  ).not.toBeNull();
  expect(root.querySelector('select[aria-label="画布模式"]')).not.toBeNull();
  expect(root.querySelector('[data-testid="canvas-undo"]')).not.toBeNull();
  expect(root.querySelector('[data-testid="canvas-redo"]')).not.toBeNull();
  expect(root.querySelector('[data-testid="canvas-zoom-in"]')).not.toBeNull();
  expect(root.querySelector('[data-testid="canvas-surface"]')).toBeInstanceOf(
    HTMLCanvasElement,
  );
  expect(root.querySelector('aside[aria-label="属性设置"]')).not.toBeNull();
  expect(root.querySelector('[data-testid="canvas-composition-inspector"]')).not.toBeNull();
  expect(root.querySelector('[role="status"]')?.textContent).toContain("离线");
  expect(root.querySelector('[data-testid="canvas-save-status"]')?.getAttribute("data-state")).toBe("offline");
  expect(root.textContent).not.toContain("模型设置");
  expect(button("导出").disabled).toBe(true);
  expect(root.querySelector('[data-testid="canvas-stage-empty"]')?.textContent).toContain("上传");
  expect(root.querySelector('[role="tablist"][aria-label="画布创作步骤"]')).not.toBeNull();

  const search = root.querySelector<HTMLInputElement>('input[aria-label="搜索项目"]');
  if (search === null) throw new Error("missing search");
  search.value = "needle";
  search.dispatchEvent(new Event("input", { bubbles: true }));
  expect(controller.searchProjects).toHaveBeenCalledWith("needle", false);

  const createName = root.querySelector<HTMLInputElement>('input[aria-label="新建项目名称"]');
  if (createName === null) throw new Error("missing create input");
  const createProject = root.querySelector<HTMLButtonElement>('[data-testid="canvas-project-create"]');
  if (createProject === null) throw new Error("missing create button");
  expect(createProject.disabled).toBe(true);
  createName.value = "New Project";
  createName.dispatchEvent(new Event("input", { bubbles: true }));
  expect(createProject.disabled).toBe(false);
  button("新建").click();
  expect(controller.createProject).toHaveBeenCalledWith("New Project");
  await vi.waitFor(() => expect(createName.value).toBe(""));
  button("Project B").click();
  expect(controller.switchProject).toHaveBeenCalledWith("b");

  root.querySelector<HTMLButtonElement>('[data-testid="canvas-project-rename-start"]')?.click();
  const rename = root.querySelector<HTMLInputElement>('input[aria-label="重命名 Project A"]');
  if (rename === null) throw new Error("missing rename input");
  rename.value = "Renamed A";
  button("保存").click();
  expect(controller.renameActiveProject).toHaveBeenCalledWith("Renamed A");
  button("归档项目").click();
  expect(controller.archiveProject).toHaveBeenCalledWith("a");
  button("恢复项目").click();
  expect(controller.restoreProject).toHaveBeenCalledWith("b");
  button("删除项目").click();
  expect(controller.requestDeleteProject).toHaveBeenCalledWith("a");

  state = { ...state, deleteCandidateId: "a" };
  const listener = controllerListener as
    | ((next: ProjectControllerState) => void)
    | null;
  listener?.(state);
  expect(root.querySelector('[role="dialog"][aria-label="确认删除项目"]')).not.toBeNull();
  button("确认删除").click();
  expect(controller.confirmDeleteProject).toHaveBeenCalledTimes(1);

  const mainOutput = root.querySelector<HTMLInputElement>(
    'input[aria-label="启用主图"]',
  );
  if (mainOutput === null) throw new Error("missing main output checkbox");
  mainOutput.checked = true;
  mainOutput.dispatchEvent(new Event("change", { bubbles: true }));
  const quantity = root.querySelector<HTMLInputElement>(
    'input[aria-label="主图数量"]',
  );
  const prompt = root.querySelector<HTMLTextAreaElement>(
    'textarea[aria-label="主图提示词"]',
  );
  if (quantity === null || prompt === null) {
    throw new Error("missing main output controls");
  }
  quantity.value = "2";
  quantity.dispatchEvent(new Event("change", { bubbles: true }));
  expect(
    root.querySelector<HTMLInputElement>('input[aria-label="主图数量"]'),
  ).toBe(quantity);
  expect(
    root.querySelector<HTMLTextAreaElement>('textarea[aria-label="主图提示词"]'),
  ).toBe(prompt);
  prompt.focus();
  prompt.value = "输入";
  prompt.dispatchEvent(new Event("input", { bubbles: true }));
  prompt.value += "期间保留焦点";
  prompt.dispatchEvent(new Event("input", { bubbles: true }));
  expect(
    root.querySelector<HTMLTextAreaElement>('textarea[aria-label="主图提示词"]'),
  ).toBe(prompt);
  expect(document.activeElement).toBe(prompt);
  expect(
    store.getState().project.semanticState.completeSet.outputs[0]?.prompt,
  ).toBe("输入期间保留焦点");

  const mode = root.querySelector<HTMLSelectElement>('select[aria-label="画布模式"]');
  if (mode === null) throw new Error("missing mode");
  mode.value = "advanced";
  mode.dispatchEvent(new Event("change", { bubbles: true }));
  expect(store.getState().project.semanticState.mode).toBe("advanced");
  expect(adapter.setMode).toHaveBeenLastCalledWith("advanced");
  button("放大").click();
  expect(store.getState().project.layoutState.viewport.zoom).toBeGreaterThan(1);
  expect(adapterDispatch).not.toBeNull();

  state = {
    ...state,
    activeProjectId: null,
    projects: [summary("a", "archived", 2)],
    save: {
      status: "saved",
      dirty: false,
      message: null,
      currentRevision: null,
    },
    remoteSync: {
      status: "failed",
      pendingRevision: 3,
      message: "Remote refresh failed",
    },
  };
  listener?.(state);
  expect(root.querySelector('[data-testid="canvas-workspace"]')?.getAttribute("data-editable")).toBe("false");
  expect(mode.disabled).toBe(true);
  const modeBeforeDisabledEdit = store.getState().project.semanticState.mode;
  mode.value = modeBeforeDisabledEdit === "advanced" ? "complete-set" : "advanced";
  mode.dispatchEvent(new Event("change", { bubbles: true }));
  expect(store.getState().project.semanticState.mode).toBe(modeBeforeDisabledEdit);
  expect(root.querySelector('[data-testid="canvas-save-status"]')?.textContent).toContain(
    "远端同步失败",
  );
  button("重试同步").click();
  expect(controller.retryRemoteSync).toHaveBeenCalledTimes(1);

  state = {
    ...state,
    projects: [],
    query: "needle",
    includeArchived: false,
  };
  listener?.(state);
  expect(root.querySelector('[data-testid="canvas-project-count"]')?.textContent).toBe("0 个项目");
  expect(root.querySelector('[data-testid="canvas-project-empty"]')?.textContent).toContain(
    "没有找到匹配项目",
  );

  mounted.dispose();
  mounted.dispose();
  expect(adapter.dispose).toHaveBeenCalledTimes(1);
  expect(controller.dispose).toHaveBeenCalledTimes(1);
  expect(root.childElementCount).toBe(0);
});

test("workspace selects and edits any composition group without mutating the first group", () => {
  document.body.innerHTML = '<div id="canvas-app"></div>';
  const root = document.querySelector<HTMLElement>("#canvas-app");
  if (root === null) throw new Error("missing root");

  const project = createEmptyProjectState();
  const firstLayout = structuredClone(DEFAULT_COMPOSITION_LAYOUT);
  const secondLayout = { ...structuredClone(DEFAULT_COMPOSITION_LAYOUT), baseline: 0.72 };
  project.semanticState.compositionGroups = [
    {
      id: "group-a",
      skuIds: ["sku-a"],
      productLayerIds: ["layer-a"],
      layout: firstLayout,
      layoutHash: compositionLayoutHash(firstLayout),
    },
    {
      id: "group-b",
      skuIds: ["sku-b"],
      productLayerIds: ["layer-b"],
      layout: secondLayout,
      layoutHash: compositionLayoutHash(secondLayout),
    },
  ];
  project.layoutState.objectTransforms = {
    "transform-a": { x: 0.5, y: 0.9, scale: 0.8, rotation: 0 },
    "transform-b": { x: 0.5, y: 0.72, scale: 0.8, rotation: 0 },
  };
  project.layoutState.productLayers = [
    {
      id: "layer-a",
      sourceAssetId: "working-a",
      renderAssetId: "working-a",
      allowOpaqueFallback: true,
      skuId: "sku-a",
      compositionGroupId: "group-a",
      transformId: "transform-a",
      locked: true,
    },
    {
      id: "layer-b",
      sourceAssetId: "working-b",
      renderAssetId: "working-b",
      allowOpaqueFallback: true,
      skuId: "sku-b",
      compositionGroupId: "group-b",
      transformId: "transform-b",
      locked: true,
    },
  ];
  const store = createProjectStore(project, { projectId: "a", revision: 1 });
  const controllerState: ProjectControllerState = {
    pendingSwitch: null,
    projects: [summary("a", "active", 1)],
    query: "",
    includeArchived: false,
    activeProjectId: "a",
    deleteCandidateId: null,
    loading: false,
    error: null,
    save: { status: "saved", dirty: false, message: null, currentRevision: null },
    remoteSync: { status: "idle", pendingRevision: null, message: null },
  };
  const controller = {
    getState: () => controllerState,
    subscribe: vi.fn(() => vi.fn()),
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
  const adapter = {
    mount: vi.fn(),
    project: vi.fn(),
    setMode: vi.fn(),
    focusBoard: vi.fn(),
    cancelPendingLoads: vi.fn(),
    dispose: vi.fn(),
  } satisfies CanvasAdapter;

  const mounted = mountWorkspace({ root, controller, store, adapter });
  const selector = root.querySelector<HTMLSelectElement>(
    '[data-testid="canvas-composition-group-select"]',
  );
  if (selector === null) throw new Error("missing composition group selector");
  expect([...selector.options].map((option) => option.value)).toEqual([
    "group-a",
    "group-b",
  ]);
  selector.value = "group-b";
  selector.dispatchEvent(new Event("change", { bubbles: true }));
  const baseline = root.querySelector<HTMLInputElement>('[data-field="baseline"]');
  if (baseline === null) throw new Error("missing baseline input");
  baseline.value = "0.61";
  baseline.dispatchEvent(new Event("change", { bubbles: true }));

  const [first, second] = store.getState().project.semanticState.compositionGroups;
  expect(first.layout.baseline).toBe(0.9);
  expect(second.layout.baseline).toBe(0.61);
  expect(second.layoutHash).toBe(compositionLayoutHash(second.layout));
  mounted.dispose();
});
