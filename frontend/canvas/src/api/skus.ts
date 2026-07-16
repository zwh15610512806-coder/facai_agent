import {
  parseProjectSnapshot,
  type Fetcher,
  type ProjectSnapshot,
  type SaveResult,
} from "./client";
import type { JsonValue } from "../domain/types";

export interface SkuCreateInput {
  name: string;
  referenceAssetId?: string | null;
  prompt?: string;
  config?: Record<string, JsonValue>;
}

export interface SkuUpdatePatch {
  name?: string;
  referenceAssetId?: string | null;
  prompt?: string;
  config?: Record<string, JsonValue>;
  sortOrder?: number;
}

export interface SkusApi {
  createSku(projectId: string, revision: number, input: SkuCreateInput): Promise<SaveResult>;
  updateSku(
    projectId: string,
    skuId: string,
    revision: number,
    patch: SkuUpdatePatch,
  ): Promise<SaveResult>;
  deleteSku(projectId: string, skuId: string, revision: number): Promise<SaveResult>;
}

export interface CreateSkusApiOptions {
  apiBase: string;
  fetcher?: Fetcher;
}

function isAbortError(error: unknown): boolean {
  return (
    (error instanceof DOMException && error.name === "AbortError") ||
    (typeof error === "object" && error !== null && "name" in error && error.name === "AbortError")
  );
}

function conflict(body: unknown): SaveResult | null {
  if (
    typeof body === "object" &&
    body !== null &&
    "code" in body &&
    body.code === "canvas_revision_conflict" &&
    "currentRevision" in body &&
    typeof body.currentRevision === "number" &&
    Number.isInteger(body.currentRevision)
  ) {
    return { ok: false, kind: "conflict", currentRevision: body.currentRevision };
  }
  return null;
}

export function createSkusApi({
  apiBase,
  fetcher = (input, init) => fetch(input, init),
}: CreateSkusApiOptions): SkusApi {
  const base = apiBase.replace(/\/+$/, "");
  const skuUrl = (projectId: string, skuId?: string): string => {
    const root = `${base}/projects/${encodeURIComponent(projectId)}/skus`;
    return skuId === undefined ? root : `${root}/${encodeURIComponent(skuId)}`;
  };
  const write = async (
    url: string,
    method: string,
    body: Record<string, unknown>,
    expectedProjectId: string,
  ): Promise<SaveResult> => {
    let response: Response;
    try {
      response = await fetcher(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
    } catch (error) {
      if (isAbortError(error)) {
        throw error;
      }
      return { ok: false, kind: "offline", message: "网络不可用，请检查连接后重试" };
    }
    let payload: unknown = null;
    try {
      payload = await response.json();
    } catch {
      // Parsed below as a safe server error.
    }
    if (!response.ok) {
      return conflict(payload) ?? {
        ok: false,
        kind: "server",
        message: `SKU 请求失败 (${response.status})`,
      };
    }
    let snapshot: ProjectSnapshot;
    try {
      snapshot = parseProjectSnapshot(payload);
      if (snapshot.project.id !== expectedProjectId) {
        throw new Error("SKU response belongs to another project");
      }
    } catch {
      return { ok: false, kind: "server", message: "SKU 服务返回了无效响应" };
    }
    return { ok: true, snapshot };
  };

  return {
    createSku: (projectId, revision, input) =>
      write(
        skuUrl(projectId),
        "POST",
        {
          revision,
          name: input.name,
          referenceAssetId: input.referenceAssetId ?? null,
          prompt: input.prompt ?? "",
          config: input.config ?? {},
        },
        projectId,
      ),
    updateSku: (projectId, skuId, revision, patch) =>
      write(skuUrl(projectId, skuId), "PATCH", { revision, ...patch }, projectId),
    deleteSku: (projectId, skuId, revision) =>
      write(skuUrl(projectId, skuId), "DELETE", { revision }, projectId),
  };
}
