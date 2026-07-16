import type { AssetsApi } from "../api/assets";
import type { AssetOperation, ProjectedAsset } from "../domain/assets";

export interface AssetInspectorOptions {
  api: AssetsApi;
  onOperation(operation: AssetOperation): void;
  onFallback(asset: ProjectedAsset): void;
  createRequestId?: () => string;
}

export interface AssetInspector {
  element: HTMLElement;
  update(asset: ProjectedAsset | null): void;
  setDisabled(disabled: boolean): void;
  dispose(): void;
}

const STATUS_LABELS: Record<ProjectedAsset["cutoutStatus"], string> = {
  ready: "素材已就绪",
  queued: "自动抠图已排队",
  running: "正在自动抠图",
  failed: "自动抠图失败",
  interrupted: "自动抠图已中断",
};

function defaultRequestId(): string {
  if (typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `cutout-retry-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function createAssetInspector({
  api,
  onOperation,
  onFallback,
  createRequestId = defaultRequestId,
}: AssetInspectorOptions): AssetInspector {
  let current: ProjectedAsset | null = null;
  let disabled = false;
  let disposed = false;
  let requestEpoch = 0;

  const element = document.createElement("section");
  element.className = "canvas-asset-inspector";
  element.dataset.testid = "canvas-asset-inspector";

  const render = (): void => {
    if (disposed) {
      return;
    }
    const heading = document.createElement("h3");
    heading.textContent = "素材与抠图";
    if (current === null) {
      const empty = document.createElement("p");
      empty.textContent = "上传主商品图片后可在此对比抠图。";
      element.replaceChildren(heading, empty);
      return;
    }

    const comparison = document.createElement("div");
    comparison.className = "canvas-asset-comparison";
    const transparentReady =
      current.cutoutStatus === "ready" &&
      current.operationId === null &&
      current.cutoutAssetId === null;
    const preview = (
      title: string,
      alt: string,
      assetId: string | null,
    ): HTMLElement => {
      const figure = document.createElement("figure");
      figure.className = "canvas-checkerboard";
      const caption = document.createElement("figcaption");
      caption.textContent = title;
      figure.append(caption);
      if (assetId === null) {
        const pending = document.createElement("span");
        pending.textContent = transparentReady
          ? "原图已含透明通道，无需抠图"
          : "等待抠图结果";
        figure.append(pending);
      } else {
        const image = document.createElement("img");
        image.alt = alt;
        image.src = api.previewUrl(assetId);
        figure.append(image);
      }
      return figure;
    };
    comparison.append(
      preview("原图", "原图预览", current.workingAssetId),
      preview("抠图", "抠图预览", current.cutoutAssetId),
    );

    const status = document.createElement("p");
    status.className = `canvas-cutout-status is-${current.cutoutStatus}`;
    status.dataset.testid = "canvas-cutout-status";
    status.textContent = STATUS_LABELS[current.cutoutStatus];
    if (current.error !== null) {
      status.textContent += `：${current.error.message}`;
    }

    const actions = document.createElement("div");
    actions.className = "canvas-asset-actions";
    if (current.cutoutStatus === "failed" || current.cutoutStatus === "interrupted") {
      const retry = document.createElement("button");
      retry.type = "button";
      retry.textContent = "重新抠图";
      retry.disabled = disabled;
      retry.addEventListener("click", () => {
        if (disabled || current === null) {
          return;
        }
        const selected = current;
        const epoch = ++requestEpoch;
        retry.disabled = true;
        void api.retryCutout(selected.workingAssetId, createRequestId()).then((result) => {
          if (disposed || epoch !== requestEpoch) {
            return;
          }
          if (result.ok) {
            onOperation(result.value);
            status.textContent = "自动抠图已重新排队";
          } else {
            status.textContent = result.message;
            retry.disabled = disabled;
          }
        });
      });
      actions.append(retry);
    }
    if (!transparentReady && !current.allowOpaqueFallback) {
      const fallback = document.createElement("button");
      fallback.type = "button";
      fallback.textContent = "使用原图矩形继续";
      fallback.disabled = disabled;
      fallback.addEventListener("click", () => {
        if (!disabled && current !== null) {
          onFallback(current);
        }
      });
      actions.append(fallback);
    }
    element.replaceChildren(heading, comparison, status, actions);
  };

  render();
  return {
    element,
    update: (asset) => {
      current = asset === null ? null : structuredClone(asset);
      requestEpoch += 1;
      render();
    },
    setDisabled: (nextDisabled) => {
      disabled = nextDisabled;
      render();
    },
    dispose: () => {
      if (disposed) {
        return;
      }
      disposed = true;
      requestEpoch += 1;
      element.remove();
    },
  };
}
