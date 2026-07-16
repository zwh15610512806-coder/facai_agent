import { describe, expect, it, vi } from "vitest";

import { createExportsApi } from "./exports";
import type { Fetcher } from "./client";

const operation = {
  id: "operation-export-1",
  projectId: "project-1",
  operationType: "export",
  status: "queued",
  attemptCount: 0,
  inputAssetId: "composed-1",
  outputAssetId: null,
  safeError: null,
};

describe("ExportsApi", () => {
  it("posts an exact idempotent export request and builds a download URL", async () => {
    const fetcher = vi.fn<Fetcher>(async () => new Response(JSON.stringify(operation), {
      status: 202,
      headers: { "Content-Type": "application/json" },
    }));
    const api = createExportsApi({ apiBase: "/api/canvas/", fetcher });
    const request = {
      projectRevision: 7,
      mode: "single" as const,
      format: "png" as const,
      selectedBoards: [{
        boardId: "board-1",
        versionId: "attempt-1",
        composedAssetId: "composed-1",
        order: 0,
      }],
      jpegBackground: null,
    };
    const result = await api.create("project-1", request, "export-request-key-0001");

    expect(result).toEqual({ ok: true, value: operation });
    expect(fetcher).toHaveBeenCalledOnce();
    const [url] = fetcher.mock.calls[0]!;
    const init = fetcher.mock.calls[0]![1]!;
    expect(url).toBe("/api/canvas/projects/project-1/exports");
    expect(init.headers).toEqual({
      "Content-Type": "application/json",
      "Idempotency-Key": "export-request-key-0001",
    });
    expect(JSON.parse(init.body as string)).toEqual(request);
    expect(api.downloadUrl("asset/导出")).toBe("/api/canvas/assets/asset%2F%E5%AF%BC%E5%87%BA/download");
  });

  it("normalizes access and validation failures without response leakage", async () => {
    const unauthorized = createExportsApi({
      apiBase: "/api/canvas",
      fetcher: async () => new Response(JSON.stringify({ detail: "secret upstream body" }), { status: 401 }),
    });
    const invalid = createExportsApi({
      apiBase: "/api/canvas",
      fetcher: async () => new Response(JSON.stringify({ detail: "请选择当前保存版本" }), { status: 422 }),
    });
    const request = {
      projectRevision: 7,
      mode: "single" as const,
      format: "png" as const,
      selectedBoards: [{ boardId: "b", versionId: "v", composedAssetId: "c", order: 0 }],
      jpegBackground: null,
    };
    expect(await unauthorized.create("p", request, "export-request-key-0002")).toEqual({
      ok: false,
      kind: "unauthorized",
      message: "需要解锁付费导出功能",
    });
    expect(await invalid.create("p", request, "export-request-key-0003")).toEqual({
      ok: false,
      kind: "validation",
      message: "请选择当前保存版本",
    });
  });
});
