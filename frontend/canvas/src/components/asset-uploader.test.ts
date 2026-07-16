import { expect, test, vi } from "vitest";

import type { AssetsApi } from "../api/assets";
import type { AssetRecord, UploadedAssetBundle } from "../domain/assets";
import { createAssetUploader } from "./asset-uploader";

function record(
  id: string,
  assetType: AssetRecord["assetType"],
  sourceAssetId: string | null,
): AssetRecord {
  return {
    id,
    projectId: "project-a",
    assetType,
    originalFilename: "product.png",
    mimeType: "image/png",
    byteCount: 3,
    width: 1,
    height: 1,
    sha256: `${id}-sha`,
    sourceAssetId,
    transparencyStatus: assetType === "working" ? "transparent" : "unknown",
    processorVersion: null,
    metadata: {},
  };
}

function bundle(): UploadedAssetBundle {
  return {
    source: record("source-a", "source", null),
    working: record("working-a", "working", "source-a"),
    preview: record("preview-a", "preview", "working-a"),
    operation: null,
  };
}

function setFiles(input: HTMLInputElement, files: File[]): void {
  Object.defineProperty(input, "files", { configurable: true, value: files });
}

async function settle(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
}

test("file picker and drag/drop validate locally, report progress, and keep server authoritative", async () => {
  const uploadAsset = vi.fn<AssetsApi["uploadAsset"]>(async (options) => {
    options.onProgress?.({ loaded: 1, total: 2, percent: 50 });
    if (options.file.name === "server-rejected.png") {
      return {
        ok: false,
        kind: "validation",
        status: 422,
        message: "图片未通过服务器校验，请检查文件后重试",
      };
    }
    return { ok: true, value: bundle() };
  });
  const api = { uploadAsset } as unknown as AssetsApi;
  const onUploaded = vi.fn();
  const uploader = createAssetUploader({ api, onUploaded });
  document.body.append(uploader.element);
  uploader.setProject("project-a");
  const input = uploader.element.querySelector<HTMLInputElement>('input[type="file"]');
  if (input === null) throw new Error("missing file input");

  expect(input.accept).toContain("image/jpeg");
  expect(input.accept).toContain("image/png");
  expect(input.accept).toContain("image/webp");

  setFiles(input, [new File(["gif"], "bad.gif", { type: "image/gif" })]);
  input.dispatchEvent(new Event("change", { bubbles: true }));
  expect(uploader.element.textContent).toContain("请选择 JPG、PNG 或 WebP 图片");
  expect(uploadAsset).not.toHaveBeenCalled();

  setFiles(input, [new File(["png"], "product.png", { type: "image/png" })]);
  input.dispatchEvent(new Event("change", { bubbles: true }));
  await settle();
  expect(uploadAsset).toHaveBeenCalledTimes(1);
  expect(uploader.element.textContent).toContain("上传完成");
  expect(uploader.element.textContent).toContain("正在检测背景并准备产品素材");
  expect(uploader.element.textContent).not.toContain("source-a / working-a / preview-a");
  expect(onUploaded).toHaveBeenCalledWith(bundle());

  const dropZone = uploader.element.querySelector<HTMLElement>('[data-testid="canvas-asset-dropzone"]');
  if (dropZone === null) throw new Error("missing drop zone");
  const drop = new Event("drop", { bubbles: true, cancelable: true });
  Object.defineProperty(drop, "dataTransfer", {
    value: { files: [new File(["png"], "server-rejected.png", { type: "image/png" })] },
  });
  dropZone.dispatchEvent(drop);
  await settle();
  expect(uploadAsset).toHaveBeenCalledTimes(2);
  expect(uploader.element.textContent).toContain("图片未通过服务器校验");
  uploader.dispose();
});

test("switching projects aborts the in-flight upload", async () => {
  let signal: AbortSignal | undefined;
  const uploadAsset = vi.fn<AssetsApi["uploadAsset"]>(async (options) => {
    signal = options.signal;
    await new Promise<void>((_resolve, reject) => {
      options.signal?.addEventListener(
        "abort",
        () => reject(new DOMException("aborted", "AbortError")),
        { once: true },
      );
    });
    return { ok: true, value: bundle() };
  });
  const uploader = createAssetUploader({
    api: { uploadAsset } as unknown as AssetsApi,
    onUploaded: vi.fn(),
  });
  document.body.append(uploader.element);
  uploader.setProject("project-a");
  const input = uploader.element.querySelector<HTMLInputElement>('input[type="file"]');
  if (input === null) throw new Error("missing file input");
  setFiles(input, [new File(["png"], "product.png", { type: "image/png" })]);
  input.dispatchEvent(new Event("change", { bubbles: true }));
  await Promise.resolve();

  uploader.setProject("project-b");

  expect(signal?.aborted).toBe(true);
  await settle();
  expect(uploader.element.textContent).not.toContain("上传失败");
  uploader.dispose();
});
