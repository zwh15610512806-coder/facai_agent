import type { CanvasViewport, ProjectAction } from "../domain/types";
import type { ProjectStore } from "../state/project-store";

export interface TopToolbar {
  element: HTMLElement;
  update(): void;
  setEditable(editable: boolean): void;
}

export function createTopToolbar(
  store: ProjectStore,
  dispatch: (action: ProjectAction) => void,
  undo: () => void,
  redo: () => void,
  onExport?: () => void,
): TopToolbar {
  let editable = false;
  const element = document.createElement("header");
  element.className = "canvas-top-toolbar";
  element.dataset.testid = "canvas-top-toolbar";

  const back = document.createElement("a");
  back.href = "/app";
  back.className = "canvas-toolbar-back";
  back.textContent = "返回 AI 工作";

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

  const future = (label: string, explanation: string): HTMLButtonElement => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = label;
    button.disabled = true;
    button.title = explanation;
    return button;
  };
  const exportButton = document.createElement("button");
  exportButton.type = "button";
  exportButton.textContent = "导出";
  exportButton.dataset.testid = "canvas-toolbar-export";
  exportButton.title = "打开导出产品图选项";
  exportButton.addEventListener("click", () => { onExport?.(); });

  element.append(
    back,
    modeLabel,
    undoButton,
    redoButton,
    zoomOut,
    zoomIn,
    zoomReset,
    zoomReadout,
    future("模型设置", "模型设置将在生成能力接入后开放"),
    exportButton,
  );

  const update = (): void => {
    const current = store.getState();
    mode.value = current.project.semanticState.mode;
    mode.disabled = !editable;
    undoButton.disabled = !editable || !store.canUndo();
    redoButton.disabled = !editable || !store.canRedo();
    zoomOut.disabled = !editable;
    zoomIn.disabled = !editable;
    zoomReset.disabled = !editable;
    exportButton.disabled = !editable || onExport === undefined;
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
