import type {
  CanvasExportRequest,
  ExportFormat,
  ExportMode,
  ExportsApi,
} from "../api/exports";
import type { ResultVersion } from "../api/generations";
import type { AssetOperation, AssetOperationProgress } from "../domain/assets";
import type { CanvasProjectState, OutputBoard } from "../domain/types";
import type { FlushResult } from "../controllers/autosave-controller";
import { canvasUserMessage } from "../domain/user-message";

export interface ExportPanelOptions {
  api: ExportsApi;
  getProject(): CanvasProjectState;
  getProjectId(): string | null;
  getRevision(): number;
  getVersions(): readonly ResultVersion[];
  isEditable(): boolean;
  flushSave(): Promise<FlushResult>;
  onUnauthorized(retry: () => void): void;
  onOperation?(operation: AssetOperation): void;
}

export interface ExportPanel {
  element: HTMLElement;
  update(): void;
  applyOperation(operation: AssetOperationProgress): void;
  reset(): void;
  dispose(): void;
}

const MODE_LABELS: ReadonlyArray<[ExportMode, string]> = [
  ["single", "单张图片"],
  ["category_zip", "分类 ZIP"],
  ["detail_slices_zip", "详情切片 ZIP"],
  ["detail_long", "详情长图"],
];
const FORMAT_LABELS: ReadonlyArray<[ExportFormat, string]> = [
  ["png", "PNG"],
  ["jpeg", "JPEG"],
  ["webp", "WebP"],
];
const OUTPUT_LABELS = { main: "主图", sku: "SKU 图", detail: "详情页" } as const;

interface EligibleBoard {
  board: OutputBoard;
  version: ResultVersion;
}

function requestId(): string {
  return typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function createExportPanel(options: ExportPanelOptions): ExportPanel {
  const element = document.createElement("section");
  element.className = "canvas-export-panel";
  element.dataset.testid = "canvas-export-panel";
  let selectedBoardIds: string[] = [];
  let mode: ExportMode | null = null;
  let format: ExportFormat | null = null;
  let jpegBackground = "#ffffff";
  let busy = false;
  let activeOperation: AssetOperationProgress | null = null;
  let feedback = "";
  let epoch = 0;
  let abort: AbortController | null = null;
  let disposed = false;

  const eligibleBoards = (): EligibleBoard[] => {
    const versions = options.getVersions();
    return options.getProject().semanticState.outputBoards
      .slice()
      .sort((left, right) => left.sortOrder - right.sortOrder || left.id.localeCompare(right.id))
      .flatMap((board) => {
        if (board.selectedResultAssetId === null) return [];
        const version = versions.find(
          (candidate) => candidate.boardId === board.id
            && candidate.composedAssetId === board.selectedResultAssetId,
        );
        return version === undefined ? [] : [{ board, version }];
      });
  };

  const validationMessage = (eligible: readonly EligibleBoard[]): string | null => {
    if (selectedBoardIds.length === 0) return "请选择至少一个已保存结果";
    if (mode === null) return "请选择导出方式";
    if (format === null) return "请选择图片格式";
    if (mode === "single" && selectedBoardIds.length !== 1) return "单张图片只能选择一个画板";
    const selected = selectedBoardIds.map(
      (id) => eligible.find((candidate) => candidate.board.id === id),
    );
    if (selected.some((item) => item === undefined)) return "所选结果已变化，请重新选择";
    if (
      (mode === "detail_slices_zip" || mode === "detail_long")
      && selected.some((item) => item?.board.outputType !== "detail")
    ) return "详情导出只能选择详情页画板";
    return null;
  };

  const operationCopy = (operation: AssetOperationProgress): string => {
    switch (operation.status) {
      case "queued": return "导出任务已进入队列";
      case "running": return "正在生成导出文件…";
      case "succeeded": return "导出完成";
      case "cancel_requested": return "正在取消导出任务…";
      case "cancelled": return "导出任务已取消";
      case "failed":
      case "interrupted":
        return canvasUserMessage(operation.safeError?.message, "导出失败，请重试");
    }
  };

  const render = (): void => {
    if (disposed) return;
    const eligible = eligibleBoards();
    const eligibleIds = new Set(eligible.map((item) => item.board.id));
    selectedBoardIds = selectedBoardIds.filter((id) => eligibleIds.has(id));
    const heading = Object.assign(document.createElement("h3"), { textContent: "导出产品图" });
    const description = Object.assign(document.createElement("p"), {
      className: "canvas-export-description",
      textContent: "选择已保存的结果、导出方式和格式。所有选项均由你决定。",
    });
    const boardList = document.createElement("div");
    boardList.className = "canvas-export-boards";
    if (eligible.length === 0) {
      boardList.append(Object.assign(document.createElement("p"), {
        textContent: "请先在结果版本中保存至少一个画板结果。",
      }));
    }
    for (const { board, version } of eligible) {
      const row = document.createElement("div");
      row.className = "canvas-export-board-row";
      const label = document.createElement("label");
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = selectedBoardIds.includes(board.id);
      checkbox.disabled = busy || !options.isEditable();
      checkbox.dataset.boardId = board.id;
      checkbox.addEventListener("change", () => {
        if (checkbox.checked) {
          if (!selectedBoardIds.includes(board.id)) selectedBoardIds.push(board.id);
        } else {
          selectedBoardIds = selectedBoardIds.filter((id) => id !== board.id);
        }
        feedback = "";
        render();
      });
      const name = board.outputType === "sku" && board.skuId !== null
        ? `${OUTPUT_LABELS[board.outputType]} · ${board.skuId}`
        : OUTPUT_LABELS[board.outputType];
      const text = document.createElement("span");
      text.innerHTML = `<strong></strong><small></small>`;
      text.querySelector("strong")!.textContent = name;
      text.querySelector("small")!.textContent = `${version.modelDisplayName} · ${version.width}×${version.height}`;
      label.append(checkbox, text);
      row.append(label);
      if (checkbox.checked) {
        const index = selectedBoardIds.indexOf(board.id);
        const up = Object.assign(document.createElement("button"), {
          type: "button",
          textContent: "上移",
          disabled: busy || index === 0,
        });
        up.setAttribute("aria-label", `上移${name}`);
        up.addEventListener("click", () => {
          [selectedBoardIds[index - 1], selectedBoardIds[index]] = [
            selectedBoardIds[index]!,
            selectedBoardIds[index - 1]!,
          ];
          render();
        });
        const down = Object.assign(document.createElement("button"), {
          type: "button",
          textContent: "下移",
          disabled: busy || index === selectedBoardIds.length - 1,
        });
        down.setAttribute("aria-label", `下移${name}`);
        down.addEventListener("click", () => {
          [selectedBoardIds[index], selectedBoardIds[index + 1]] = [
            selectedBoardIds[index + 1]!,
            selectedBoardIds[index]!,
          ];
          render();
        });
        row.append(up, down);
      }
      boardList.append(row);
    }

    const modeGroup = document.createElement("fieldset");
    modeGroup.className = "canvas-export-choice-group";
    modeGroup.append(Object.assign(document.createElement("legend"), { textContent: "导出方式" }));
    for (const [value, label] of MODE_LABELS) {
      const button = Object.assign(document.createElement("button"), {
        type: "button",
        textContent: label,
        disabled: busy || !options.isEditable(),
      });
      button.dataset.exportMode = value;
      button.setAttribute("aria-pressed", String(mode === value));
      button.addEventListener("click", () => {
        mode = value;
        feedback = "";
        render();
      });
      modeGroup.append(button);
    }

    const formatGroup = document.createElement("fieldset");
    formatGroup.className = "canvas-export-choice-group";
    formatGroup.append(Object.assign(document.createElement("legend"), { textContent: "图片格式" }));
    for (const [value, label] of FORMAT_LABELS) {
      const button = Object.assign(document.createElement("button"), {
        type: "button",
        textContent: label,
        disabled: busy || !options.isEditable(),
      });
      button.dataset.exportFormat = value;
      button.setAttribute("aria-pressed", String(format === value));
      button.addEventListener("click", () => {
        format = value;
        feedback = "";
        render();
      });
      formatGroup.append(button);
    }

    const children: HTMLElement[] = [heading, description, boardList, modeGroup, formatGroup];
    if (format === "jpeg") {
      const background = document.createElement("label");
      background.className = "canvas-export-jpeg-background";
      background.textContent = "JPEG 透明区域背景";
      const input = document.createElement("input");
      input.type = "color";
      input.value = jpegBackground;
      input.disabled = busy;
      input.addEventListener("input", () => { jpegBackground = input.value; });
      background.append(input);
      children.push(background);
    }
    const validation = validationMessage(eligible);
    const submit = Object.assign(document.createElement("button"), {
      type: "button",
      className: "canvas-export-submit",
      textContent: busy ? "正在提交…" : "开始导出",
      disabled: busy || !options.isEditable() || validation !== null,
    });
    submit.dataset.testid = "canvas-export-submit";
    submit.addEventListener("click", () => { void submitExport(); });
    const status = document.createElement("p");
    status.className = "canvas-export-feedback";
    status.dataset.tone = activeOperation?.status === "succeeded"
      ? "success"
      : activeOperation !== null && ["failed", "interrupted", "cancelled"].includes(activeOperation.status)
        ? "error"
        : busy || activeOperation !== null ? "working" : "idle";
    status.textContent = feedback || validation || "";
    children.push(submit, status);
    if (
      activeOperation?.status === "succeeded"
      && activeOperation.outputAssetId !== null
      && activeOperation.outputAssetId !== undefined
    ) {
      const download = Object.assign(document.createElement("a"), {
        className: "canvas-export-download",
        textContent: "下载导出文件",
        href: options.api.downloadUrl(activeOperation.outputAssetId),
      });
      download.dataset.testid = "canvas-export-download";
      children.push(download);
    }
    element.replaceChildren(...children);
  };

  const submitExport = async (): Promise<void> => {
    const projectId = options.getProjectId();
    const eligible = eligibleBoards();
    const invalid = validationMessage(eligible);
    if (busy || projectId === null || invalid !== null || mode === null || format === null) {
      feedback = invalid ?? "当前没有可导出的项目";
      render();
      return;
    }
    const requestEpoch = ++epoch;
    busy = true;
    feedback = "正在保存项目…";
    render();
    const flushed = await options.flushSave();
    if (disposed || requestEpoch !== epoch || options.getProjectId() !== projectId) return;
    if (!flushed.ok) {
      busy = false;
      feedback = flushed.kind === "conflict" ? "项目版本有冲突，请刷新后重试" : canvasUserMessage(flushed.message, "项目保存失败，请重试");
      render();
      return;
    }
    const currentEligible = eligibleBoards();
    const currentInvalid = validationMessage(currentEligible);
    if (currentInvalid !== null) {
      busy = false;
      feedback = currentInvalid;
      render();
      return;
    }
    const selectedBoards = selectedBoardIds.map((boardId, order) => {
      const selected = currentEligible.find((candidate) => candidate.board.id === boardId)!;
      return {
        boardId,
        versionId: selected.version.versionId,
        composedAssetId: selected.version.composedAssetId,
        order,
      };
    });
    const request: CanvasExportRequest = {
      projectRevision: options.getRevision(),
      mode,
      format,
      selectedBoards,
      jpegBackground: format === "jpeg" ? jpegBackground : null,
    };
    const requestAbort = new AbortController();
    abort?.abort();
    abort = requestAbort;
    feedback = "正在提交导出任务…";
    render();
    const result = await options.api.create(
      projectId,
      request,
      `export:${requestId()}`,
      requestAbort.signal,
    );
    if (
      disposed
      || requestEpoch !== epoch
      || abort !== requestAbort
      || options.getProjectId() !== projectId
    ) return;
    abort = null;
    busy = false;
    if (!result.ok) {
      feedback = canvasUserMessage(result.message, "导出请求失败，请重试");
      render();
      if (result.kind === "unauthorized") {
        options.onUnauthorized(() => { void submitExport(); });
      }
      return;
    }
    activeOperation = result.value;
    feedback = operationCopy(result.value);
    options.onOperation?.(result.value);
    render();
  };

  const panel: ExportPanel = {
    element,
    update: render,
    applyOperation: (operation) => {
      if (
        operation.operationType !== "export"
        || operation.projectId !== options.getProjectId()
        || (activeOperation !== null && operation.id !== activeOperation.id)
      ) return;
      activeOperation = operation;
      feedback = operationCopy(operation);
      busy = false;
      render();
    },
    reset: () => {
      epoch += 1;
      abort?.abort();
      abort = null;
      selectedBoardIds = [];
      mode = null;
      format = null;
      busy = false;
      activeOperation = null;
      feedback = "";
      render();
    },
    dispose: () => {
      if (disposed) return;
      disposed = true;
      epoch += 1;
      abort?.abort();
      abort = null;
      element.replaceChildren();
    },
  };
  render();
  return panel;
}
