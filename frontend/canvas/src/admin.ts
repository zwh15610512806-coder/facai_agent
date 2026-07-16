import { createGenerationsApi } from "./api/generations";
import { createProvidersApi } from "./api/providers";
import { createAccessDialog } from "./components/access-dialog";
import { createModelManager } from "./components/model-manager";
import { canvasUserMessage } from "./domain/user-message";

export interface CanvasModelAdminOptions {
  root: HTMLElement;
  apiBase: string;
}

export interface MountedCanvasModelAdmin {
  dispose(): void;
}

export function mountCanvasModelManager({
  root,
  apiBase,
}: CanvasModelAdminOptions): MountedCanvasModelAdmin {
  const providersApi = createProvidersApi({ apiBase });
  const generationsApi = createGenerationsApi({ apiBase });
  const accessDialog = createAccessDialog();
  const status = document.createElement("p");
  status.className = "canvas-model-admin-status";
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  const requestUnlock = (retry: () => void): void => {
    accessDialog.open(async (token) => {
      const result = await generationsApi.unlock(token);
      if (!result.ok) return canvasUserMessage(result.message, "解锁失败，请检查访问令牌");
      retry();
      return null;
    });
  };
  const manager = createModelManager({
    catalogApi: providersApi,
    managementApi: providersApi,
    onUnauthorized: requestUnlock,
    onUnconfigured: () => {
      status.textContent = "服务器尚未配置产品画布访问令牌，第三方图像模型管理暂不可用。";
    },
    onCatalog: () => {
      status.textContent = "图像生成模型目录已更新。";
    },
  });
  root.replaceChildren(manager.element, status, accessDialog.element);
  return {
    dispose: () => {
      manager.clearSensitive();
      root.replaceChildren();
    },
  };
}

const root = document.querySelector<HTMLElement>("#canvas-model-admin");
if (root !== null) {
  const apiBase = root.dataset.apiBase ?? "/api/canvas";
  const mounted = mountCanvasModelManager({ root, apiBase });
  window.addEventListener("pagehide", () => mounted.dispose(), { once: true });
}
