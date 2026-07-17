import type { AssetOperation } from "../domain/assets";
import { parseAssetOperation } from "./assets";
import type { Fetcher } from "./client";

export type ExportMode = "single" | "category_zip" | "detail_slices_zip" | "detail_long";
export type ExportFormat = "png" | "jpeg" | "webp";

export interface SelectedExportBoard {
  boardId: string;
  versionId: string;
  composedAssetId: string;
  order: number;
}

export interface CanvasExportRequest {
  projectRevision: number;
  mode: ExportMode;
  format: ExportFormat;
  selectedBoards: SelectedExportBoard[];
  jpegBackground: string | null;
}

export type ExportApiResult =
  | { ok: true; value: AssetOperation }
  | {
      ok: false;
      kind: "unauthorized" | "validation" | "conflict" | "offline" | "server";
      message: string;
      currentRevision?: number;
    };

export interface ExportsApi {
  create(
    projectId: string,
    request: CanvasExportRequest,
    idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<ExportApiResult>;
  downloadUrl(assetId: string): string;
}

export interface CreateExportsApiOptions {
  apiBase: string;
  fetcher?: Fetcher;
}

function objectValue(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function safeValidationMessage(value: unknown): string {
  const detail = objectValue(value).detail;
  return typeof detail === "string" && detail.length > 0 && detail.length <= 500
    ? detail
    : "导出选项无效，请检查后重试";
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

export function createExportsApi({
  apiBase,
  fetcher = (input, init) => fetch(input, init),
}: CreateExportsApiOptions): ExportsApi {
  const base = apiBase.replace(/\/+$/, "");
  return {
    create: async (projectId, request, idempotencyKey, signal) => {
      let response: Response;
      try {
        response = await fetcher(
          `${base}/projects/${encodeURIComponent(projectId)}/exports`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "Idempotency-Key": idempotencyKey,
            },
            body: JSON.stringify(request),
            signal,
          },
        );
      } catch (error) {
        if (isAbortError(error)) throw error;
        return { ok: false, kind: "offline", message: "网络不可用，请检查连接后重试" };
      }
      let body: unknown = null;
      try {
        body = await response.json();
      } catch {
        // Invalid response bodies are normalized below.
      }
      if (response.status === 401) {
        return { ok: false, kind: "unauthorized", message: "导出请求被服务拒绝" };
      }
      if (response.status === 422) {
        return { ok: false, kind: "validation", message: safeValidationMessage(body) };
      }
      if (response.status === 409) {
        const record = objectValue(body);
        const currentRevision = record.currentRevision;
        return {
          ok: false,
          kind: "conflict",
          message: "项目或幂等请求已发生冲突，请刷新后重试",
          ...(typeof currentRevision === "number" && Number.isInteger(currentRevision)
            ? { currentRevision }
            : {}),
        };
      }
      if (!response.ok) {
        return { ok: false, kind: "server", message: "导出服务暂时不可用，请稍后重试" };
      }
      try {
        const operation = parseAssetOperation(body, "export operation");
        if (operation.projectId !== projectId || operation.operationType !== "export") {
          throw new Error("export operation ownership mismatch");
        }
        return { ok: true, value: operation };
      } catch {
        return { ok: false, kind: "server", message: "导出服务返回了无效响应" };
      }
    },
    downloadUrl: (assetId) => `${base}/assets/${encodeURIComponent(assetId)}/download`,
  };
}
