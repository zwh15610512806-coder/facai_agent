import type { CanvasViewport, ProjectAction } from "../domain/types";
import type { ProjectStore } from "../state/project-store";

export interface TopToolbar {
  element: HTMLElement;
  update(): void;
  setEditable(editable: boolean): void;
}

export interface TopToolbarOptions {
  getProjectName?(): string | null;
  canExport?(): boolean;
  onToggleProjects?(): void;
  onToggleInspector?(): void;
}

export function createTopToolbar(
  store: ProjectStore,
  dispatch: (action: ProjectAction) => void,
  undo: () => void,
  redo: () => void,
  onExport?: () => void,
  options: TopToolbarOptions = {},
): TopToolbar {
  let editable = false;
  const element = document.createElement("header");
  element.className = "canvas-top-toolbar";
  element.dataset.testid = "canvas-top-toolbar";

  const projectsToggle = document.createElement("button");
  projectsToggle.type = "button";
  projectsToggle.className = "canvas-drawer-toggle canvas-projects-toggle";
  projectsToggle.dataset.testid = "canvas-toggle-projects";
  projectsToggle.textContent = "项目";
  projectsToggle.setAttribute("aria-label", "打开项目列表");
  projectsToggle.addEventListener("click", () => options.onToggleProjects?.());

  const title = document.createElement("div");
  title.className = "canvas-toolbar-title";
  const titleLabel = document.createElement("strong");
  const titleMeta = document.createElement("span");
  titleMeta.textContent = "产品视觉画布";
  title.append(titleLabel, titleMeta);

  const modeLabel = document.createElement("label");
  modeLabel.textContent = "模式";
  const mode = document.createElement("select");
  mode.setAttribute("aria-label", "画布模式");
  mode.dataset.testid = "canvas-mode";
  mode.innerHTML = '<option value="complete-set">完整套图</option><option value="advanced">高级模式</option>';
  mode.addEventListener("change", () => {
    if (mode.value === "complete-set" || mode.value === "advanced") {
      dispatch({ type: "mode/set", mode: mode.value });
    }
  });
  modeLabel.append(mode);

  const undoButton = document.createElement("button");
  undoButton.type = "button";
  undoButton.textContent = "撤销";
  undoButton.dataset.testid = "canvas-undo";
  undoButton.addEventListener("click", undo);
  const redoButton = document.createElement("button");
  redoButton.type = "button";
  redoButton.textContent = "重做";
  redoButton.dataset.testid = "canvas-redo";
  redoButton.addEventListener("click", redo);

  const viewportAction = (viewport: CanvasViewport): void => {
    dispatch({ type: "viewport/set", viewport });
  };
  const zoom = (factor: number): void => {
    const viewport = store.getState().project.layoutState.viewport;
    viewportAction({ ...viewport, zoom: Math.min(1_000, Math.max(0.01, viewport.zoom * factor)) });
  };
  const zoomOut = document.createElement("button");
  zoomOut.type = "button";
  zoomOut.textContent = "缩小";
  zoomOut.dataset.testid = "canvas-zoom-out";
  zoomOut.addEventListener("click", () => zoom(0.8));
  const zoomIn = document.createElement("button");
  zoomIn.type = "button";
  zoomIn.textContent = "放大";
  zoomIn.dataset.testid = "canvas-zoom-in";
  zoomIn.addEventListener("click", () => zoom(1.25));
  const zoomReset = document.createElement("button");
  zoomReset.type = "button";
  zoomReset.textContent = "重置视图";
  zoomReset.dataset.testid = "canvas-zoom-reset";
  zoomReset.addEventListener("click", () => viewportAction({ x: 0, y: 0, zoom: 1 }));
  const zoomReadout = document.createElement("output");
  zoomReadout.dataset.testid = "canvas-zoom-readout";
  zoomReadout.setAttribute("aria-label", "当前缩放");

  const exportButton = document.createElement("button");
  exportButton.type = "button";
  exportButton.textContent = "导出";
  exportButton.dataset.testid = "canvas-toolbar-export";
  exportButton.title = "打开导出产品图选项";
  exportButton.addEventListener("click", () => { onExport?.(); });

  const inspectorToggle = document.createElement("button");
  inspectorToggle.type = "button";
  inspectorToggle.className = "canvas-drawer-toggle canvas-inspector-toggle";
  inspectorToggle.dataset.testid = "canvas-toggle-inspector";
  inspectorToggle.textContent = "设置";
  inspectorToggle.setAttribute("aria-label", "打开画布设置");
  inspectorToggle.addEventListener("click", () => options.onToggleInspector?.());

  element.append(
    projectsToggle,
    title,
    modeLabel,
    undoButton,
    redoButton,
    zoomOut,
    zoomIn,
    zoomReset,
    zoomReadout,
    exportButton,
    inspectorToggle,
  );

  const update = (): void => {
    const current = store.getState();
    mode.value = current.project.semanticState.mode;
    titleLabel.textContent = options.getProjectName?.() ?? "未选择项目";
    mode.disabled = !editable;
    undoButton.disabled = !editable || !store.canUndo();
    redoButton.disabled = !editable || !store.canRedo();
    zoomOut.disabled = !editable;
    zoomIn.disabled = !editable;
    zoomReset.disabled = !editable;
    const canExport = options.canExport?.() ?? onExport !== undefined;
    exportButton.hidden = !canExport;
    exportButton.disabled = !editable || onExport === undefined || !canExport;
    projectsToggle.disabled = options.onToggleProjects === undefined;
    inspectorToggle.disabled = !editable || options.onToggleInspector === undefined;
    zoomReadout.value = `${Math.round(current.project.layoutState.viewport.zoom * 100)}%`;
  };
  update();
  return {
    element,
    update,
    setEditable: (nextEditable) => {
      editable = nextEditable;
      update();
    },
  };
}
