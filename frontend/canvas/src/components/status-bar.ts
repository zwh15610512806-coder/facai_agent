import type { AutosaveState } from "../controllers/autosave-controller";
import type { RemoteSyncState } from "../controllers/project-controller";
import type { CutoutProjectionStatus } from "../domain/assets";
import { canvasUserMessage } from "../domain/user-message";

const STATUS_LABELS: Record<AutosaveState["status"], string> = {
  dirty: "有未保存更改",
  saving: "正在保存…",
  saved: "已保存",
  offline: "离线，等待重试",
  failed: "保存失败",
  conflict: "检测到版本冲突",
};

export interface StatusBar {
  element: HTMLElement;
  update(
    state: AutosaveState,
    remoteSync: RemoteSyncState,
    cutoutStatus?: CutoutProjectionStatus | null,
  ): void;
}

const CUTOUT_LABELS: Record<CutoutProjectionStatus, string> = {
  ready: "抠图：素材已就绪",
  queued: "抠图：已排队",
  running: "抠图：处理中",
  failed: "抠图：失败",
  interrupted: "抠图：已中断",
};

export function createStatusBar(
  onRetry: () => void,
  onRetryRemote: () => void,
): StatusBar {
  const element = document.createElement("footer");
  element.className = "canvas-status-bar";
  element.dataset.testid = "canvas-save-status";
  element.setAttribute("role", "status");
  element.setAttribute("aria-live", "polite");

  const update = (
    state: AutosaveState,
    remoteSync: RemoteSyncState,
    cutoutStatus: CutoutProjectionStatus | null = null,
  ): void => {
    const appendCutout = (): void => {
      if (cutoutStatus === null) {
        return;
      }
      const cutout = document.createElement("span");
      cutout.className = `canvas-cutout-summary is-${cutoutStatus}`;
      cutout.dataset.testid = "canvas-cutout-summary";
      cutout.textContent = CUTOUT_LABELS[cutoutStatus];
      element.append(cutout);
    };
    if (remoteSync.status !== "idle") {
      element.dataset.state = `remote-${remoteSync.status}`;
      const label = document.createElement("span");
      label.className = `canvas-save-state is-remote-${remoteSync.status}`;
      label.textContent =
        remoteSync.status === "syncing" ? "正在同步远端更改…" : "远端同步失败";
      const message = document.createElement("span");
      message.className = "canvas-save-message";
      message.textContent = remoteSync.message === null ? "" : canvasUserMessage(remoteSync.message, "远端同步失败，请重试");
      element.replaceChildren(label, message);
      if (remoteSync.status === "failed") {
        const retry = document.createElement("button");
        retry.type = "button";
        retry.textContent = "重试同步";
        retry.dataset.testid = "canvas-remote-sync-retry";
        retry.addEventListener("click", onRetryRemote);
        element.append(retry);
      }
      appendCutout();
      return;
    }
    element.dataset.state = state.status;
    const label = document.createElement("span");
    label.className = `canvas-save-state is-${state.status}`;
    label.textContent = STATUS_LABELS[state.status];
    const message = document.createElement("span");
    message.className = "canvas-save-message";
    message.textContent = state.message === null ? "" : canvasUserMessage(state.message, "保存失败，请重试");
    element.replaceChildren(label, message);
    if (state.status === "offline" || state.status === "failed") {
      const retry = document.createElement("button");
      retry.type = "button";
      retry.textContent = "重试保存";
      retry.addEventListener("click", onRetry);
      element.append(retry);
    }
    appendCutout();
  };

  return { element, update };
}
