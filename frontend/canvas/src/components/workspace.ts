import type { AssetsApi } from "../api/assets";
import type { CompositionsApi } from "../api/compositions";
import type { CanvasGenerationProgress, CanvasProjectEvent } from "../api/events";
import { loadAllResultVersions, type GenerationsApi } from "../api/generations";
import type { ProjectSku, ProjectSnapshot } from "../api/client";
import type { ProvidersApi } from "../api/providers";
import type { ExportsApi } from "../api/exports";
import type { SkusApi } from "../api/skus";
import type { CanvasAdapter } from "../canvas/canvas-adapter";
import type { ProjectController } from "../controllers/project-controller";
import type {
  ProjectAction,
} from "../domain/types";
import {
  applyCutoutEvent,
  hydrateProjectedAsset,
  projectUploadedAsset,
  type AssetOperation,
  type AssetOperationProgress,
  type AssetRecord,
  type ProjectedAssetResult,
  type UploadedAssetBundle,
} from "../domain/assets";
import type { ProjectStore } from "../state/project-store";
import { createProjectSidebar } from "./project-sidebar";
import { createAssetInspector, type AssetInspector } from "./asset-inspector";
import { createAssetUploader, type AssetUploader } from "./asset-uploader";
import { createSkuEditor, type SkuEditor } from "./sku-editor";
import { createCompositionInspector } from "./composition-inspector";
import { createTextInspector } from "./text-inspector";
import { createStatusBar } from "./status-bar";
import { createTopToolbar } from "./top-toolbar";
import { createCompleteSetPanel } from "./complete-set-panel";
import { createGenerationStatus } from "./generation-status";
import { createNodeInspector } from "./node-inspector";
import { createNodeToolbar } from "./node-toolbar";
import { createResultBoard } from "./result-board";
import { createExportPanel, type ExportPanel } from "./export-panel";
import type { ResultVersion } from "../api/generations";
import { createGenerationController } from "../controllers/generation-controller";
import type { ModelProfile } from "../domain/providers";
import { previewGenerationRequest } from "../domain/generation";
import { compatibleEdgeKinds, createTypedEdge } from "../domain/node-ports";
import {
  canOpenInspectorTab,
  defaultInspectorTab,
  deriveCanvasWorkflowStage,
  type CanvasInspectorTab,
  type CanvasWorkflowSnapshot,
} from "../domain/workflow";
import { canvasUserMessage } from "../domain/user-message";

export interface WorkspaceOptions {
  root: HTMLElement;
  controller: ProjectController;
  store: ProjectStore;
  adapter: CanvasAdapter;
  assetsApi?: AssetsApi;
  compositionsApi?: CompositionsApi;
  skusApi?: SkusApi;
  providersApi?: ProvidersApi;
  generationsApi?: GenerationsApi;
  exportsApi?: ExportsApi;
  subscribeEvents?(listener: (event: CanvasProjectEvent) => void): () => void;
}

export interface MountedWorkspace {
  dispose(): void;
}

function preservesPropertyControls(action: ProjectAction): boolean {
  switch (action.type) {
    case "output/setQuantity":
    case "sku/setOutputQuantity":
    case "output/configure":
    case "board/selectResult":
    case "viewport/set":
    case "node/update":
    case "node/move":
    case "text/update":
    case "composition/update":
    case "asset/useRectangularSource":
      return true;
    default:
      return false;
  }
}

const GENERATION_STATUS_LABELS: Readonly<Record<string, string>> = {
  queued: "排队中",
  running: "生成中",
  retrying: "正在重试",
  succeeded: "已完成",
  failed: "失败",
  partially_failed: "部分完成",
  cancel_requested: "正在取消",
  cancelled: "已取消",
  unknown: "状态待确认",
};

function generationStatusLabel(status: string): string {
  return GENERATION_STATUS_LABELS[status] ?? "处理中";
}

function operationPhase(status: AssetOperationProgress["status"]): number {
  switch (status) {
    case "queued":
    case "cancel_requested":
      return 0;
    case "running":
      return 1;
    case "cancelled":
    case "failed":
    case "interrupted":
    case "succeeded":
      return 2;
  }
}

function laterOperation(
  left: AssetOperationProgress,
  right: AssetOperationProgress,
): AssetOperationProgress {
  const leftAttempt = left.attemptCount ?? -1;
  const rightAttempt = right.attemptCount ?? -1;
  if (leftAttempt !== rightAttempt) {
    return leftAttempt > rightAttempt ? left : right;
  }
  return operationPhase(left.status) >= operationPhase(right.status) ? left : right;
}

export function mountWorkspace({
  root,
  controller,
  store,
  adapter,
  assetsApi,
  compositionsApi,
  skusApi,
  providersApi,
  generationsApi,
  exportsApi,
  subscribeEvents,
}: WorkspaceOptions): MountedWorkspace {
  let disposed = false;
  let customNodeOrdinal = 0;
  let editable = false;
  let preservePropertiesDom = false;
  let assetUploader: AssetUploader | null = null;

  const shell = document.createElement("main");
  shell.className = "canvas-workspace";
  shell.dataset.testid = "canvas-workspace";
  shell.dataset.projectsOpen = "false";
  shell.dataset.inspectorOpen = "false";

  let activeInspectorTab: CanvasInspectorTab = "source";
  let exportRequested = false;
  let lastWorkflowStage: ReturnType<typeof deriveCanvasWorkflowStage> | null = null;
  let lastDrawerTrigger: HTMLElement | null = null;
  const drawerBackdrop = document.createElement("button");
  drawerBackdrop.type = "button";
  drawerBackdrop.className = "canvas-drawer-backdrop";
  drawerBackdrop.setAttribute("aria-label", "关闭侧栏");
  const setProjectsOpen = (open: boolean): void => {
    shell.dataset.projectsOpen = String(open);
    if (open) queueMicrotask(() => sidebar.element.querySelector<HTMLElement>("button, input, summary")?.focus());
    if (!open && lastDrawerTrigger?.isConnected) lastDrawerTrigger.focus();
  };
  const setInspectorOpen = (open: boolean): void => {
    shell.dataset.inspectorOpen = String(open);
    if (open) queueMicrotask(() => properties.querySelector<HTMLElement>("button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled])")?.focus());
    if (!open && lastDrawerTrigger?.isConnected) lastDrawerTrigger.focus();
  };
  const closeDrawers = (): void => {
    setProjectsOpen(false);
    setInspectorOpen(false);
  };
  drawerBackdrop.addEventListener("click", closeDrawers);
  const onWorkspaceKeydown = (event: KeyboardEvent): void => {
    if (event.key === "Escape") {
      closeDrawers();
      return;
    }
    if (event.key !== "Tab") return;
    const activeDrawer = shell.dataset.inspectorOpen === "true"
      ? properties
      : shell.dataset.projectsOpen === "true"
        ? sidebar.element
        : null;
    if (activeDrawer === null) return;
    const focusable = Array.from(activeDrawer.querySelectorAll<HTMLElement>(
      'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), summary, [href], [tabindex]:not([tabindex="-1"])',
    )).filter((candidate) => !candidate.hidden && candidate.getAttribute("aria-hidden") !== "true");
    if (focusable.length === 0) return;
    const first = focusable[0]!;
    const last = focusable[focusable.length - 1]!;
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };
  document.addEventListener("keydown", onWorkspaceKeydown);

  const sidebar = createProjectSidebar(controller);
  const center = document.createElement("section");
  center.className = "canvas-workspace-center";
  center.setAttribute("aria-label", "产品视觉画布工作区");
  const stage = document.createElement("div");
  stage.className = "canvas-stage";
  stage.dataset.testid = "canvas-stage";
  stage.setAttribute("role", "region");
  stage.setAttribute("aria-label", "无限画布视口");
  const canvas = document.createElement("canvas");
  canvas.width = 1_600;
  canvas.height = 1_000;
  canvas.dataset.testid = "canvas-surface";
  canvas.dataset.canvasSurface = "product-canvas";
  const stageEmpty = document.createElement("section");
  stageEmpty.className = "canvas-stage-empty";
  stageEmpty.dataset.testid = "canvas-stage-empty";
  const stageEmptyIcon = document.createElement("span");
  stageEmptyIcon.className = "canvas-stage-empty-icon";
  stageEmptyIcon.textContent = "+";
  stageEmptyIcon.setAttribute("aria-hidden", "true");
  const stageEmptyTitle = document.createElement("h2");
  const stageEmptyCopy = document.createElement("p");
  const stageUpload = document.createElement("button");
  stageUpload.type = "button";
  stageUpload.className = "canvas-primary-action";
  stageUpload.dataset.testid = "canvas-stage-upload";
  stageUpload.textContent = "上传主商品图片";
  stageUpload.addEventListener("click", () => assetUploader?.openPicker());
  const stageSteps = document.createElement("ol");
  for (const copy of ["上传并自动准备产品素材", "选择主图、SKU 图或详情图", "生成、挑选版本并导出"]) {
    stageSteps.append(Object.assign(document.createElement("li"), { textContent: copy }));
  }
  stageEmpty.append(stageEmptyIcon, stageEmptyTitle, stageEmptyCopy, stageUpload, stageSteps);
  stageEmpty.addEventListener("dragover", (event) => {
    if (editable) event.preventDefault();
  });
  stageEmpty.addEventListener("drop", (event) => {
    if (!editable) return;
    event.preventDefault();
    const file = event.dataTransfer?.files[0];
    if (file !== undefined) assetUploader?.uploadFile(file);
  });
  stage.append(canvas, stageEmpty);

  const properties = document.createElement("aside");
  properties.className = "canvas-properties";
  properties.dataset.testid = "canvas-properties";
  properties.setAttribute("aria-label", "属性设置");
  const propertiesHeader = document.createElement("header");
  propertiesHeader.className = "canvas-properties-header";
  const propertiesTitle = document.createElement("div");
  propertiesTitle.innerHTML = "<strong>创作流程</strong><span>按步骤完成产品套图</span>";
  const propertiesClose = document.createElement("button");
  propertiesClose.type = "button";
  propertiesClose.className = "canvas-properties-close";
  propertiesClose.textContent = "关闭";
  propertiesClose.setAttribute("aria-label", "关闭画布设置");
  propertiesClose.addEventListener("click", () => setInspectorOpen(false));
  propertiesHeader.append(propertiesTitle, propertiesClose);

  const propertiesTabs = document.createElement("div");
  propertiesTabs.className = "canvas-properties-tabs";
  propertiesTabs.setAttribute("role", "tablist");
  propertiesTabs.setAttribute("aria-label", "画布创作步骤");
  const inspectorPanels = new Map<CanvasInspectorTab, HTMLElement>();
  const inspectorButtons = new Map<CanvasInspectorTab, HTMLButtonElement>();
  for (const [tab, label] of [
    ["source", "素材"],
    ["generate", "生成"],
    ["results", "结果"],
    ["export", "导出"],
  ] as const) {
    const button = document.createElement("button");
    button.type = "button";
    button.role = "tab";
    button.textContent = label;
    button.dataset.inspectorTab = tab;
    button.id = `canvas-tab-${tab}`;
    button.setAttribute("aria-controls", `canvas-panel-${tab}`);
    button.addEventListener("click", () => {
      const snapshot = workflowSnapshot();
      if (!canOpenInspectorTab(tab, snapshot)) return;
      activeInspectorTab = tab;
      exportRequested = tab === "export";
      lastWorkflowStage = deriveCanvasWorkflowStage(workflowSnapshot());
      renderWorkflow();
    });
    const panel = document.createElement("div");
    panel.className = "canvas-properties-panel";
    panel.dataset.inspectorPanel = tab;
    panel.id = `canvas-panel-${tab}`;
    panel.role = "tabpanel";
    panel.setAttribute("aria-labelledby", button.id);
    propertiesTabs.append(button);
    inspectorButtons.set(tab, button);
    inspectorPanels.set(tab, panel);
  }
  const propertiesControls = document.createElement("div");
  propertiesControls.className = "canvas-properties-controls";

  const projectState = (): ReturnType<ProjectStore["getState"]>["project"] =>
    store.getState().project;

  const projectToAdapter = (
    previous: ReturnType<typeof projectState>,
  ): void => {
    const next = projectState();
    adapter.project(previous, next);
    if (previous.semanticState.mode !== next.semanticState.mode) {
      adapter.setMode(next.semanticState.mode);
    }
  };

  const dispatch = (action: ProjectAction): void => {
    if (!editable) {
      return;
    }
    const previous = projectState();
    const previousPreservation = preservePropertiesDom;
    preservePropertiesDom ||= preservesPropertyControls(action);
    let result;
    try {
      result = store.dispatch(action);
      if (result.confirmation !== undefined && window.confirm("此操作会解除已有结果关联，是否继续？")) {
        result = store.dispatch({
          ...action,
          acceptedDiffId: result.confirmation.token,
        } as ProjectAction);
      }
    } finally {
      preservePropertiesDom = previousPreservation;
    }
    if (result.applied) {
      projectToAdapter(previous);
    }
  };

  const undo = (): void => {
    if (!editable) {
      return;
    }
    const previous = projectState();
    if (store.undo()) {
      projectToAdapter(previous);
    }
  };
  const redo = (): void => {
    if (!editable) {
      return;
    }
    const previous = projectState();
    if (store.redo()) {
      projectToAdapter(previous);
    }
  };

  let exportPanel: ExportPanel | null = null;
  const toolbar = createTopToolbar(
    store,
    dispatch,
    undo,
    redo,
    exportsApi === undefined
      ? undefined
      : () => {
        activeInspectorTab = "export";
        exportRequested = true;
        renderWorkflow();
        lastDrawerTrigger = document.activeElement instanceof HTMLElement ? document.activeElement : null;
        setInspectorOpen(true);
      },
    {
      getProjectName: () => controller.getState().projects.find(
        (project) => project.id === controller.getState().activeProjectId,
      )?.name ?? null,
      canExport: () => projectState().semanticState.outputBoards.some(
        (board) => board.selectedResultAssetId !== null,
      ),
      onToggleProjects: () => {
        lastDrawerTrigger = document.activeElement instanceof HTMLElement ? document.activeElement : null;
        setProjectsOpen(shell.dataset.projectsOpen !== "true");
      },
      onToggleInspector: () => {
        lastDrawerTrigger = document.activeElement instanceof HTMLElement ? document.activeElement : null;
        setInspectorOpen(shell.dataset.inspectorOpen !== "true");
      },
    },
  );
  let activeCompositionGroupId: string | null = null;
  const compositionGroupField = document.createElement("label");
  compositionGroupField.className = "canvas-composition-group-field";
  compositionGroupField.textContent = "活动构图组";
  const compositionGroupSelect = document.createElement("select");
  compositionGroupSelect.dataset.testid = "canvas-composition-group-select";
  const compositionGroupCreate = document.createElement("button");
  compositionGroupCreate.type = "button";
  compositionGroupCreate.dataset.testid = "canvas-composition-group-create";
  compositionGroupCreate.textContent = "新建构图组";
  compositionGroupSelect.setAttribute("aria-label", "选择构图组");
  compositionGroupField.append(compositionGroupSelect, compositionGroupCreate);
  const compositionInspector = createCompositionInspector({
    onUpdate: (groupId, layout) => {
      dispatch({ type: "composition/update", groupId, layout });
    },
  });
  let activeTextLayerId: string | null = null;
  const nodeInspector = createNodeInspector();
  const textInspector = createTextInspector({
    onSelect: (layerId) => {
      activeTextLayerId = layerId;
      renderTextInspector();
    },
    onUpdate: (layerId, patch) => {
      dispatch({ type: "text/update", layerId, patch });
    },
  });
  const status = createStatusBar(
    () => {
      void controller.retrySave();
    },
    () => {
      void controller.retryRemoteSync();
    },
  );
  let activeProjectId: string | null = null;
  let activeProjection: ProjectedAssetResult | null = null;
  let knownAssets: AssetRecord[] = [];
  let knownOperations: AssetOperation[] = [];
  const bufferedOperationUpdates = new Map<string, AssetOperationProgress>();
  let skus: ProjectSku[] = [];
  let assetLoadAbort: AbortController | null = null;
  let lastControllerState = controller.getState();
  let assetInspector: AssetInspector | null = null;
  let skuEditor: SkuEditor | null = null;
  let composeAbort: AbortController | null = null;
  let composeBusy = false;
  let composeRequestEpoch = 0;
  let activeComposeOperationId: string | null = null;
  let selectedComposeBoardId: string | null = null;
  let selectedComposeBackgroundId: string | null = null;
  let lastComposeOperation: AssetOperationProgress | null = null;
  let resultVersions: ResultVersion[] = [];
  let latestGenerationStatus: string | null = null;
  const resultBoard = createResultBoard(assetsApi === undefined ? undefined : (assetId) => assetsApi.previewUrl(assetId));
  const resultBoardPickerField = document.createElement("label");
  resultBoardPickerField.className = "canvas-result-board-picker";
  resultBoardPickerField.textContent = "审阅画板";
  const resultBoardPicker = document.createElement("select");
  resultBoardPicker.setAttribute("aria-label", "选择要审阅的结果画板");
  resultBoardPicker.dataset.testid = "canvas-result-board-picker";
  resultBoardPickerField.append(resultBoardPicker);
  resultBoardPicker.addEventListener("change", () => {
    selectedComposeBoardId = resultBoardPicker.value || null;
    renderResultBoard();
  });
  let modelCatalog: ModelProfile[] = [];
  const generationStatus = createGenerationStatus();
  const generationController = generationsApi === undefined ? null : createGenerationController({
    store,
    autosave: { flush: () => controller.flushSave() },
    api: generationsApi,
    catalog: () => modelCatalog,
  });

  const submitGeneration = async (): Promise<void> => {
    if (generationController === null || generationsApi === undefined) {
      generationStatus.update("生成服务尚未配置", "error");
      return;
    }
    const run = async (): Promise<void> => {
      latestGenerationStatus = "submitting";
      activeInspectorTab = "results";
      renderWorkflow();
      generationStatus.update("正在保存并提交生成…", "working");
      const result = await generationController.submit();
      latestGenerationStatus = result.ok ? "queued" : null;
      generationStatus.update(
        result.ok ? `已创建生成任务 ${result.generationId}` : canvasUserMessage(result.message, "生成任务提交失败，请重试"),
        result.ok ? "success" : "error",
      );
      renderWorkflow();
    };
    await run();
  };

  const completeSetPanel = createCompleteSetPanel({
    getProject: projectState,
    getRevision: () => store.getState().runtime.revision,
    getModels: () => modelCatalog,
    getSkus: () => skus,
    getReferenceAssets: () => knownAssets
      .filter((asset) => asset.assetType === "working" || asset.assetType === "cutout")
      .map((asset) => ({ id: asset.id, label: asset.originalFilename || asset.id })),
    isEditable: () => editable,
    dispatch,
    onGenerate: () => { void submitGeneration(); },
  });
  const reportUnexpectedAccessDenial = (_retry: () => void): void => {
    generationStatus.update("请求被服务拒绝，请刷新页面后重试", "error");
  };
  if (exportsApi !== undefined) {
    exportPanel = createExportPanel({
      api: exportsApi,
      getProject: projectState,
      getProjectId: () => activeProjectId,
      getRevision: () => store.getState().runtime.revision,
      getVersions: () => resultVersions,
      isEditable: () => editable,
      flushSave: () => controller.flushSave(),
      onUnauthorized: reportUnexpectedAccessDenial,
      onOperation: (operation) => {
        knownOperations = [
          ...knownOperations.filter((candidate) => candidate.id !== operation.id),
          operation,
        ];
        bufferedOperationUpdates.set(operation.id, operation);
      },
    });
  }
  const composeControls = document.createElement("section");
  composeControls.className = "canvas-compose-controls";
  composeControls.dataset.testid = "canvas-compose-controls";
  const composeBoard = document.createElement("select");
  composeBoard.dataset.testid = "canvas-compose-board";
  const composeBackground = document.createElement("select");
  composeBackground.dataset.testid = "canvas-compose-background";
  const composeSubmit = document.createElement("button");
  composeSubmit.type = "button";
  composeSubmit.dataset.testid = "canvas-compose-submit";
  composeSubmit.textContent = "合成产品图";
  const composeFeedback = document.createElement("p");
  composeFeedback.dataset.testid = "canvas-compose-feedback";

  const composeStatusMessage = (operation: AssetOperationProgress): string =>
    operation.status === "succeeded"
      ? "合成完成"
      : operation.status === "failed"
        ? "合成失败，可从任务状态重试"
        : operation.status === "queued"
          ? "合成任务已进入队列"
          : "合成处理中";

  const renderComposeControls = (): void => {
    const boards = projectState().semanticState.outputBoards;
    const backgrounds = knownAssets.filter(
      (asset) => asset.assetType === "generated_background" || asset.assetType === "working",
    );
    if (!boards.some((board) => board.id === selectedComposeBoardId)) {
      selectedComposeBoardId = boards[0]?.id ?? null;
    }
    if (!backgrounds.some((asset) => asset.id === selectedComposeBackgroundId)) {
      selectedComposeBackgroundId = backgrounds[0]?.id ?? null;
    }
    composeBoard.replaceChildren(...boards.map((board) => Object.assign(
      document.createElement("option"),
      { value: board.id, textContent: `${board.outputType} · ${board.id}` },
    )));
    composeBoard.value = selectedComposeBoardId ?? "";
    composeBackground.replaceChildren(...backgrounds.map((asset) => Object.assign(
      document.createElement("option"),
      { value: asset.id, textContent: asset.originalFilename || asset.id },
    )));
    composeBackground.value = selectedComposeBackgroundId ?? "";
    const disabled = !editable || composeBusy || compositionsApi === undefined
      || selectedComposeBoardId === null || selectedComposeBackgroundId === null;
    composeBoard.disabled = disabled;
    composeBackground.disabled = disabled;
    composeSubmit.disabled = disabled;
    const children: HTMLElement[] = [
      Object.assign(document.createElement("h3"), { textContent: "权威合成" }),
      composeBoard,
      composeBackground,
      composeSubmit,
      composeFeedback,
    ];
    if (
      lastComposeOperation?.status === "succeeded"
      && lastComposeOperation.outputAssetId != null
      && assetsApi !== undefined
    ) {
      const preview = document.createElement("img");
      preview.className = "canvas-compose-preview";
      preview.dataset.testid = "canvas-compose-preview";
      preview.alt = "合成结果预览";
      preview.src = assetsApi.previewUrl(lastComposeOperation.outputAssetId);
      children.push(preview);
    }
    composeControls.replaceChildren(...children);
  };

  composeBoard.addEventListener("change", () => {
    selectedComposeBoardId = composeBoard.value || null;
  });
  composeBackground.addEventListener("change", () => {
    selectedComposeBackgroundId = composeBackground.value || null;
  });
  composeSubmit.addEventListener("click", () => {
    if (
      composeBusy
      || compositionsApi === undefined
      || activeProjectId === null
      || selectedComposeBoardId === null
      || selectedComposeBackgroundId === null
    ) return;
    const requestProjectId = activeProjectId;
    const requestEpoch = ++composeRequestEpoch;
    const boardId = selectedComposeBoardId;
    const backgroundAssetId = selectedComposeBackgroundId;
    composeBusy = true;
    composeFeedback.textContent = "正在保存并提交合成…";
    renderComposeControls();
    void (async () => {
      const flushed = await controller.flushSave();
      if (
        !flushed.ok
        || disposed
        || requestEpoch !== composeRequestEpoch
        || activeProjectId !== requestProjectId
      ) {
        composeFeedback.textContent = flushed.ok ? "项目已切换，未提交合成" : "请先解决保存问题";
        composeBusy = false;
        renderComposeControls();
        return;
      }
      const requestController = new AbortController();
      composeAbort?.abort();
      composeAbort = requestController;
      activeComposeOperationId = null;
      lastComposeOperation = null;
      const requestId = typeof crypto.randomUUID === "function"
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random()}`;
      const result = await compositionsApi.enqueueCompose({
        projectId: requestProjectId,
        revision: store.getState().runtime.revision,
        boardId,
        backgroundAssetId,
        clientRequestId: `compose:${requestId}`,
        signal: requestController.signal,
      });
      if (
        disposed
        || requestEpoch !== composeRequestEpoch
        || activeProjectId !== requestProjectId
        || composeAbort !== requestController
      ) return;
      composeAbort = null;
      composeBusy = false;
      if (!result.ok) {
        composeFeedback.textContent = result.kind === "conflict"
          ? `项目版本已更新到 ${result.currentRevision}，请刷新后重试`
          : canvasUserMessage(result.message, "合成请求失败，请重试");
        renderComposeControls();
        return;
      }
      activeComposeOperationId = result.value.id;
      const buffered = bufferedOperationUpdates.get(result.value.id);
      lastComposeOperation = buffered === undefined
        ? result.value
        : laterOperation(result.value, buffered);
      composeFeedback.textContent = composeStatusMessage(lastComposeOperation);
      renderComposeControls();
    })().catch(() => {
      if (
        !disposed
        && requestEpoch === composeRequestEpoch
        && activeProjectId === requestProjectId
      ) {
        composeAbort = null;
        composeBusy = false;
        composeFeedback.textContent = "合成请求失败，请重试";
        renderComposeControls();
      }
    });
  });

  const renderStatus = (): void => {
    status.update(
      lastControllerState.save,
      lastControllerState.remoteSync,
      activeProjection?.asset.cutoutStatus ?? null,
    );
  };

  const renderSkuEditor = (): void => {
    if (skuEditor === null || activeProjectId === null) {
      skuEditor?.update(null);
      return;
    }
    const mainProduct = projectState().layoutState.productLayers.find(
      (layer) => layer.skuId === null && layer.locked,
    );
    skuEditor.update({
      projectId: activeProjectId,
      revision: store.getState().runtime.revision,
      skus,
      mainProductAssetId: mainProduct?.renderAssetId ?? null,
      referenceAssets: knownAssets
        .filter((asset) => asset.assetType === "working")
        .map((asset) => ({
          id: asset.id,
          label: asset.originalFilename || asset.id,
        })),
      disabled: !editable,
    });
  };

  const applyProjection = (projection: ProjectedAssetResult): void => {
    const previous = projectState();
    if (JSON.stringify(previous) !== JSON.stringify(projection.project)) {
      const runtime = store.getState().runtime;
      store.replaceProject(projection.project, {
        projectId: runtime.projectId,
        revision: runtime.revision,
      });
      adapter.project(previous, projection.project);
      if (previous.semanticState.mode !== projection.project.semanticState.mode) {
        adapter.setMode(projection.project.semanticState.mode);
      }
    }
    activeProjection = {
      project: projectState(),
      asset: structuredClone(projection.asset),
    };
    assetInspector?.update(activeProjection.asset);
    renderSkuEditor();
    renderStatus();
    renderWorkflow();
  };

  const applyOperation = (operation: AssetOperationProgress): void => {
    if (activeProjection === null) {
      return;
    }
    const currentMainProduct = projectState().layoutState.productLayers.find(
      (layer) => layer.skuId === null && layer.locked,
    );
    if (currentMainProduct?.sourceAssetId !== activeProjection.asset.workingAssetId) {
      return;
    }
    const current = {
      project: projectState(),
      asset: activeProjection.asset,
    };
    const next = applyCutoutEvent(current, operation);
    if (next !== current) {
      applyProjection(next);
    }
  };

  const onUploaded = (upload: UploadedAssetBundle): void => {
    if (activeProjectId === null || upload.source.projectId !== activeProjectId) {
      return;
    }
    const uploadedIds = new Set([
      upload.source.id,
      upload.working.id,
      upload.preview.id,
    ]);
    knownAssets = [
      ...knownAssets.filter((asset) => !uploadedIds.has(asset.id)),
      upload.source,
      upload.working,
      upload.preview,
    ];
    if (upload.operation !== null) {
      if (!knownOperations.some((operation) => operation.id === upload.operation?.id)) {
        knownOperations = [...knownOperations, upload.operation];
      }
    }
    applyProjection(projectUploadedAsset(projectState(), upload));
    if (upload.operation !== null) {
      const authoritative = knownOperations.find(
        (operation) => operation.id === upload.operation?.id,
      ) ?? upload.operation;
      const buffered = bufferedOperationUpdates.get(upload.operation.id);
      applyOperation(buffered === undefined
        ? authoritative
        : laterOperation(authoritative, buffered));
    }
  };

  const onFallback = (): void => {
    if (activeProjection === null) {
      return;
    }
    dispatch({
      type: "asset/useRectangularSource",
      workingAssetId: activeProjection.asset.workingAssetId,
    });
    activeProjection = {
      project: projectState(),
      asset: {
        ...activeProjection.asset,
        renderAssetId: activeProjection.asset.workingAssetId,
        allowOpaqueFallback: true,
      },
    };
    assetInspector?.update(activeProjection.asset);
    renderStatus();
    renderWorkflow();
  };

  if (assetsApi !== undefined) {
    assetUploader = createAssetUploader({ api: assetsApi, onUploaded });
    assetInspector = createAssetInspector({
      api: assetsApi,
      onOperation: (operation) => {
        knownOperations = [
          ...knownOperations.filter((candidate) => candidate.id !== operation.id),
          operation,
        ];
        bufferedOperationUpdates.set(operation.id, operation);
        applyOperation(operation);
      },
      onFallback,
    });
  }
  if (skusApi !== undefined) {
    skuEditor = createSkuEditor({
      api: skusApi,
      onSnapshot: (snapshot: ProjectSnapshot) => {
        if (snapshot.project.id !== activeProjectId) {
          return;
        }
        skus = snapshot.skus;
        controller.adoptMutationSnapshot(snapshot);
        renderSkuEditor();
      },
    });
  }

  const sourcePanel = inspectorPanels.get("source")!;
  const generatePanel = inspectorPanels.get("generate")!;
  const resultsPanel = inspectorPanels.get("results")!;
  const exportPanelHost = inspectorPanels.get("export")!;
  generatePanel.append(
    propertiesControls,
    compositionGroupField,
    compositionInspector.element,
    textInspector.element,
    composeControls,
  );
  resultsPanel.append(generationStatus.element, resultBoardPickerField, resultBoard.element);
  if (exportPanel !== null) exportPanelHost.append(exportPanel.element);
  if (assetUploader !== null && assetInspector !== null) {
    sourcePanel.append(assetUploader.element, assetInspector.element);
  }
  if (skuEditor !== null) {
    sourcePanel.append(skuEditor.element);
  }
  properties.append(
    propertiesHeader,
    propertiesTabs,
    ...inspectorPanels.values(),
  );
  center.append(toolbar.element, stage, status.element);
  shell.append(sidebar.element, center, properties, drawerBackdrop);
  root.replaceChildren(shell);

  function workflowSnapshot(): CanvasWorkflowSnapshot {
    const hasSelectedResult = projectState().semanticState.outputBoards.some((board) => (
      board.selectedResultAssetId !== null
      && resultVersions.some(
        (version) => version.boardId === board.id
          && version.composedAssetId === board.selectedResultAssetId,
      )
    ));
    return {
      hasProject: activeProjectId !== null,
      hasSource: activeProjection !== null,
      processing: activeProjection?.asset.cutoutStatus === "queued"
        || activeProjection?.asset.cutoutStatus === "running",
      generating: latestGenerationStatus !== null
        && !["succeeded", "failed", "partially_failed", "cancelled", "unknown"].includes(
          latestGenerationStatus,
        ),
      hasResults: resultVersions.length > 0,
      hasSelectedResult,
      exportRequested,
    };
  }

  function renderWorkflow(): void {
    const snapshot = workflowSnapshot();
    const cutoutFailed = activeProjection?.asset.cutoutStatus === "failed";
    if (!snapshot.hasSelectedResult) exportRequested = false;
    const stageValue = deriveCanvasWorkflowStage({ ...snapshot, exportRequested });
    shell.dataset.workflowStage = stageValue;
    if (stageValue !== lastWorkflowStage) {
      activeInspectorTab = cutoutFailed ? "source" : defaultInspectorTab(stageValue);
      lastWorkflowStage = stageValue;
    }
    if (cutoutFailed) activeInspectorTab = "source";
    if (!canOpenInspectorTab(activeInspectorTab, snapshot)) {
      activeInspectorTab = defaultInspectorTab(stageValue);
    }

    const stageLabels: Record<typeof stageValue, [string, string]> = {
      project: ["先创建一个产品项目", "每个项目会独立保存素材、提示词、结果和导出设置。"],
      source: ["上传主商品图片", "支持 JPG、PNG、WebP。上传后会自动检测并准备可用于生成的产品素材。"],
      processing: ["正在准备产品素材", "系统正在检测背景并处理产品图，完成后会自动进入生成设置。"],
      configure: ["设置要生成的产品套图", "在右侧选择主图、SKU 图或详情图，并分别设置模型与提示词。"],
      generating: ["正在生成产品套图", "任务在后台运行，可以留在当前页面查看进度。"],
      results: ["审阅生成结果", "从每个画板的成功版本中选择最终结果，再进入导出。"],
      export: ["导出已选产品图", "选择画板、导出方式与格式后生成下载文件。"],
    };
    const [titleText, copyText] = cutoutFailed
      ? ["产品素材处理失败", "查看失败原因并重新抠图，或明确选择使用原图矩形继续。"]
      : stageLabels[stageValue];
    propertiesTitle.querySelector("strong")!.textContent = titleText;
    propertiesTitle.querySelector("span")!.textContent = copyText;
    stageEmptyTitle.textContent = titleText;
    stageEmptyCopy.textContent = copyText;
    stageEmpty.hidden = snapshot.hasSource && !snapshot.processing;
    stageEmpty.dataset.state = stageValue;
    stageUpload.disabled = !snapshot.hasProject || snapshot.processing;
    stageUpload.hidden = snapshot.processing;
    stageSteps.hidden = snapshot.processing;

    for (const [tab, button] of inspectorButtons) {
      const allowed = canOpenInspectorTab(tab, snapshot);
      button.hidden = tab !== "source" && !allowed;
      button.disabled = !allowed;
      button.setAttribute("aria-selected", String(activeInspectorTab === tab));
      button.tabIndex = activeInspectorTab === tab ? 0 : -1;
      const panel = inspectorPanels.get(tab)!;
      panel.hidden = activeInspectorTab !== tab;
    }
    toolbar.update();
  }

  if (providersApi !== undefined) {
    void providersApi.loadCatalog().then((result) => {
      if (disposed) return;
      if (!result.ok) {
        generationStatus.update(canvasUserMessage(result.message, "图像模型目录加载失败，请重试"), "error");
        return;
      }
      modelCatalog = result.value;
      completeSetPanel.update();
      renderProperties();
    }).catch(() => {
      if (!disposed) generationStatus.update("模型目录加载失败", "error");
    });
  }

  const renderProperties = (): void => {
    const current = projectState();
    const heading = document.createElement("h2");
    heading.textContent = "属性设置";
    const modeCopy = document.createElement("p");
    modeCopy.textContent =
      current.semanticState.mode === "complete-set"
        ? "选择套图输出并设置数量与提示词。"
        : "高级模式保留同一画布与项目状态。";
    propertiesControls.replaceChildren(heading, modeCopy);

    if (current.semanticState.mode === "advanced") {
      const nodeToolbar = createNodeToolbar({
        disabled: !editable,
        nextId: (kind) => {
          let id: string;
          do {
            customNodeOrdinal += 1;
            id = `advanced:${kind}:${customNodeOrdinal}`;
          } while (current.semanticState.nodes.some((node) => node.id === id));
          return id;
        },
        onAdd: (node) => {
          dispatch({ type: "node/add", node });
          dispatch({
            type: "node/move",
            nodeId: node.id,
            position: { x: 120 + customNodeOrdinal * 24, y: 120 },
          });
        },
      });
      nodeInspector.update(current.semanticState.nodes, modelCatalog, !editable, (nodeId, patch) => {
        dispatch({
          type: "node/update",
          nodeId,
          patch,
        });
      }, (sourceNodeId, targetNodeId) => {
        const source = current.semanticState.nodes.find((node) => node.id === sourceNodeId);
        const target = current.semanticState.nodes.find((node) => node.id === targetNodeId);
        if (source === undefined || target === undefined) return;
        const kind = compatibleEdgeKinds(source.kind, target.kind)[0];
        if (kind === undefined) return;
        let ordinal = 1;
        let edgeId = `advanced:edge:${sourceNodeId}:${targetNodeId}:${kind}:${ordinal}`;
        while (current.semanticState.edges.some((edge) => edge.id === edgeId)) {
          ordinal += 1;
          edgeId = `advanced:edge:${sourceNodeId}:${targetNodeId}:${kind}:${ordinal}`;
        }
        dispatch({
          type: "edge/connect",
          edge: createTypedEdge(edgeId, kind, sourceNodeId, targetNodeId),
        });
      });
      const validation = previewGenerationRequest(current, modelCatalog, store.getState().runtime.revision);
      const generate = document.createElement("button");
      generate.type = "button";
      generate.dataset.testid = "canvas-generate-advanced";
      generate.textContent = validation.ok ? "生成高级画布" : validation.reasons.map((reason) => reason.message).join("；");
      generate.disabled = !editable || !validation.ok;
      generate.addEventListener("click", () => { void submitGeneration(); });
      propertiesControls.append(nodeToolbar, nodeInspector.element, generate);
      if (current.semanticState.outputBoards.length === 0) {
        const emptyRoute = document.createElement("button");
        emptyRoute.type = "button";
        emptyRoute.textContent = "返回套图模式选择输出";
        emptyRoute.disabled = !editable;
        emptyRoute.addEventListener("click", () => dispatch({ type: "mode/set", mode: "complete-set" }));
        propertiesControls.append(
          Object.assign(document.createElement("p"), { textContent: "高级图谱需要至少一个输出画板。请先在套图模式选择主图、SKU 图或详情图；已有节点不会丢失。" }),
          emptyRoute,
        );
      }
      return;
    }

    completeSetPanel.update();
    propertiesControls.append(completeSetPanel.element);
  };

  const renderResultBoard = (): void => {
    const boards = projectState().semanticState.outputBoards;
    const boardLabel = (board: (typeof boards)[number]): string => {
      const type = board.outputType === "main" ? "主图" : board.outputType === "sku" ? "SKU 图" : "详情图";
      const ordinal = boards.filter((candidate) => (
        candidate.outputType === board.outputType && candidate.sortOrder <= board.sortOrder
      )).length;
      return `${type} ${ordinal}`;
    };
    if (!boards.some((board) => board.id === selectedComposeBoardId)) {
      selectedComposeBoardId = boards[0]?.id ?? null;
    }
    resultBoardPicker.replaceChildren(...boards.map((board) => Object.assign(
      document.createElement("option"),
      { value: board.id, textContent: boardLabel(board) },
    )));
    resultBoardPicker.value = selectedComposeBoardId ?? "";
    resultBoardPickerField.hidden = boards.length <= 1;
    const selected = boards.find((board) => board.id === selectedComposeBoardId) ?? boards[0] ?? null;
    resultBoard.update(selected, resultVersions, !editable, (assetId) => {
      if (selected !== null) {
        dispatch({ type: "board/selectResult", boardId: selected.id, assetId });
        const version = assetId === null
          ? null
          : resultVersions.find(
              (candidate) => candidate.boardId === selected.id && candidate.composedAssetId === assetId,
            ) ?? null;
        adapter.setResultBackgroundPreview?.(version?.backgroundPreviewAssetId ?? null);
      }
    });
    const version = selected?.selectedResultAssetId === null || selected === null
      ? null
      : resultVersions.find(
          (candidate) => candidate.boardId === selected.id && candidate.composedAssetId === selected.selectedResultAssetId,
        ) ?? null;
    adapter.setResultBackgroundPreview?.(version?.backgroundPreviewAssetId ?? null);
    exportPanel?.update();
  };

  const loadResultVersions = async (projectId: string): Promise<void> => {
    if (generationsApi === undefined) return;
    const result = await loadAllResultVersions(generationsApi, projectId);
    if (disposed || activeProjectId !== projectId || !result.ok) return;
    resultVersions = result.value;
    const assetIdsByBoard = new Map<string, string[]>();
    for (const version of resultVersions) {
      const assetIds = assetIdsByBoard.get(version.boardId) ?? [];
      assetIds.push(version.composedAssetId);
      assetIdsByBoard.set(version.boardId, assetIds);
    }
    for (const board of projectState().semanticState.outputBoards) {
      store.dispatch({
        type: "runtime/setAllowedResultAssets",
        boardId: board.id,
        assetIds: assetIdsByBoard.get(board.id) ?? [],
      });
    }
    renderResultBoard();
    renderWorkflow();
  };

  const loadAssets = async (projectId: string): Promise<void> => {
    if (assetsApi === undefined) {
      return;
    }
    assetLoadAbort?.abort();
    const controller = new AbortController();
    assetLoadAbort = controller;
    let assetsResult: Awaited<ReturnType<AssetsApi["listAssets"]>>;
    let operationsResult: Awaited<ReturnType<AssetsApi["listOperations"]>>;
    try {
      [assetsResult, operationsResult] = await Promise.all([
        assetsApi.listAssets(projectId, controller.signal),
        assetsApi.listOperations(projectId, controller.signal),
      ]);
    } catch {
      // Project switches abort both requests; typed clients return safe failures otherwise.
      if (assetLoadAbort === controller) {
        assetLoadAbort = null;
      }
      return;
    }
    if (
      disposed ||
      controller.signal.aborted ||
      assetLoadAbort !== controller ||
      activeProjectId !== projectId
    ) {
      return;
    }
    assetLoadAbort = null;
    if (!assetsResult.ok || !operationsResult.ok) {
      return;
    }
    knownAssets = assetsResult.value;
    knownOperations = operationsResult.value;
    const latestExport = knownOperations.find((operation) => operation.operationType === "export");
    if (latestExport !== undefined) exportPanel?.applyOperation(latestExport);
    renderComposeControls();
    renderResultBoard();
    const hydrated = hydrateProjectedAsset(projectState(), knownAssets, knownOperations);
    if (hydrated === null) {
      activeProjection = null;
      assetInspector?.update(null);
      renderSkuEditor();
      renderStatus();
      renderWorkflow();
      return;
    }
    applyProjection(hydrated);
    const buffered = bufferedOperationUpdates.get(hydrated.asset.operationId ?? "");
    const authoritative = knownOperations.find(
      (operation) => operation.id === hydrated.asset.operationId,
    );
    if (buffered !== undefined) {
      applyOperation(authoritative === undefined
        ? buffered
        : laterOperation(authoritative, buffered));
    }
  };

  const renderGenerationProgress = (generation: CanvasGenerationProgress): void => {
    latestGenerationStatus = generation.status;
    const rawDetail = generation.safeErrorSummary ?? generation.safeStorageBlockReason;
    const detail = rawDetail === null
      ? null
      : canvasUserMessage(rawDetail, "生成失败，请检查模型配置后重试");
    const terminalFailure = new Set(["failed", "partially_failed", "cancelled", "unknown"]);
    generationStatus.update(
      detail ?? `任务 ${generationStatusLabel(generation.status)}（成功 ${generation.succeededItems}/${generation.totalItems}）`,
      detail !== null
        ? "error"
        : generation.status === "succeeded"
          ? "success"
          : terminalFailure.has(generation.status)
            ? "error"
            : "working",
    );
    if (generation.succeededItems > 0 && activeProjectId !== null) {
      void loadResultVersions(activeProjectId);
    }
    renderWorkflow();
  };

  const unsubscribeEvents = subscribeEvents?.((event) => {
    if (disposed || activeProjectId === null) {
      return;
    }
    if (event.type === "snapshot") {
      if (event.snapshot.project.id !== activeProjectId) {
        return;
      }
      skus = event.snapshot.skus;
      knownOperations = event.operations;
      bufferedOperationUpdates.clear();
      resultVersions = [];
      const latestExport = knownOperations.find((operation) => operation.operationType === "export");
      if (latestExport !== undefined) exportPanel?.applyOperation(latestExport);
      const persistedGeneration = event.generations?.[0];
      if (persistedGeneration !== undefined) renderGenerationProgress(persistedGeneration);
      renderSkuEditor();
      void loadAssets(activeProjectId);
      return;
    }
    if (event.projectId !== activeProjectId) {
      return;
    }
    if ("generation" in event) {
      renderGenerationProgress(event.generation);
      return;
    }
    if (event.type === "asset.uploaded" || event.type === "asset.deleted") {
      void loadAssets(activeProjectId);
      return;
    }
    if ("operation" in event) {
      bufferedOperationUpdates.set(event.operation.id, event.operation);
      if (event.operation.operationType === "export") {
        exportPanel?.applyOperation(event.operation);
        return;
      }
      if (event.operation.operationType === "compose") {
        if (event.operation.id !== activeComposeOperationId) return;
        lastComposeOperation = lastComposeOperation === null
          ? event.operation
          : laterOperation(lastComposeOperation, event.operation);
        composeFeedback.textContent = composeStatusMessage(lastComposeOperation);
        renderComposeControls();
        return;
      }
      applyOperation(event.operation);
    }
  }) ?? (() => {});

  adapter.mount(canvas, dispatch);
  const initialProject = projectState();
  adapter.project(null, initialProject);
  adapter.setMode(initialProject.semanticState.mode);

  const renderCompositionInspector = (): void => {
    const groups = projectState().semanticState.compositionGroups;
    const active = groups.find((group) => group.id === activeCompositionGroupId)
      ?? groups[0];
    activeCompositionGroupId = active?.id ?? null;
    compositionGroupSelect.replaceChildren(
      ...(groups.length === 0
        ? [Object.assign(document.createElement("option"), {
            value: "",
            textContent: "暂无构图组",
          })]
        : groups.map((group, index) => Object.assign(document.createElement("option"), {
            value: group.id,
            textContent: `构图组 ${index + 1} · ${group.id}`,
          }))),
    );
    compositionGroupSelect.value = activeCompositionGroupId ?? "";
    compositionGroupSelect.disabled = !editable || groups.length === 0;
    compositionGroupCreate.disabled = !editable || !projectState().layoutState.productLayers.some(
      (layer) => layer.skuId === null && layer.locked && layer.compositionGroupId === null,
    );
    compositionInspector.update(
      active === undefined
        ? null
        : { groupId: active.id, layout: active.layout, disabled: !editable },
    );
  };
  function renderTextInspector(): void {
    const layers = projectState().layoutState.textSnapshots;
    if (!layers.some((layer) => layer.id === activeTextLayerId)) {
      activeTextLayerId = layers[0]?.id ?? null;
    }
    textInspector.update({
      layers,
      selectedLayerId: activeTextLayerId,
      disabled: !editable,
    });
  }
  compositionGroupSelect.addEventListener("change", () => {
    if (!editable) return;
    const groupId = compositionGroupSelect.value;
    if (!projectState().semanticState.compositionGroups.some((group) => group.id === groupId)) {
      return;
    }
    activeCompositionGroupId = groupId;
    renderCompositionInspector();
    renderTextInspector();
    renderComposeControls();
    exportPanel?.update();
  });
  compositionGroupCreate.addEventListener("click", () => {
    if (!editable) return;
    const before = projectState().semanticState.compositionGroups.length;
    const mainProduct = projectState().layoutState.productLayers.find(
      (layer) => layer.skuId === null && layer.locked,
    );
    if (mainProduct === undefined) return;
    dispatch({
      type: "composition/create",
      skuProducts: skus.map((sku) => {
        const usesMainProduct = sku.referenceAssetId === null;
        const sourceAssetId = sku.referenceAssetId ?? mainProduct.sourceAssetId;
        return {
          skuId: sku.id,
          sourceAssetId,
          renderAssetId: usesMainProduct ? mainProduct.renderAssetId : sourceAssetId,
          allowOpaqueFallback: usesMainProduct ? mainProduct.allowOpaqueFallback : false,
        };
      }),
    });
    const created = projectState().semanticState.compositionGroups[before];
    if (created === undefined) return;
    activeCompositionGroupId = created.id;
    renderCompositionInspector();
  });

  const renderStore = (): void => {
    toolbar.update();
    if (!preservePropertiesDom) {
      renderProperties();
    }
    renderCompositionInspector();
    renderTextInspector();
    renderComposeControls();
    renderWorkflow();
  };
  renderStore();
  const unsubscribeStore = store.subscribe(renderStore);
  const renderController = (state: ReturnType<ProjectController["getState"]>): void => {
    const changedProject = activeProjectId !== state.activeProjectId;
    lastControllerState = state;
    editable = state.activeProjectId !== null;
    activeProjectId = state.activeProjectId;
    if (changedProject) {
      latestGenerationStatus = null;
      exportRequested = false;
      activeInspectorTab = "source";
      lastWorkflowStage = null;
      composeRequestEpoch += 1;
      composeBusy = false;
      activeComposeOperationId = null;
      activeCompositionGroupId = null;
      activeTextLayerId = null;
      selectedComposeBoardId = null;
      selectedComposeBackgroundId = null;
      lastComposeOperation = null;
      exportPanel?.reset();
    }
    sidebar.update(state);
    toolbar.setEditable(editable);
    shell.dataset.editable = String(editable);
    stage.inert = !editable;
    properties.inert = !editable;
    stage.setAttribute("aria-disabled", String(!editable));
    properties.setAttribute("aria-disabled", String(!editable));
    renderCompositionInspector();
    shell.dataset.activeProjectId = state.activeProjectId ?? "";
    assetUploader?.setDisabled(!editable);
    assetUploader?.setProject(activeProjectId);
    assetInspector?.setDisabled(!editable);
    const snapshotGetter = (
      controller as ProjectController & {
        getActiveSnapshot?: () => ProjectSnapshot | null;
      }
    ).getActiveSnapshot;
    const snapshot = snapshotGetter?.call(controller) ?? null;
    if (snapshot !== null && snapshot.project.id === activeProjectId) {
      skus = snapshot.skus;
    }
    const currentMainProduct = projectState().layoutState.productLayers.find(
      (layer) => layer.skuId === null && layer.locked,
    );
    const replacedSameProjectState =
      activeProjection !== null &&
      currentMainProduct?.sourceAssetId !== activeProjection.asset.workingAssetId;
    if (changedProject || replacedSameProjectState) {
      assetLoadAbort?.abort();
      assetLoadAbort = null;
      composeAbort?.abort();
      composeAbort = null;
      activeProjection = null;
      knownAssets = [];
      knownOperations = [];
      bufferedOperationUpdates.clear();
      assetInspector?.update(null);
      if (activeProjectId !== null) {
        void loadAssets(activeProjectId);
        void loadResultVersions(activeProjectId);
      }
    }
    renderSkuEditor();
    renderStatus();
    renderTextInspector();
    renderComposeControls();
    renderResultBoard();
    renderWorkflow();
  };
  renderController(controller.getState());
  const unsubscribeController = controller.subscribe(renderController);

  return {
    dispose: () => {
      if (disposed) {
        return;
      }
      disposed = true;
      assetLoadAbort?.abort();
      assetLoadAbort = null;
      composeAbort?.abort();
      composeAbort = null;
      unsubscribeStore();
      unsubscribeController();
      unsubscribeEvents();
      assetUploader?.dispose();
      assetInspector?.dispose();
      skuEditor?.dispose();
      exportPanel?.dispose();
      document.removeEventListener("keydown", onWorkspaceKeydown);
      compositionInspector.dispose();
      textInspector.dispose();
      controller.dispose();
      adapter.dispose();
      root.replaceChildren();
    },
  };
}
