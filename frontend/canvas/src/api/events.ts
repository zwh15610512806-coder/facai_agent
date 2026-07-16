import type {
  AssetOperation,
  AssetOperationStatus,
  SafeOperationError,
  TransparencyStatus,
} from "../domain/assets";
import { parseAssetOperation } from "./assets";
import {
  parseProjectSnapshot,
  type ProjectSnapshot,
  type ProjectStatus,
} from "./client";

export const CANVAS_MUTATION_EVENT_TYPES = [
  "project.created",
  "project.updated",
  "project.state_saved",
  "project.archived",
  "project.restored",
  "project.deleting",
  "sku.created",
  "sku.updated",
  "sku.deleted",
] as const;

export const CANVAS_ASSET_EVENT_TYPES = ["asset.uploaded", "asset.deleted"] as const;
export const CANVAS_OPERATION_EVENT_TYPES = [
  "operation.queued",
  "operation.retried",
  "operation.running",
  "operation.recovered",
  "operation.released",
  "operation.succeeded",
  "operation.failed",
  "operation.interrupted",
] as const;
export const CANVAS_GENERATION_EVENT_TYPES = [
  "generation.item.running",
  "generation.attempt.submitting",
  "generation.attempt.polling",
  "generation.item.cancel_requested",
  "generation.item.cancelled",
  "generation.item.failed",
  "generation.item.unknown",
  "generation.item.composing",
  "generation.item.succeeded",
  "generation.item.compose_failed",
  "generation.item.retrying",
  "generation.item.abandoned",
] as const;
export const CANVAS_EVENT_TYPES = [
  ...CANVAS_MUTATION_EVENT_TYPES,
  ...CANVAS_ASSET_EVENT_TYPES,
  ...CANVAS_OPERATION_EVENT_TYPES,
  ...CANVAS_GENERATION_EVENT_TYPES,
] as const;

export type CanvasMutationEventType = (typeof CANVAS_MUTATION_EVENT_TYPES)[number];
export type CanvasAssetEventType = (typeof CANVAS_ASSET_EVENT_TYPES)[number];
export type CanvasOperationEventType = (typeof CANVAS_OPERATION_EVENT_TYPES)[number];
export type CanvasGenerationEventType = (typeof CANVAS_GENERATION_EVENT_TYPES)[number];
export type CanvasEventType = (typeof CANVAS_EVENT_TYPES)[number];

export interface CanvasMutationEvent {
  type: CanvasMutationEventType;
  projectId: string;
  revision: number;
  status: ProjectStatus | "deleted";
  skuId?: string;
  summary?: {
    nodeCount: number;
    edgeCount: number;
    outputBoardCount: number;
  };
}

export interface CanvasSnapshotEvent {
  type: "snapshot";
  snapshot: ProjectSnapshot;
  operations: AssetOperation[];
  /** Recent persisted generation activity, present on a fresh/gap stream snapshot. */
  generations?: CanvasGenerationProgress[];
}

export interface CanvasAssetUploadedEvent {
  type: "asset.uploaded";
  projectId: string;
  sourceAssetId: string;
  workingAssetId: string;
  previewAssetId: string;
  transparencyStatus: Extract<TransparencyStatus, "opaque" | "transparent">;
}

export interface CanvasAssetDeletedEvent {
  type: "asset.deleted";
  projectId: string;
  assetId: string;
  status: "deleted";
}

export type CanvasAssetEvent = CanvasAssetUploadedEvent | CanvasAssetDeletedEvent;

export interface AssetOperationUpdate {
  id: string;
  projectId: string;
  operationType: AssetOperation["operationType"];
  status: AssetOperationStatus;
  attemptCount?: number;
  inputAssetId?: string;
  outputAssetId?: string;
  safeError?: SafeOperationError;
}

export interface CanvasOperationEvent {
  type: CanvasOperationEventType;
  projectId: string;
  operation: AssetOperationUpdate;
}

export interface CanvasGenerationProgress {
  id: string;
  status: string;
  totalItems: number;
  succeededItems: number;
  failedItems: number;
  cancelledItems: number;
  unknownItems: number;
  safeStorageBlockReason: string | null;
  itemId?: string;
  itemStatus?: string;
  attemptId?: string;
  safeErrorSummary?: string | null;
}

export interface CanvasGenerationEvent {
  type: CanvasGenerationEventType;
  projectId: string;
  generation: CanvasGenerationProgress;
}

export type CanvasRevisionEvent = CanvasMutationEvent | CanvasSnapshotEvent;
export type CanvasProjectEvent =
  | CanvasRevisionEvent
  | CanvasAssetEvent
  | CanvasOperationEvent
  | CanvasGenerationEvent;

export function isCanvasRevisionEvent(
  event: CanvasProjectEvent,
): event is CanvasRevisionEvent {
  return event.type === "snapshot" || "revision" in event;
}

export interface ProjectEventStream {
  close(): void;
}

interface EventSourceLike {
  addEventListener(type: string, listener: EventListener): void;
  removeEventListener(type: string, listener: EventListener): void;
  close(): void;
}

export interface OpenProjectEventsOptions {
  apiBase: string;
  projectId: string;
  onEvent(event: CanvasProjectEvent): void;
  onError?(error: unknown): void;
  eventSourceFactory?(url: string): EventSourceLike;
}

function recordValue(value: unknown, path: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`${path} must be an object`);
  }
  return value as Record<string, unknown>;
}

function exactKeys(value: Record<string, unknown>, keys: readonly string[], path: string): void {
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) {
    throw new Error(`${path} fields do not match the Canvas event contract`);
  }
}

function allowedKeys(
  value: Record<string, unknown>,
  required: readonly string[],
  allowed: readonly string[],
  path: string,
): void {
  if (
    required.some((key) => !(key in value)) ||
    Object.keys(value).some((key) => !allowed.includes(key))
  ) {
    throw new Error(`${path} fields do not match the Canvas event contract`);
  }
}

function stringValue(value: unknown, path: string): string {
  if (typeof value !== "string" || value.length === 0) {
    throw new Error(`${path} must be a non-empty string`);
  }
  return value;
}

function nullableString(value: unknown, path: string): string | null {
  return value === null ? null : stringValue(value, path);
}

function positiveRevision(value: unknown): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 1) {
    throw new Error("Canvas event revision must be a positive integer");
  }
  return value;
}

function nonNegativeInteger(value: unknown, path: string): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0) {
    throw new Error(`${path} must be a non-negative integer`);
  }
  return value;
}

function expectedStatus(type: CanvasMutationEventType): ProjectStatus | "deleted" {
  switch (type) {
    case "project.archived":
      return "archived";
    case "project.deleting":
      return "deleting";
    case "sku.deleted":
      return "deleted";
    default:
      return "active";
  }
}

function parseMutationEvent(
  type: CanvasMutationEventType,
  value: unknown,
  expectedProjectId: string,
): CanvasMutationEvent {
  const payload = recordValue(value, `event ${type}`);
  const skuEvent = type.startsWith("sku.");
  const stateSaved = type === "project.state_saved";
  exactKeys(
    payload,
    ["projectId", "revision", "status", ...(skuEvent ? ["skuId"] : []), ...(stateSaved ? ["summary"] : [])],
    `event ${type}`,
  );
  if (payload.projectId !== expectedProjectId) {
    throw new Error(`event ${type} belongs to another project`);
  }
  const status = expectedStatus(type);
  if (payload.status !== status) {
    throw new Error(`event ${type} has an invalid status`);
  }
  const event: CanvasMutationEvent = {
    type,
    projectId: expectedProjectId,
    revision: positiveRevision(payload.revision),
    status,
  };
  if (skuEvent) {
    event.skuId = stringValue(payload.skuId, `event ${type}.skuId`);
  }
  if (stateSaved) {
    const summary = recordValue(payload.summary, `event ${type}.summary`);
    exactKeys(summary, ["nodeCount", "edgeCount", "outputBoardCount"], `event ${type}.summary`);
    event.summary = {
      nodeCount: nonNegativeInteger(summary.nodeCount, `event ${type}.summary.nodeCount`),
      edgeCount: nonNegativeInteger(summary.edgeCount, `event ${type}.summary.edgeCount`),
      outputBoardCount: nonNegativeInteger(
        summary.outputBoardCount,
        `event ${type}.summary.outputBoardCount`,
      ),
    };
  }
  return event;
}

function parseAssetEvent(
  type: CanvasAssetEventType,
  value: unknown,
  expectedProjectId: string,
): CanvasAssetEvent {
  const payload = recordValue(value, `event ${type}`);
  if (type === "asset.uploaded") {
    exactKeys(
      payload,
      ["projectId", "sourceAssetId", "workingAssetId", "previewAssetId", "transparencyStatus"],
      `event ${type}`,
    );
    if (payload.projectId !== expectedProjectId) {
      throw new Error(`event ${type} belongs to another project`);
    }
    if (payload.transparencyStatus !== "opaque" && payload.transparencyStatus !== "transparent") {
      throw new Error(`event ${type}.transparencyStatus is invalid`);
    }
    return {
      type,
      projectId: expectedProjectId,
      sourceAssetId: stringValue(payload.sourceAssetId, `event ${type}.sourceAssetId`),
      workingAssetId: stringValue(payload.workingAssetId, `event ${type}.workingAssetId`),
      previewAssetId: stringValue(payload.previewAssetId, `event ${type}.previewAssetId`),
      transparencyStatus: payload.transparencyStatus,
    };
  }
  exactKeys(payload, ["projectId", "assetId", "status"], `event ${type}`);
  if (payload.projectId !== expectedProjectId || payload.status !== "deleted") {
    throw new Error(`event ${type} has an invalid owner or status`);
  }
  return {
    type,
    projectId: expectedProjectId,
    assetId: stringValue(payload.assetId, `event ${type}.assetId`),
    status: "deleted",
  };
}

const OPERATION_TYPES = ["compose", "cutout", "export"] as const;
const OPERATION_STATUSES = [
  "cancel_requested",
  "cancelled",
  "failed",
  "interrupted",
  "queued",
  "running",
  "succeeded",
] as const;

function operationStatus(type: CanvasOperationEventType): AssetOperationStatus {
  switch (type) {
    case "operation.queued":
    case "operation.retried":
    case "operation.recovered":
    case "operation.released":
      return "queued";
    case "operation.running":
      return "running";
    case "operation.succeeded":
      return "succeeded";
    case "operation.failed":
      return "failed";
    case "operation.interrupted":
      return "interrupted";
  }
}

function safeErrorValue(value: unknown, path: string): SafeOperationError {
  const record = recordValue(value, path);
  exactKeys(record, ["code", "message", "retryable"], path);
  if (typeof record.retryable !== "boolean") {
    throw new Error(`${path}.retryable must be a boolean`);
  }
  return {
    code: stringValue(record.code, `${path}.code`),
    message: stringValue(record.message, `${path}.message`),
    retryable: record.retryable,
  };
}

function parseOperationEvent(
  type: CanvasOperationEventType,
  value: unknown,
  projectId: string,
): CanvasOperationEvent {
  const payload = recordValue(value, `event ${type}`);
  const required = ["operationId", "operationType", "status"];
  const allowed = [
    ...required,
    "attemptCount",
    "inputAssetId",
    "outputAssetId",
    "safeError",
    "clientRequestFingerprint",
    "reason",
  ];
  allowedKeys(payload, required, allowed, `event ${type}`);
  const expected = operationStatus(type);
  if (payload.status !== expected) {
    throw new Error(`event ${type}.status is invalid`);
  }
  if (
    typeof payload.operationType !== "string" ||
    !(OPERATION_TYPES as readonly string[]).includes(payload.operationType)
  ) {
    throw new Error(`event ${type}.operationType is invalid`);
  }
  if (
    typeof payload.status !== "string" ||
    !(OPERATION_STATUSES as readonly string[]).includes(payload.status)
  ) {
    throw new Error(`event ${type}.status is invalid`);
  }
  const operation: AssetOperationUpdate = {
    id: stringValue(payload.operationId, `event ${type}.operationId`),
    projectId,
    operationType: payload.operationType as AssetOperation["operationType"],
    status: payload.status as AssetOperationStatus,
  };
  if (payload.attemptCount !== undefined) {
    operation.attemptCount = nonNegativeInteger(payload.attemptCount, `event ${type}.attemptCount`);
  }
  if (payload.inputAssetId !== undefined) {
    operation.inputAssetId = stringValue(payload.inputAssetId, `event ${type}.inputAssetId`);
  }
  if (payload.outputAssetId !== undefined) {
    operation.outputAssetId = stringValue(payload.outputAssetId, `event ${type}.outputAssetId`);
  }
  if (payload.safeError !== undefined) {
    operation.safeError = safeErrorValue(payload.safeError, `event ${type}.safeError`);
  }
  return { type, projectId, operation };
}

function parseGenerationEvent(
  type: CanvasGenerationEventType,
  value: unknown,
  projectId: string,
): CanvasGenerationEvent {
  const payload = recordValue(value, `event ${type}`);
  const required = [
    "generationId", "generationStatus", "totalItems", "succeededItems", "failedItems",
    "cancelledItems", "unknownItems", "safeStorageBlockReason",
  ];
  const allowed = [
    ...required, "itemId", "itemStatus", "outputType", "attemptId", "attemptNo",
    "attemptStatus", "providerResultStage", "safeErrorCode", "safeErrorSummary",
  ];
  allowedKeys(payload, required, allowed, `event ${type}`);
  const nullable = (entry: unknown, path: string): string | null =>
    entry === null ? null : stringValue(entry, path);
  const generation: CanvasGenerationProgress = {
    id: stringValue(payload.generationId, `event ${type}.generationId`),
    status: stringValue(payload.generationStatus, `event ${type}.generationStatus`),
    totalItems: nonNegativeInteger(payload.totalItems, `event ${type}.totalItems`),
    succeededItems: nonNegativeInteger(payload.succeededItems, `event ${type}.succeededItems`),
    failedItems: nonNegativeInteger(payload.failedItems, `event ${type}.failedItems`),
    cancelledItems: nonNegativeInteger(payload.cancelledItems, `event ${type}.cancelledItems`),
    unknownItems: nonNegativeInteger(payload.unknownItems, `event ${type}.unknownItems`),
    safeStorageBlockReason: nullable(payload.safeStorageBlockReason, `event ${type}.safeStorageBlockReason`),
  };
  if (payload.itemId !== undefined) generation.itemId = stringValue(payload.itemId, `event ${type}.itemId`);
  if (payload.itemStatus !== undefined) generation.itemStatus = stringValue(payload.itemStatus, `event ${type}.itemStatus`);
  if (payload.attemptId !== undefined) generation.attemptId = stringValue(payload.attemptId, `event ${type}.attemptId`);
  if (payload.safeErrorSummary !== undefined) generation.safeErrorSummary = nullable(payload.safeErrorSummary, `event ${type}.safeErrorSummary`);
  return { type, projectId, generation };
}

function nullableTimestamp(value: unknown, path: string): string | null {
  return value === null ? null : stringValue(value, path);
}

function parseSnapshotGeneration(value: unknown): CanvasGenerationProgress {
  const payload = recordValue(value, "snapshot generation");
  exactKeys(payload, [
    "id", "status", "mode", "totalItems", "succeededItems", "failedItems",
    "cancelledItems", "unknownItems", "safeStorageBlockReason", "createdAt",
    "updatedAt", "completedAt", "items",
  ], "snapshot generation");
  if (payload.mode !== "complete_set" && payload.mode !== "advanced") {
    throw new Error("snapshot generation.mode is invalid");
  }
  if (!Array.isArray(payload.items)) {
    throw new Error("snapshot generation.items must be an array");
  }
  // Validate the durable activity payload even though the workspace summary only
  // renders aggregate state. This prevents an event snapshot from smuggling a
  // malformed or cross-project item graph into the reload path.
  for (const item of payload.items) {
    const record = recordValue(item, "snapshot generation item");
    exactKeys(record, [
      "id", "ordinal", "outputType", "boardId", "nodeId", "status", "attemptCount",
      "latestBackgroundAssetId", "latestComposedAssetId", "safeErrorCode",
      "safeErrorSummary", "latestAttempt",
    ], "snapshot generation item");
    stringValue(record.id, "snapshot generation item.id");
    nonNegativeInteger(record.ordinal, "snapshot generation item.ordinal");
    stringValue(record.outputType, "snapshot generation item.outputType");
    stringValue(record.boardId, "snapshot generation item.boardId");
    stringValue(record.nodeId, "snapshot generation item.nodeId");
    stringValue(record.status, "snapshot generation item.status");
    nonNegativeInteger(record.attemptCount, "snapshot generation item.attemptCount");
    nullableString(record.latestBackgroundAssetId, "snapshot generation item.latestBackgroundAssetId");
    nullableString(record.latestComposedAssetId, "snapshot generation item.latestComposedAssetId");
    nullableString(record.safeErrorCode, "snapshot generation item.safeErrorCode");
    nullableString(record.safeErrorSummary, "snapshot generation item.safeErrorSummary");
    if (record.latestAttempt !== null) recordValue(record.latestAttempt, "snapshot generation item.latestAttempt");
  }
  nullableTimestamp(payload.createdAt, "snapshot generation.createdAt");
  nullableTimestamp(payload.updatedAt, "snapshot generation.updatedAt");
  nullableTimestamp(payload.completedAt, "snapshot generation.completedAt");
  return {
    id: stringValue(payload.id, "snapshot generation.id"),
    status: stringValue(payload.status, "snapshot generation.status"),
    totalItems: nonNegativeInteger(payload.totalItems, "snapshot generation.totalItems"),
    succeededItems: nonNegativeInteger(payload.succeededItems, "snapshot generation.succeededItems"),
    failedItems: nonNegativeInteger(payload.failedItems, "snapshot generation.failedItems"),
    cancelledItems: nonNegativeInteger(payload.cancelledItems, "snapshot generation.cancelledItems"),
    unknownItems: nonNegativeInteger(payload.unknownItems, "snapshot generation.unknownItems"),
    safeStorageBlockReason: nullableString(payload.safeStorageBlockReason, "snapshot generation.safeStorageBlockReason"),
  };
}

function parseSnapshotEvent(value: unknown, projectId: string): CanvasSnapshotEvent {
  const raw = recordValue(value, "snapshot event");
  const operationsValue = raw.operations ?? [];
  const generationsValue = raw.generations;
  allowedKeys(raw, ["project", "skus", "revision"], ["project", "skus", "revision", "operations", "generations", "highWaterEventId"], "snapshot event");
  const snapshot = parseProjectSnapshot({
    project: raw.project,
    skus: raw.skus,
    revision: raw.revision,
  });
  if (snapshot.project.id !== projectId) {
    throw new Error("snapshot event belongs to another project");
  }
  if (!Array.isArray(operationsValue)) {
    throw new Error("snapshot event.operations must be an array");
  }
  const operations = operationsValue.map((operation, index) =>
    parseAssetOperation(operation, `snapshot event.operations[${index}]`));
  if (operations.some((operation) => operation.projectId !== projectId)) {
    throw new Error("snapshot operation belongs to another project");
  }
  if (generationsValue !== undefined && !Array.isArray(generationsValue)) {
    throw new Error("snapshot event.generations must be an array");
  }
  const generations = generationsValue === undefined
    ? undefined
    : generationsValue.map(parseSnapshotGeneration);
  return {
    type: "snapshot",
    snapshot,
    operations,
    ...(generations === undefined ? {} : { generations }),
  };
}

export function openProjectEvents({
  apiBase,
  projectId,
  onEvent,
  onError,
  eventSourceFactory = (url) => new EventSource(url),
}: OpenProjectEventsOptions): ProjectEventStream {
  const base = apiBase.replace(/\/+$/, "");
  const source = eventSourceFactory(
    `${base}/projects/${encodeURIComponent(projectId)}/events`,
  );
  let active = true;
  const listeners = new Map<string, EventListener>();

  const listen = (type: string, decode: (data: unknown) => CanvasProjectEvent): void => {
    const listener: EventListener = (event) => {
      if (!active || !(event instanceof MessageEvent)) {
        return;
      }
      try {
        const parsed: unknown = JSON.parse(String(event.data));
        if (active) {
          onEvent(decode(parsed));
        }
      } catch (error) {
        if (active) {
          onError?.(error);
        }
      }
    };
    listeners.set(type, listener);
    source.addEventListener(type, listener);
  };

  for (const type of CANVAS_MUTATION_EVENT_TYPES) {
    listen(type, (data) => parseMutationEvent(type, data, projectId));
  }
  for (const type of CANVAS_ASSET_EVENT_TYPES) {
    listen(type, (data) => parseAssetEvent(type, data, projectId));
  }
  for (const type of CANVAS_OPERATION_EVENT_TYPES) {
    listen(type, (data) => parseOperationEvent(type, data, projectId));
  }
  for (const type of CANVAS_GENERATION_EVENT_TYPES) {
    listen(type, (data) => parseGenerationEvent(type, data, projectId));
  }
  listen("snapshot", (data) => parseSnapshotEvent(data, projectId));

  const errorListener: EventListener = (event) => {
    if (active) {
      onError?.(event);
    }
  };
  listeners.set("error", errorListener);
  source.addEventListener("error", errorListener);

  return {
    close: () => {
      if (!active) {
        return;
      }
      active = false;
      for (const [type, listener] of listeners) {
        source.removeEventListener(type, listener);
      }
      listeners.clear();
      source.close();
    },
  };
}
