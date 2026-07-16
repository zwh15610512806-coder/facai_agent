import type { AssetsApi } from "../api/assets";
import { validateAssetFile, type UploadedAssetBundle } from "../domain/assets";
import { canvasUserMessage } from "../domain/user-message";

export interface AssetUploaderOptions {
  api: AssetsApi;
  onUploaded(upload: UploadedAssetBundle): void;
}

export interface AssetUploader {
  element: HTMLElement;
  setProject(projectId: string | null): void;
  setDisabled(disabled: boolean): void;
  openPicker(): void;
  uploadFile(file: File): void;
  dispose(): void;
}

function isAbortError(error: unknown): boolean {
  return (
    (error instanceof DOMException && error.name === "AbortError") ||
    (typeof error === "object" && error !== null && "name" in error && error.name === "AbortError")
  );
}

export function createAssetUploader({
  api,
  onUploaded,
}: AssetUploaderOptions): AssetUploader {
  let projectId: string | null = null;
  let disabled = false;
  let disposed = false;
  let uploadAbort: AbortController | null = null;

  const element = document.createElement("section");
  element.className = "canvas-asset-uploader";
  element.dataset.testid = "canvas-asset-uploader";

  const heading = document.createElement("h3");
  heading.textContent = "主商品素材";
  const dropZone = document.createElement("label");
  dropZone.className = "canvas-asset-dropzone";
  dropZone.dataset.testid = "canvas-asset-dropzone";
  dropZone.textContent = "拖放图片，或选择文件";
  const input = document.createElement("input");
  input.type = "file";
  input.accept = "image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp";
  input.setAttribute("aria-label", "上传主商品图片");
  dropZone.append(input);
  const feedback = document.createElement("p");
  feedback.className = "canvas-asset-feedback";
  feedback.setAttribute("role", "status");
  feedback.setAttribute("aria-live", "polite");
  element.append(heading, dropZone, feedback);

  const setInteractiveState = (): void => {
    input.disabled = disabled || projectId === null || disposed;
    dropZone.dataset.disabled = String(input.disabled);
  };

  const upload = async (file: File): Promise<void> => {
    if (disposed || disabled || projectId === null) {
      return;
    }
    const validation = validateAssetFile(file);
    if (!validation.ok) {
      feedback.textContent = validation.message;
      feedback.dataset.state = "validation";
      return;
    }
    uploadAbort?.abort();
    const controller = new AbortController();
    uploadAbort = controller;
    const uploadProjectId = projectId;
    feedback.dataset.state = "uploading";
    feedback.textContent = "正在上传…";
    try {
      const result = await api.uploadAsset({
        projectId: uploadProjectId,
        file,
        signal: controller.signal,
        onProgress: ({ percent, loaded, total }) => {
          if (uploadAbort !== controller || controller.signal.aborted) {
            return;
          }
          feedback.textContent = percent === null
            ? `正在上传 ${loaded} 字节…`
            : `正在上传 ${percent}%${total === null ? "" : `（${loaded}/${total}）`}`;
        },
      });
      if (
        disposed ||
        controller.signal.aborted ||
        uploadAbort !== controller ||
        projectId !== uploadProjectId
      ) {
        return;
      }
      if (!result.ok) {
        feedback.dataset.state = result.kind;
        feedback.textContent = canvasUserMessage(result.message, "图片上传失败，请重试");
        return;
      }
      feedback.dataset.state = "complete";
      feedback.textContent = "上传完成，正在检测背景并准备产品素材…";
      onUploaded(result.value);
    } catch (error) {
      if (!isAbortError(error) && uploadAbort === controller && !disposed) {
        feedback.dataset.state = "offline";
        feedback.textContent = "上传失败，请检查网络后重试";
      }
    } finally {
      if (uploadAbort === controller) {
        uploadAbort = null;
      }
    }
  };

  input.addEventListener("change", () => {
    const file = input.files?.[0];
    if (file !== undefined) {
      void upload(file);
    }
  });
  dropZone.addEventListener("dragover", (event) => {
    event.preventDefault();
  });
  dropZone.addEventListener("drop", (event) => {
    event.preventDefault();
    const file = event.dataTransfer?.files[0];
    if (file !== undefined) {
      void upload(file);
    }
  });
  setInteractiveState();

  return {
    element,
    setProject: (nextProjectId) => {
      if (projectId !== nextProjectId) {
        uploadAbort?.abort();
        uploadAbort = null;
        input.value = "";
        feedback.textContent = "";
        delete feedback.dataset.state;
      }
      projectId = nextProjectId;
      setInteractiveState();
    },
    setDisabled: (nextDisabled) => {
      disabled = nextDisabled;
      if (disabled) {
        uploadAbort?.abort();
        uploadAbort = null;
      }
      setInteractiveState();
    },
    openPicker: () => {
      if (!input.disabled) input.click();
    },
    uploadFile: (file) => {
      void upload(file);
    },
    dispose: () => {
      if (disposed) {
        return;
      }
      disposed = true;
      uploadAbort?.abort();
      uploadAbort = null;
      setInteractiveState();
      element.remove();
    },
  };
}
