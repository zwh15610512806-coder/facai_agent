import type { ApiFailure, Fetcher, ReadResult } from "./client";
import type {
  ModelCapabilities,
  ModelProfile,
  ProviderAvailability,
  ProviderProfile,
} from "../domain/providers";

export interface ProvidersApi {
  loadCatalog(signal?: AbortSignal): Promise<ReadResult<ModelProfile[]>>;
}

export interface ProviderManagementApi {
  loadProviders(signal?: AbortSignal): Promise<ReadResult<ProviderProfile[]>>;
  createProvider(request: ProviderCreateRequest): Promise<ProviderManagementResult<ProviderConnectionView>>;
  createModelProfile(providerId: string, request: ModelProfileCreateRequest): Promise<ProviderManagementResult<ModelProfileView>>;
  probeProvider(providerId: string, allowPaidProbe: boolean): Promise<ProviderManagementResult<ProviderProbeResult>>;
}

export interface ProviderCreateRequest {
  adapterType: "openai_images" | "declarative_http";
  name: string;
  baseUrl: string;
  authType: "bearer" | "api_key" | "none";
  credential?: Record<string, string>;
  credentialHint?: string | null;
  enabled?: boolean;
}

export interface ModelProfileCreateRequest {
  modelId: string;
  displayName: string;
  capabilities: Record<string, unknown>;
  config: Record<string, unknown>;
  enabled?: boolean;
}

export interface ProviderConnectionView {
  id: string;
  adapterType: string;
  name: string;
  baseUrl: string;
  authType: string;
  enabled: boolean;
  configVersion: number;
  credentialConfigured: boolean;
  credentialHint: string | null;
}

export interface ModelProfileView {
  id: string;
  providerId: string;
  modelId: string;
  displayName: string;
  enabled: boolean;
  configVersion: number;
}

export interface ProviderProbeResult {
  status: "configuration_ready" | "disabled" | "missing_credential";
  paidProbeRequired: boolean;
}

export type ProviderManagementFailure = {
  ok: false;
  kind: "unauthorized" | "unconfigured" | "offline" | "validation" | "server";
  message: string;
};

export type ProviderManagementResult<T> = { ok: true; value: T } | ProviderManagementFailure;

export interface CreateProvidersApiOptions {
  apiBase: string;
  fetcher?: Fetcher;
}

function objectValue(value: unknown, path: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`${path} must be an object`);
  }
  return value as Record<string, unknown>;
}

function exactKeys(value: Record<string, unknown>, keys: readonly string[], path: string): void {
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) {
    throw new Error(`${path} fields do not match the Canvas contract`);
  }
}

function stringValue(value: unknown, path: string): string {
  if (typeof value !== "string" || value.length === 0) throw new Error(`${path} must be a string`);
  return value;
}

function nullableString(value: unknown, path: string): string | null {
  return value === null ? null : stringValue(value, path);
}

function integer(value: unknown, path: string, minimum = 0): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < minimum) {
    throw new Error(`${path} must be an integer >= ${minimum}`);
  }
  return value;
}

function nullableInteger(value: unknown, path: string): number | null {
  return value === null ? null : integer(value, path);
}

function availability(value: unknown, path: string): ProviderAvailability {
  if (value === "available" || value === "disabled" || value === "missing_credential" || value === "invalid_configuration" || value === "unsupported_local_reference") {
    return value;
  }
  throw new Error(`${path} is unsupported`);
}

function stringArray(value: unknown, path: string): string[] {
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string" || item.length === 0)) {
    throw new Error(`${path} must be a string array`);
  }
  return [...value];
}

function jsonObject(value: unknown, path: string): Record<string, unknown> | null {
  return value === null ? null : objectValue(value, path);
}

function capabilities(value: unknown, priceMetadata: Record<string, unknown> | null): ModelCapabilities {
  const record = objectValue(value, "model.capabilities");
  exactKeys(record, [
    "text_to_image", "image_to_image", "mask_edit", "allowed_ratios", "allowed_sizes",
    "min_width", "max_width", "min_height", "max_height", "max_quantity",
    "max_reference_images", "reference_transfer", "protocol", "supports_cancel",
    "supports_idempotency", "supports_idempotency_lookup", "concurrency_limit",
  ], "model.capabilities");
  const bool = (item: unknown, path: string): boolean => {
    if (typeof item !== "boolean") throw new Error(`${path} must be boolean`);
    return item;
  };
  const transfer = record.reference_transfer;
  if (transfer !== "none" && transfer !== "bytes" && transfer !== "base64" && transfer !== "public_url") {
    throw new Error("model.capabilities.reference_transfer is unsupported");
  }
  const protocol = record.protocol;
  if (protocol !== "sync" && protocol !== "async" && protocol !== "both") {
    throw new Error("model.capabilities.protocol is unsupported");
  }
  return {
    textToImage: bool(record.text_to_image, "model.capabilities.text_to_image"),
    imageToImage: bool(record.image_to_image, "model.capabilities.image_to_image"),
    maskEdit: bool(record.mask_edit, "model.capabilities.mask_edit"),
    allowedRatios: stringArray(record.allowed_ratios, "model.capabilities.allowed_ratios"),
    allowedSizes: stringArray(record.allowed_sizes, "model.capabilities.allowed_sizes"),
    minWidth: nullableInteger(record.min_width, "model.capabilities.min_width"),
    maxWidth: nullableInteger(record.max_width, "model.capabilities.max_width"),
    minHeight: nullableInteger(record.min_height, "model.capabilities.min_height"),
    maxHeight: nullableInteger(record.max_height, "model.capabilities.max_height"),
    maxQuantity: integer(record.max_quantity, "model.capabilities.max_quantity", 1),
    maxReferenceImages: integer(record.max_reference_images, "model.capabilities.max_reference_images", 0),
    referenceTransfer: transfer,
    protocol,
    supportsCancel: bool(record.supports_cancel, "model.capabilities.supports_cancel"),
    supportsIdempotency: bool(record.supports_idempotency, "model.capabilities.supports_idempotency"),
    supportsIdempotencyLookup: bool(record.supports_idempotency_lookup, "model.capabilities.supports_idempotency_lookup"),
    concurrencyLimit: integer(record.concurrency_limit, "model.capabilities.concurrency_limit", 1),
    priceMetadata,
  };
}

function parseProvider(value: unknown): ProviderProfile {
  const record = objectValue(value, "provider");
  exactKeys(record, ["id", "name", "enabled", "availability", "availabilityReason", "configVersion"], "provider");
  if (typeof record.enabled !== "boolean") throw new Error("provider.enabled must be boolean");
  return {
    id: stringValue(record.id, "provider.id"),
    name: stringValue(record.name, "provider.name"),
    enabled: record.enabled,
    availability: availability(record.availability, "provider.availability"),
    availabilityReason: nullableString(record.availabilityReason, "provider.availabilityReason"),
    configVersion: integer(record.configVersion, "provider.configVersion", 1),
  };
}

function parseModel(value: unknown): ModelProfile {
  const record = objectValue(value, "model");
  exactKeys(record, [
    "id", "providerId", "modelId", "displayName", "enabled", "availability",
    "availabilityReason", "configVersion", "capabilities", "priceMetadata",
  ], "model");
  if (typeof record.enabled !== "boolean") throw new Error("model.enabled must be boolean");
  const priceMetadata = jsonObject(record.priceMetadata, "model.priceMetadata");
  return {
    id: stringValue(record.id, "model.id"),
    providerId: stringValue(record.providerId, "model.providerId"),
    modelId: stringValue(record.modelId, "model.modelId"),
    displayName: stringValue(record.displayName, "model.displayName"),
    enabled: record.enabled,
    availability: availability(record.availability, "model.availability"),
    availabilityReason: nullableString(record.availabilityReason, "model.availabilityReason"),
    configVersion: integer(record.configVersion, "model.configVersion", 1),
    capabilities: capabilities(record.capabilities, priceMetadata),
    priceMetadata,
  };
}

function serverFailure(status: number): ApiFailure {
  return { ok: false, kind: "server", message: `模型目录请求失败 (${status})` };
}

function managementFailure(status: number): ProviderManagementFailure {
  if (status === 401) return { ok: false, kind: "unauthorized", message: "需要解锁提供方管理功能" };
  if (status === 503) return { ok: false, kind: "unconfigured", message: "服务器尚未配置图像模型服务" };
  if (status === 422) return { ok: false, kind: "validation", message: "提供方配置未通过安全校验" };
  return { ok: false, kind: "server", message: `提供方管理请求失败 (${status})` };
}

function providerConnectionView(value: unknown): ProviderConnectionView {
  const record = objectValue(value, "provider write response");
  exactKeys(record, ["id", "adapterType", "name", "baseUrl", "authType", "enabled", "configVersion", "credentialConfigured", "credentialHint"], "provider write response");
  if (typeof record.enabled !== "boolean" || typeof record.credentialConfigured !== "boolean") throw new Error("provider write response has invalid booleans");
  return {
    id: stringValue(record.id, "provider write response.id"),
    adapterType: stringValue(record.adapterType, "provider write response.adapterType"),
    name: stringValue(record.name, "provider write response.name"),
    baseUrl: stringValue(record.baseUrl, "provider write response.baseUrl"),
    authType: stringValue(record.authType, "provider write response.authType"),
    enabled: record.enabled,
    configVersion: integer(record.configVersion, "provider write response.configVersion", 1),
    credentialConfigured: record.credentialConfigured,
    credentialHint: nullableString(record.credentialHint, "provider write response.credentialHint"),
  };
}

function modelProfileView(value: unknown): ModelProfileView {
  const record = objectValue(value, "model profile write response");
  exactKeys(record, ["id", "providerId", "modelId", "displayName", "enabled", "configVersion"], "model profile write response");
  if (typeof record.enabled !== "boolean") throw new Error("model profile write response has invalid enabled flag");
  return {
    id: stringValue(record.id, "model profile write response.id"),
    providerId: stringValue(record.providerId, "model profile write response.providerId"),
    modelId: stringValue(record.modelId, "model profile write response.modelId"),
    displayName: stringValue(record.displayName, "model profile write response.displayName"),
    enabled: record.enabled,
    configVersion: integer(record.configVersion, "model profile write response.configVersion", 1),
  };
}

function providerProbe(value: unknown): ProviderProbeResult {
  const record = objectValue(value, "provider probe response");
  exactKeys(record, ["status", "paidProbeRequired"], "provider probe response");
  if (record.status !== "configuration_ready" && record.status !== "disabled" && record.status !== "missing_credential") throw new Error("provider probe response status is invalid");
  if (typeof record.paidProbeRequired !== "boolean") throw new Error("provider probe response paidProbeRequired is invalid");
  return { status: record.status, paidProbeRequired: record.paidProbeRequired };
}

export function createProvidersApi({
  apiBase,
  fetcher = (input, init) => fetch(input, init),
}: CreateProvidersApiOptions): ProvidersApi & ProviderManagementApi {
  const base = apiBase.replace(/\/+$/, "");
  const getJson = async (url: string, signal?: AbortSignal): Promise<ReadResult<unknown>> => {
    let response: Response;
    try {
      response = await fetcher(url, { signal });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") throw error;
      return { ok: false, kind: "offline", message: "模型目录网络不可用" };
    }
    let body: unknown = null;
    try { body = await response.json(); } catch { /* parsed below */ }
    return response.ok ? { ok: true, value: body } : serverFailure(response.status);
  };
  const writeJson = async <T>(url: string, payload: object, parse: (value: unknown) => T): Promise<ProviderManagementResult<T>> => {
    let response: Response;
    try {
      response = await fetcher(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") throw error;
      return { ok: false, kind: "offline", message: "提供方管理网络不可用" };
    }
    let body: unknown = null;
    try { body = await response.json(); } catch { /* parse failure below */ }
    if (!response.ok) return managementFailure(response.status);
    try {
      return { ok: true, value: parse(body) };
    } catch {
      return { ok: false, kind: "server", message: "提供方管理响应无效" };
    }
  };
  return {
    loadProviders: async (signal) => {
      const result = await getJson(`${base}/model-providers`, signal);
      if (!result.ok) return result;
      try {
        if (!Array.isArray(result.value)) throw new Error("provider catalog must be an array");
        return { ok: true, value: result.value.map(parseProvider) };
      } catch (error) {
        return { ok: false, kind: "server", message: error instanceof Error ? `无效提供方目录：${error.message}` : "无效提供方目录" };
      }
    },
    loadCatalog: async (signal) => {
      const providers = await getJson(`${base}/model-providers`, signal);
      if (!providers.ok) return providers;
      try {
        if (!Array.isArray(providers.value)) throw new Error("provider catalog must be an array");
        const parsedProviders = providers.value.map(parseProvider);
        const collections = await Promise.all(parsedProviders.map(async (provider) => {
          const models = await getJson(`${base}/model-providers/${encodeURIComponent(provider.id)}/models`, signal);
          if (!models.ok) return models;
          if (!Array.isArray(models.value)) throw new Error("model catalog must be an array");
          const parsed = models.value.map(parseModel);
          if (parsed.some((model) => model.providerId !== provider.id)) {
            throw new Error("model catalog belongs to another provider");
          }
          return { ok: true as const, value: parsed };
        }));
        const failure = collections.find((entry) => !entry.ok);
        if (failure !== undefined && !failure.ok) return failure;
        return { ok: true, value: collections.flatMap((entry) => entry.ok ? entry.value : []) };
      } catch (error) {
        return { ok: false, kind: "server", message: error instanceof Error ? `无效模型目录：${error.message}` : "无效模型目录" };
      }
    },
    createProvider: (request) => writeJson(`${base}/model-providers`, request, providerConnectionView),
    createModelProfile: (providerId, request) => writeJson(
      `${base}/model-providers/${encodeURIComponent(providerId)}/models`, request, modelProfileView,
    ),
    probeProvider: (providerId, allowPaidProbe) => writeJson(
      `${base}/model-providers/${encodeURIComponent(providerId)}/test`, { allowPaidProbe }, providerProbe,
    ),
  };
}
