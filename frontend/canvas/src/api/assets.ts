import {
  type AssetOperation,
  type AssetOperationStatus,
  type AssetRecord,
  type AssetType,
  type SafeOperationError,
  type TransparencyStatus,
  type UploadedAssetBundle,
} from "../domain/assets";
import type { Fetcher } from "./client";

export interface UploadProgress {
  loaded: number;
  total: number | null;
  percent: number | null;
}

export interface UploadTransportRequest {
  url: string;
  file: File;
  signal?: AbortSignal;
  onProgress?(progress: UploadProgress): void;
}

export interface UploadTransportResponse {
  status: number;
  body: unknown;
}

export type UploadTransport = (
  request: UploadTransportRequest,
) => Promise<UploadTransportResponse>;

export type AssetApiResult<Value> =
  | { ok: true; value: Value }
  | {
      ok: false;
      kind: "validation" | "offline" | "server";
      status?: number;
      message: string;
    };

export interface UploadAssetOptions {
  projectId: string;
  file: File;
  signal?: AbortSignal;
  onProgress?(progress: UploadProgress): void;
}

export interface AssetsApi {
  previewUrl(assetId: string): string;
  uploadAsset(options: UploadAssetOptions): Promise<AssetApiResult<UploadedAssetBundle>>;
  listAssets(projectId: string, signal?: AbortSignal): Promise<AssetApiResult<AssetRecord[]>>;
  listOperations(
    projectId: string,
    signal?: AbortSignal,
  ): Promise<AssetApiResult<AssetOperation[]>>;
  retryCutout(
    workingAssetId: string,
    clientRequestId: string,
    signal?: AbortSignal,
  ): Promise<AssetApiResult<AssetOperation>>;
  retryOperation(
    operationId: string,
    signal?: AbortSignal,
  ): Promise<AssetApiResult<AssetOperation>>;
  deleteAsset(assetId: string, signal?: AbortSignal): Promise<AssetApiResult<string>>;
}

export interface CreateAssetsApiOptions {
  apiBase: string;
  fetcher?: Fetcher;
  uploadTransport?: UploadTransport;
}

type XhrFactory = () => XMLHttpRequest;

function parseJson(raw: string): unknown {
  if (raw === "") {
    return null;
  }
  try {
    return JSON.parse(raw) as unknown;
  } catch {
    return null;
  }
}

function abortError(): DOMException {
  return new DOMException("Canvas upload aborted", "AbortError");
}

export function createXhrUploadTransport(
  xhrFactory: XhrFactory = () => new XMLHttpRequest(),
): UploadTransport {
  return ({ url, file, signal, onProgress }) =>
    new Promise<UploadTransportResponse>((resolve, reject) => {
      if (signal?.aborted) {
        reject(abortError());
        return;
      }
      const xhr = xhrFactory();
      const cleanup = (): void => {
        signal?.removeEventListener("abort", onSignalAbort);
      };
      const onSignalAbort = (): void => {
        xhr.abort();
      };
      xhr.upload.addEventListener("progress", (event) => {
        const total = event.lengthComputable ? event.total : null;
        onProgress?.({
          loaded: event.loaded,
          total,
          percent: total !== null && total > 0 ? Math.round((event.loaded / total) * 100) : null,
        });
      });
      xhr.addEventListener("load", () => {
        cleanup();
        resolve({ status: xhr.status, body: parseJson(xhr.responseText) });
      });
      xhr.addEventListener("error", () => {
        cleanup();
        reject(new Error("Canvas upload network unavailable"));
      });
      xhr.addEventListener("abort", () => {
        cleanup();
        reject(abortError());
      });
      signal?.addEventListener("abort", onSignalAbort, { once: true });
      const body = new FormData();
      body.append("file", file, file.name);
      xhr.open("POST", url);
      xhr.send(body);
    });
}

function objectValue(value: unknown, path: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`${path} must be an object`);
  }
  return value as Record<string, unknown>;
}

function stringValue(value: unknown, path: string, allowEmpty = false): string {
  if (typeof value !== "string" || (!allowEmpty && value.length === 0)) {
    throw new Error(`${path} must be a string`);
  }
  return value;
}

function nullableString(value: unknown, path: string): string | null {
  return value === null ? null : stringValue(value, path, true);
}

function nonNegativeInteger(value: unknown, path: string): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0) {
    throw new Error(`${path} must be a non-negative integer`);
  }
  return value;
}

function enumValue<const Values extends readonly string[]>(
  value: unknown,
  values: Values,
  path: string,
): Values[number] {
  if (typeof value !== "string" || !(values as readonly string[]).includes(value)) {
    throw new Error(`${path} is unsupported`);
  }
  return value as Values[number];
}

const ASSET_TYPES = [
  "source",
  "working",
  "preview",
  "cutout",
  "generated_background",
  "composed",
  "export",
] as const satisfies readonly AssetType[];
const TRANSPARENCY_STATUSES = ["unknown", "opaque", "transparent"] as const satisfies readonly TransparencyStatus[];
const OPERATION_STATUSES = [
  "cancel_requested",
  "cancelled",
  "failed",
  "interrupted",
  "queued",
  "running",
  "succeeded",
] as const satisfies readonly AssetOperationStatus[];
const OPERATION_TYPES = ["compose", "cutout", "export"] as const;

export function parseAssetRecord(value: unknown, path = "asset"): AssetRecord {
  const record = objectValue(value, path);
  return {
    id: stringValue(record.id, `${path}.id`),
    projectId: stringValue(record.projectId, `${path}.projectId`),
    assetType: enumValue(record.assetType, ASSET_TYPES, `${path}.assetType`),
    originalFilename: stringValue(record.originalFilename, `${path}.originalFilename`, true),
    mimeType: stringValue(record.mimeType, `${path}.mimeType`),
    byteCount: nonNegativeInteger(record.byteCount, `${path}.byteCount`),
    width: nonNegativeInteger(record.width, `${path}.width`),
    height: nonNegativeInteger(record.height, `${path}.height`),
    sha256: stringValue(record.sha256, `${path}.sha256`),
    sourceAssetId: nullableString(record.sourceAssetId, `${path}.sourceAssetId`),
    transparencyStatus: enumValue(
      record.transparencyStatus,
      TRANSPARENCY_STATUSES,
      `${path}.transparencyStatus`,
    ),
    processorVersion: nullableString(record.processorVersion, `${path}.processorVersion`),
    metadata: objectValue(record.metadata, `${path}.metadata`),
  };
}

function safeErrorValue(value: unknown, path: string): SafeOperationError | null {
  if (value === null || value === undefined) {
    return null;
  }
  const error = objectValue(value, path);
  if (typeof error.retryable !== "boolean") {
    throw new Error(`${path}.retryable must be a boolean`);
  }
  return {
    code: stringValue(error.code, `${path}.code`),
    message: stringValue(error.message, `${path}.message`),
    retryable: error.retryable,
  };
}

export function parseAssetOperation(
  value: unknown,
  path = "operation",
): AssetOperation {
  const record = objectValue(value, path);
  const operationType = record.operationType ?? record.type;
  const safeError = record.safeError ?? record.error ?? null;
  return {
    id: stringValue(record.id, `${path}.id`),
    projectId: stringValue(record.projectId, `${path}.projectId`),
    operationType: enumValue(operationType, OPERATION_TYPES, `${path}.operationType`),
    status: enumValue(record.status, OPERATION_STATUSES, `${path}.status`),
    attemptCount: nonNegativeInteger(record.attemptCount, `${path}.attemptCount`),
    inputAssetId: stringValue(record.inputAssetId, `${path}.inputAssetId`),
    outputAssetId: nullableString(record.outputAssetId, `${path}.outputAssetId`),
    safeError: safeErrorValue(safeError, `${path}.safeError`),
  };
}

function parseUpload(value: unknown, expectedProjectId: string): UploadedAssetBundle {
  const body = objectValue(value, "upload response");
  const source = parseAssetRecord(body.source, "upload response.source");
  const working = parseAssetRecord(body.working, "upload response.working");
  const preview = parseAssetRecord(body.preview, "upload response.preview");
  const operation = body.operation === null
    ? null
    : parseAssetOperation(body.operation, "upload response.operation");
  if (
    source.projectId !== expectedProjectId ||
    working.projectId !== expectedProjectId ||
    preview.projectId !== expectedProjectId ||
    (operation !== null && operation.projectId !== expectedProjectId)
  ) {
    throw new Error("Canvas upload response belongs to another project");
  }
  return { source, working, preview, operation };
}

function isAbortError(error: unknown): boolean {
  return (
    (error instanceof DOMException && error.name === "AbortError") ||
    (typeof error === "object" && error !== null && "name" in error && error.name === "AbortError")
  );
}

function uploadFailure(status: number): Exclude<AssetApiResult<never>, { ok: true }> {
  if (status === 413) {
    return { ok: false, kind: "validation", status, message: "图片不能超过 12 MB" };
  }
  if (status === 415) {
    return { ok: false, kind: "validation", status, message: "仅支持 JPG、PNG 或 WebP 图片" };
  }
  if (status === 422) {
    return {
      ok: false,
      kind: "validation",
      status,
      message: "图片未通过服务器校验，请检查文件后重试",
    };
  }
  return { ok: false, kind: "server", status, message: "素材服务暂时不可用，请稍后重试" };
}

function serverFailure(status: number): Exclude<AssetApiResult<never>, { ok: true }> {
  return { ok: false, kind: "server", status, message: "素材服务暂时不可用，请稍后重试" };
}

export function createAssetsApi({
  apiBase,
  fetcher = (input, init) => fetch(input, init),
  uploadTransport = createXhrUploadTransport(),
}: CreateAssetsApiOptions): AssetsApi {
  const base = apiBase.replace(/\/+$/, "");
  const requestJson = async <Value>(
    url: string,
    init: RequestInit,
    parse: (body: unknown) => Value,
  ): Promise<AssetApiResult<Value>> => {
    let response: Response;
    try {
      response = await fetcher(url, init);
    } catch (error) {
      if (isAbortError(error)) {
        throw error;
      }
      return { ok: false, kind: "offline", message: "网络不可用，请检查连接后重试" };
    }
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      // Invalid server bodies are handled below without exposing response text.
    }
    if (!response.ok) {
      return serverFailure(response.status);
    }
    try {
      return { ok: true, value: parse(body) };
    } catch {
      return { ok: false, kind: "server", status: response.status, message: "素材服务返回了无效响应" };
    }
  };
  const jsonInit = (method: string, body: Record<string, unknown>, signal?: AbortSignal): RequestInit => ({
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });

  return {
    previewUrl: (assetId) =>
      `${base}/assets/${encodeURIComponent(assetId)}/content?variant=preview`,
    uploadAsset: async ({ projectId, file, signal, onProgress }) => {
      let response: UploadTransportResponse;
      try {
        response = await uploadTransport({
          url: `${base}/projects/${encodeURIComponent(projectId)}/assets`,
          file,
          signal,
          onProgress,
        });
      } catch (error) {
        if (isAbortError(error)) {
          throw error;
        }
        return { ok: false, kind: "offline", message: "网络不可用，请检查连接后重试" };
      }
      if (response.status < 200 || response.status >= 300) {
        return uploadFailure(response.status);
      }
      try {
        return { ok: true, value: parseUpload(response.body, projectId) };
      } catch {
        return { ok: false, kind: "server", status: response.status, message: "素材服务返回了无效响应" };
      }
    },
    listAssets: (projectId, signal) =>
      requestJson(
        `${base}/projects/${encodeURIComponent(projectId)}/assets`,
        { signal },
        (body) => {
          const record = objectValue(body, "asset list response");
          if (!Array.isArray(record.assets)) {
            throw new Error("asset list response.assets must be an array");
          }
          const assets = record.assets.map((item, index) => parseAssetRecord(item, `assets[${index}]`));
          if (assets.some((asset) => asset.projectId !== projectId)) {
            throw new Error("asset list response belongs to another project");
          }
          return assets;
        },
      ),
    listOperations: (projectId, signal) =>
      requestJson(
        `${base}/projects/${encodeURIComponent(projectId)}/operations`,
        { signal },
        (body) => {
          const record = objectValue(body, "operation list response");
          if (!Array.isArray(record.operations)) {
            throw new Error("operation list response.operations must be an array");
          }
          const operations = record.operations.map((item, index) =>
            parseAssetOperation(item, `operations[${index}]`)).reverse();
          if (operations.some((operation) => operation.projectId !== projectId)) {
            throw new Error("operation list response belongs to another project");
          }
          return operations;
        },
      ),
    retryCutout: (workingAssetId, clientRequestId, signal) =>
      requestJson(
        `${base}/assets/${encodeURIComponent(workingAssetId)}/cutout/retry`,
        jsonInit("POST", { clientRequestId }, signal),
        parseAssetOperation,
      ),
    retryOperation: (operationId, signal) =>
      requestJson(
        `${base}/operations/${encodeURIComponent(operationId)}/retry`,
        jsonInit("POST", {}, signal),
        parseAssetOperation,
      ),
    deleteAsset: (assetId, signal) =>
      requestJson(
        `${base}/assets/${encodeURIComponent(assetId)}`,
        { method: "DELETE", signal },
        (body) => {
          const record = objectValue(body, "delete asset response");
          if (record.status !== "deleted") {
            throw new Error("delete asset response status is invalid");
          }
          return stringValue(record.assetId, "delete asset response.assetId");
        },
      ),
  };
}
