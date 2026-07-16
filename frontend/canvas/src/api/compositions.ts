import { parseAssetOperation } from "./assets";
import type { AssetOperation } from "../domain/assets";
import type { Fetcher } from "./client";

export interface EnqueueComposeRequest {
  projectId: string;
  revision: number;
  boardId: string;
  backgroundAssetId: string;
  clientRequestId: string;
  signal?: AbortSignal;
}

export type ComposeApiResult =
  | { ok: true; value: AssetOperation }
  | { ok: false; kind: "conflict"; currentRevision: number }
  | {
      ok: false;
      kind: "validation" | "offline" | "server";
      status?: number;
      message: string;
    };

export interface CompositionsApi {
  enqueueCompose(request: EnqueueComposeRequest): Promise<ComposeApiResult>;
}

export interface CreateCompositionsApiOptions {
  apiBase: string;
  fetcher?: Fetcher;
}

function objectValue(value: unknown): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return {};
  }
  return value as Record<string, unknown>;
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

export function createCompositionsApi({
  apiBase,
  fetcher = (input, init) => fetch(input, init),
}: CreateCompositionsApiOptions): CompositionsApi {
  const base = apiBase.replace(/\/+$/, "");
  return {
    enqueueCompose: async ({
      projectId,
      revision,
      boardId,
      backgroundAssetId,
      clientRequestId,
      signal,
    }) => {
      let response: Response;
      try {
        response = await fetcher(
          `${base}/projects/${encodeURIComponent(projectId)}/compose`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              revision,
              boardId,
              backgroundAssetId,
              idempotencyKey: clientRequestId,
            }),
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
        // Mapped below without exposing raw server content.
      }
      if (response.status === 409) {
        const record = objectValue(body);
        return {
          ok: false,
          kind: "conflict",
          currentRevision:
            typeof record.currentRevision === "number" && Number.isInteger(record.currentRevision)
              ? record.currentRevision
              : revision,
        };
      }
      if (response.status === 422) {
        return {
          ok: false,
          kind: "validation",
          status: response.status,
          message: "当前构图或素材不满足合成条件",
        };
      }
      if (!response.ok) {
        return {
          ok: false,
          kind: "server",
          status: response.status,
          message: "合成服务暂时不可用，请稍后重试",
        };
      }
      try {
        const operation = parseAssetOperation(body);
        if (operation.projectId !== projectId || operation.operationType !== "compose") {
          throw new Error("composition response ownership mismatch");
        }
        return { ok: true, value: operation };
      } catch {
        return {
          ok: false,
          kind: "server",
          status: response.status,
          message: "合成服务返回了无效响应",
        };
      }
    },
  };
}
