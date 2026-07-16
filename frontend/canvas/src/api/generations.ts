import type { CanvasGenerationCreate } from "../domain/generation";
import type { Fetcher } from "./client";

export type GenerationCreateResult =
  | { ok: true; value: { id: string } }
  | { ok: false; kind: "unauthorized" | "offline" | "server" | "busy"; message: string };

export interface CanvasAccessStatus {
  configured: boolean;
  locked: boolean;
}

export interface ResultVersion {
  versionId: string;
  generationId: string;
  itemId: string;
  attemptId: string;
  boardId: string;
  outputType: "main" | "sku" | "detail";
  skuId: string | null;
  backgroundAssetId: string;
  backgroundPreviewAssetId: string;
  composedAssetId: string;
  composedPreviewAssetId: string;
  width: number;
  height: number;
  modelProfileId: string;
  modelDisplayName: string;
  modelConfigVersion: number;
  createdAt: string;
}

export interface ResultVersionPage {
  items: ResultVersion[];
  nextCursor: string | null;
}

export interface GenerationsApi {
  create(projectId: string, request: CanvasGenerationCreate, idempotencyKey: string): Promise<GenerationCreateResult>;
  accessStatus(): Promise<{ ok: true; value: CanvasAccessStatus } | Extract<GenerationCreateResult, { ok: false }>>;
  unlock(token: string): Promise<{ ok: true; value: CanvasAccessStatus } | Extract<GenerationCreateResult, { ok: false }>>;
  listResultVersions(projectId: string, boardId?: string, cursor?: string | null): Promise<
    { ok: true; value: ResultVersionPage } | Extract<GenerationCreateResult, { ok: false }>
  >;
}

export interface CreateGenerationsApiOptions {
  apiBase: string;
  fetcher?: Fetcher;
}

type Failure = Extract<GenerationCreateResult, { ok: false }>;

export async function loadAllResultVersions(
  api: Pick<GenerationsApi, "listResultVersions">,
  projectId: string,
): Promise<{ ok: true; value: ResultVersion[] } | Failure> {
  const versions: ResultVersion[] = [];
  const cursors = new Set<string>();
  let cursor: string | null = null;
  do {
    const result = await api.listResultVersions(projectId, undefined, cursor);
    if (!result.ok) return result;
    versions.push(...result.value.items);
    cursor = result.value.nextCursor;
    if (cursor !== null && (cursors.has(cursor) || cursors.size >= 1_000)) {
      return { ok: false, kind: "server", message: "结果版本分页响应无效" };
    }
    if (cursor !== null) cursors.add(cursor);
  } while (cursor !== null);
  return { ok: true, value: versions };
}

function recordValue(value: unknown, path: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) throw new Error(`${path} must be an object`);
  return value as Record<string, unknown>;
}

function exactKeys(record: Record<string, unknown>, keys: readonly string[], path: string): void {
  const actual = Object.keys(record).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) {
    throw new Error(`${path} fields do not match the Canvas contract`);
  }
}

function stringValue(value: unknown, path: string): string {
  if (typeof value !== "string" || value.length === 0) throw new Error(`${path} must be a string`);
  return value;
}

function integer(value: unknown, path: string, minimum = 0): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < minimum) throw new Error(`${path} must be an integer`);
  return value;
}

function nullableString(value: unknown, path: string): string | null {
  return value === null ? null : stringValue(value, path);
}

function safeMessage(body: unknown, fallback: string): string {
  if (typeof body === "object" && body !== null && "detail" in body && typeof body.detail === "string") {
    return body.detail;
  }
  return fallback;
}

function failure(status: number, body: unknown): Failure {
  if (status === 401) return { ok: false, kind: "unauthorized", message: "需要解锁付费生成功能" };
  if (status === 409 || status === 503 || status === 507) {
    return { ok: false, kind: "busy", message: safeMessage(body, "生成服务暂时不可用") };
  }
  return { ok: false, kind: "server", message: safeMessage(body, `生成请求失败 (${status})`) };
}

function parseAccessStatus(value: unknown): CanvasAccessStatus {
  const record = recordValue(value, "access status");
  exactKeys(record, ["configured", "locked"], "access status");
  if (typeof record.configured !== "boolean" || typeof record.locked !== "boolean") {
    throw new Error("access status fields must be boolean");
  }
  return { configured: record.configured, locked: record.locked };
}

function parseResultVersion(value: unknown): ResultVersion {
  const record = recordValue(value, "result version");
  exactKeys(record, [
    "versionId", "generationId", "itemId", "attemptId", "boardId", "outputType", "skuId",
    "backgroundAssetId", "backgroundPreviewAssetId", "composedAssetId", "composedPreviewAssetId",
    "width", "height", "modelProfileId", "modelDisplayName", "modelConfigVersion", "createdAt",
  ], "result version");
  if (record.outputType !== "main" && record.outputType !== "sku" && record.outputType !== "detail") {
    throw new Error("result version.outputType is unsupported");
  }
  return {
    versionId: stringValue(record.versionId, "result version.versionId"),
    generationId: stringValue(record.generationId, "result version.generationId"),
    itemId: stringValue(record.itemId, "result version.itemId"),
    attemptId: stringValue(record.attemptId, "result version.attemptId"),
    boardId: stringValue(record.boardId, "result version.boardId"),
    outputType: record.outputType,
    skuId: nullableString(record.skuId, "result version.skuId"),
    backgroundAssetId: stringValue(record.backgroundAssetId, "result version.backgroundAssetId"),
    backgroundPreviewAssetId: stringValue(record.backgroundPreviewAssetId, "result version.backgroundPreviewAssetId"),
    composedAssetId: stringValue(record.composedAssetId, "result version.composedAssetId"),
    composedPreviewAssetId: stringValue(record.composedPreviewAssetId, "result version.composedPreviewAssetId"),
    width: integer(record.width, "result version.width", 1),
    height: integer(record.height, "result version.height", 1),
    modelProfileId: stringValue(record.modelProfileId, "result version.modelProfileId"),
    modelDisplayName: stringValue(record.modelDisplayName, "result version.modelDisplayName"),
    modelConfigVersion: integer(record.modelConfigVersion, "result version.modelConfigVersion", 1),
    createdAt: stringValue(record.createdAt, "result version.createdAt"),
  };
}

export function createGenerationsApi({
  apiBase,
  fetcher = (input, init) => fetch(input, init),
}: CreateGenerationsApiOptions): GenerationsApi {
  const base = apiBase.replace(/\/+$/, "");
  const request = async (url: string, init: RequestInit): Promise<{ response: Response; body: unknown } | Failure> => {
    let response: Response;
    try {
      response = await fetcher(url, init);
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") throw error;
      return { ok: false, kind: "offline", message: "网络不可用，请检查连接后重试" };
    }
    let body: unknown = null;
    try { body = await response.json(); } catch { /* parsed below */ }
    return response.ok ? { response, body } : failure(response.status, body);
  };
  return {
    create: async (projectId, payload, idempotencyKey) => {
      const result = await request(`${base}/projects/${encodeURIComponent(projectId)}/generations`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey },
        body: JSON.stringify(payload),
      });
      if ("ok" in result) return result;
      try {
        return { ok: true, value: { id: stringValue(recordValue(result.body, "generation").id, "generation.id") } };
      } catch {
        return { ok: false, kind: "server", message: "生成服务返回了无效响应" };
      }
    },
    accessStatus: async () => {
      const result = await request(`${base}/access/status`, { method: "GET" });
      if ("ok" in result) return result;
      try { return { ok: true, value: parseAccessStatus(result.body) }; }
      catch { return { ok: false, kind: "server", message: "访问状态响应无效" }; }
    },
    unlock: async (token) => {
      const result = await request(`${base}/access/unlock`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token }),
      });
      if ("ok" in result) return result;
      try { return { ok: true, value: parseAccessStatus(result.body) }; }
      catch { return { ok: false, kind: "server", message: "解锁服务返回了无效响应" }; }
    },
    listResultVersions: async (projectId, boardId, cursor) => {
      const query = new URLSearchParams();
      if (boardId !== undefined) query.set("boardId", boardId);
      if (cursor !== undefined && cursor !== null) query.set("cursor", cursor);
      const suffix = query.size === 0 ? "" : `?${query.toString()}`;
      const result = await request(`${base}/projects/${encodeURIComponent(projectId)}/result-versions${suffix}`, { method: "GET" });
      if ("ok" in result) return result;
      try {
        const page = recordValue(result.body, "result versions");
        exactKeys(page, ["items", "nextCursor"], "result versions");
        if (!Array.isArray(page.items)) throw new Error("result versions.items must be an array");
        return { ok: true, value: { items: page.items.map(parseResultVersion), nextCursor: nullableString(page.nextCursor, "result versions.nextCursor") } };
      } catch {
        return { ok: false, kind: "server", message: "结果版本响应无效" };
      }
    },
  };
}
