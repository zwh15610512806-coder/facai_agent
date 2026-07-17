import { createProvidersApi } from "./api/providers";
import { createModelManager } from "./components/model-manager";

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
  const status = document.createElement("p");
  status.className = "canvas-model-admin-status";
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  const reportUnexpectedAccessDenial = (_retry: () => void): void => {
    status.textContent = "请求被服务拒绝，请刷新页面后重试。";
  };
  const manager = createModelManager({
    catalogApi: providersApi,
    managementApi: providersApi,
    onUnauthorized: reportUnexpectedAccessDenial,
    onUnconfigured: () => {
      status.textContent = "服务器尚未配置第三方图像模型密钥，模型管理暂不可用。";
    },
    onCatalog: () => {
      status.textContent = "图像生成模型目录已更新。";
    },
  });
  root.replaceChildren(manager.element, status);
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
