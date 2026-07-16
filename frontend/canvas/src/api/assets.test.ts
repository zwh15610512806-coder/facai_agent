import { describe, expect, test, vi } from "vitest";

import {
  createAssetsApi,
  createXhrUploadTransport,
  type UploadTransport,
  type UploadTransportRequest,
} from "./assets";

function asset(
  id: string,
  assetType: "source" | "working" | "preview" | "cutout",
  sourceAssetId: string | null,
): Record<string, unknown> {
  return {
    id,
    projectId: "project-a",
    assetType,
    originalFilename: "product.png",
    mimeType: "image/png",
    byteCount: 128,
    width: 8,
    height: 8,
    sha256: `${id}-sha256`,
    sourceAssetId,
    transparencyStatus: assetType === "cutout" ? "transparent" : "opaque",
    processorVersion: null,
    metadata: {},
  };
}

function uploadBody(): Record<string, unknown> {
  return {
    source: asset("source-a", "source", null),
    working: asset("working-a", "working", "source-a"),
    preview: asset("preview-a", "preview", "working-a"),
    operation: {
      id: "operation-a",
      projectId: "project-a",
      operationType: "cutout",
      status: "queued",
      attemptCount: 0,
      inputAssetId: "working-a",
      outputAssetId: null,
      createdAt: null,
      updatedAt: null,
      startedAt: null,
      completedAt: null,
    },
  };
}

describe("Canvas assets API", () => {
  test("default XHR abstraction sends multipart progress and aborts with the caller signal", async () => {
    class FakeXhr extends EventTarget {
      readonly upload = new EventTarget();
      status = 201;
      responseText = JSON.stringify(uploadBody());
      method = "";
      url = "";
      body: Document | XMLHttpRequestBodyInit | null = null;
      abortCalls = 0;
      autoComplete = true;

      open(method: string, url: string): void {
        this.method = method;
        this.url = url;
      }

      send(body: Document | XMLHttpRequestBodyInit | null): void {
        this.body = body;
        if (!this.autoComplete) return;
        this.upload.dispatchEvent(new ProgressEvent("progress", {
          lengthComputable: true,
          loaded: 1,
          total: 2,
        }));
        this.dispatchEvent(new Event("load"));
      }

      abort(): void {
        this.abortCalls += 1;
        this.dispatchEvent(new Event("abort"));
      }
    }

    const completed = new FakeXhr();
    const progress = vi.fn();
    const transport = createXhrUploadTransport(() => completed as unknown as XMLHttpRequest);
    await expect(transport({
      url: "/api/canvas/projects/project-a/assets",
      file: new File(["png"], "product.png", { type: "image/png" }),
      onProgress: progress,
    })).resolves.toMatchObject({ status: 201 });
    expect(completed).toMatchObject({ method: "POST", url: "/api/canvas/projects/project-a/assets" });
    expect(completed.body).toBeInstanceOf(FormData);
    expect(progress).toHaveBeenCalledWith({ loaded: 1, total: 2, percent: 50 });

    const pending = new FakeXhr();
    pending.autoComplete = false;
    const abortController = new AbortController();
    const pendingTransport = createXhrUploadTransport(() => pending as unknown as XMLHttpRequest);
    const request = pendingTransport({
      url: "/upload",
      file: new File(["png"], "product.png", { type: "image/png" }),
      signal: abortController.signal,
    });
    abortController.abort();
    await expect(request).rejects.toMatchObject({ name: "AbortError" });
    expect(pending.abortCalls).toBe(1);
  });

  test("reports XHR upload progress and returns source, working, and preview IDs", async () => {
    let request: UploadTransportRequest | null = null;
    const transport: UploadTransport = vi.fn(async (next) => {
      request = next;
      next.onProgress?.({ loaded: 64, total: 128, percent: 50 });
      return { status: 201, body: uploadBody() };
    });
    const progress = vi.fn();
    const controller = new AbortController();
    const api = createAssetsApi({ apiBase: "/api/canvas", uploadTransport: transport });

    const result = await api.uploadAsset({
      projectId: "project-a",
      file: new File(["png"], "product.png", { type: "image/png" }),
      signal: controller.signal,
      onProgress: progress,
    });

    expect(result.ok && result.value).toMatchObject({
      source: { id: "source-a" },
      working: { id: "working-a" },
      preview: { id: "preview-a" },
      operation: { id: "operation-a", safeError: null },
    });
    expect(request).toMatchObject({
      url: "/api/canvas/projects/project-a/assets",
      signal: controller.signal,
    });
    expect(progress).toHaveBeenCalledWith({ loaded: 64, total: 128, percent: 50 });
  });

  test.each([
    [413, "图片不能超过 12 MB"],
    [415, "仅支持 JPG、PNG 或 WebP 图片"],
    [422, "图片未通过服务器校验，请检查文件后重试"],
    [500, "素材服务暂时不可用，请稍后重试"],
  ])("maps server status %i to safe upload feedback", async (status, message) => {
    const api = createAssetsApi({
      apiBase: "/api/canvas",
      uploadTransport: async () => ({
        status,
        body: { detail: "unsafe internal detail", code: "internal_path_C:\\secret" },
      }),
    });

    const result = await api.uploadAsset({
      projectId: "project-a",
      file: new File(["png"], "product.png", { type: "image/png" }),
    });

    expect(result).toEqual({
      ok: false,
      kind: status === 413 || status === 415 || status === 422 ? "validation" : "server",
      status,
      message,
    });
    expect(JSON.stringify(result)).not.toContain("secret");
  });

  test("posts retry through the typed client with a client request ID", async () => {
    const fetcher = vi.fn(async () => new Response(JSON.stringify({
      id: "operation-a",
      projectId: "project-a",
      operationType: "cutout",
      status: "queued",
      attemptCount: 2,
      inputAssetId: "working-a",
      outputAssetId: null,
      createdAt: null,
      updatedAt: null,
      startedAt: null,
      completedAt: null,
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    const api = createAssetsApi({ apiBase: "/api/canvas", fetcher });

    const result = await api.retryCutout("working-a", "request-a");

    expect(result.ok && result.value.status).toBe("queued");
    expect(fetcher).toHaveBeenCalledWith(
      "/api/canvas/assets/working-a/cutout/retry",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ clientRequestId: "request-a" }),
      }),
    );
  });

  test("normalizes newest-first operation reads to chronological projection order", async () => {
    const operation = (id: string, status: string) => ({
      id,
      projectId: "project-a",
      operationType: "cutout",
      status,
      attemptCount: 1,
      inputAssetId: "working-a",
      outputAssetId: status === "succeeded" ? `cutout-${id}` : null,
      safeError: null,
    });
    const fetcher = vi.fn(async () => new Response(JSON.stringify({
      operations: [operation("new", "running"), operation("old", "succeeded")],
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    const api = createAssetsApi({ apiBase: "/api/canvas", fetcher });

    const result = await api.listOperations("project-a");

    expect(result.ok && result.value.map((item) => item.id)).toEqual(["old", "new"]);
  });
});
