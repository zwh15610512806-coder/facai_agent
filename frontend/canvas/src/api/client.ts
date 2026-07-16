import type {
  CanvasLayoutState,
  CanvasSemanticState,
  JsonValue,
} from "../domain/types";
import { parseProjectState } from "../domain/validation";

export type ProjectStatus = "active" | "archived" | "deleting";

export interface ProjectSummary {
  id: string;
  name: string;
  status: ProjectStatus;
  schemaVersion: 1;
  revision: number;
  createdAt: string | null;
  updatedAt: string | null;
  archivedAt: string | null;
}

export interface ProjectRecord extends ProjectSummary {
  semanticState: CanvasSemanticState;
  layoutState: CanvasLayoutState;
}

export interface ProjectSku {
  id: string;
  projectId: string;
  name: string;
  sortOrder: number;
  referenceAssetId: string | null;
  prompt: string;
  config: Record<string, JsonValue>;
}

export interface ProjectSnapshot {
  project: ProjectRecord;
  skus: ProjectSku[];
  revision: number;
}

export interface SaveProjectStateRequest {
  projectId: string;
  revision: number;
  semanticState: CanvasSemanticState;
  layoutState: CanvasLayoutState;
}

export type SaveResult =
  | { ok: true; snapshot: ProjectSnapshot }
  | { ok: false; kind: "conflict"; currentRevision: number }
  | { ok: false; kind: "offline" | "server"; message: string };

export type ApiFailure = Extract<SaveResult, { ok: false; kind: "offline" | "server" }>;
export type ReadResult<Value> = { ok: true; value: Value } | ApiFailure;

export interface ListProjectsOptions {
  query?: string;
  includeArchived?: boolean;
  signal?: AbortSignal;
}

export interface CanvasApi {
  listProjects(options?: ListProjectsOptions): Promise<ReadResult<ProjectSummary[]>>;
  createProject(name: string): Promise<ReadResult<ProjectSnapshot>>;
  getProject(projectId: string, signal?: AbortSignal): Promise<ReadResult<ProjectSnapshot>>;
  saveProjectState(request: SaveProjectStateRequest): Promise<SaveResult>;
  renameProject(projectId: string, revision: number, name: string): Promise<SaveResult>;
  archiveProject(projectId: string, revision: number): Promise<SaveResult>;
  restoreProject(projectId: string, revision: number): Promise<SaveResult>;
  deleteProject(projectId: string, revision: number): Promise<SaveResult>;
}

export type Fetcher = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type TransportResult =
  | { ok: true; response: Response; body: unknown }
  | ApiFailure;

export interface CanvasApiOptions {
  apiBase: string;
  fetcher?: Fetcher;
}

function recordValue(value: unknown, path: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`${path} must be an object`);
  }
  return value as Record<string, unknown>;
}

function exactKeys(
  value: Record<string, unknown>,
  keys: readonly string[],
  path: string,
): void {
  const expected = [...keys].sort();
  const actual = Object.keys(value).sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) {
    throw new Error(`${path} fields do not match the Canvas contract`);
  }
}

function stringValue(value: unknown, path: string, allowEmpty = false): string {
  if (typeof value !== "string" || (!allowEmpty && value.length === 0)) {
    throw new Error(`${path} must be ${allowEmpty ? "a string" : "a non-empty string"}`);
  }
  return value;
}

function nullableString(value: unknown, path: string): string | null {
  return value === null ? null : stringValue(value, path, true);
}

function integerValue(value: unknown, path: string, minimum: number): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < minimum) {
    throw new Error(`${path} must be an integer >= ${minimum}`);
  }
  return value;
}

function projectStatus(value: unknown, path: string): ProjectStatus {
  if (value !== "active" && value !== "archived" && value !== "deleting") {
    throw new Error(`${path} is not a supported project status`);
  }
  return value;
}

function assertJsonValue(value: unknown, path: string): void {
  if (value === null || typeof value === "string" || typeof value === "boolean") {
    return;
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      throw new Error(`${path} must contain finite JSON numbers`);
    }
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((item, index) => assertJsonValue(item, `${path}[${index}]`));
    return;
  }
  const object = recordValue(value, path);
  for (const [key, item] of Object.entries(object)) {
    assertJsonValue(item, `${path}.${key}`);
  }
}

const SUMMARY_KEYS = [
  "id",
  "name",
  "status",
  "schemaVersion",
  "revision",
  "createdAt",
  "updatedAt",
  "archivedAt",
] as const;

function summaryFromRecord(value: Record<string, unknown>, path: string): ProjectSummary {
  const schemaVersion = integerValue(value.schemaVersion, `${path}.schemaVersion`, 1);
  if (schemaVersion !== 1) {
    throw new Error(`${path}.schemaVersion must be 1`);
  }
  return {
    id: stringValue(value.id, `${path}.id`),
    name: stringValue(value.name, `${path}.name`),
    status: projectStatus(value.status, `${path}.status`),
    schemaVersion: 1,
    revision: integerValue(value.revision, `${path}.revision`, 1),
    createdAt: nullableString(value.createdAt, `${path}.createdAt`),
    updatedAt: nullableString(value.updatedAt, `${path}.updatedAt`),
    archivedAt: nullableString(value.archivedAt, `${path}.archivedAt`),
  };
}

export function parseProjectSummary(value: unknown): ProjectSummary {
  const record = recordValue(value, "project");
  exactKeys(record, SUMMARY_KEYS, "project");
  return summaryFromRecord(record, "project");
}

function parseSku(value: unknown, path: string): ProjectSku {
  const record = recordValue(value, path);
  exactKeys(
    record,
    ["id", "projectId", "name", "sortOrder", "referenceAssetId", "prompt", "config"],
    path,
  );
  const config = recordValue(record.config, `${path}.config`);
  assertJsonValue(config, `${path}.config`);
  return {
    id: stringValue(record.id, `${path}.id`),
    projectId: stringValue(record.projectId, `${path}.projectId`),
    name: stringValue(record.name, `${path}.name`),
    sortOrder: integerValue(record.sortOrder, `${path}.sortOrder`, 0),
    referenceAssetId:
      record.referenceAssetId === null
        ? null
        : stringValue(record.referenceAssetId, `${path}.referenceAssetId`),
    prompt: stringValue(record.prompt, `${path}.prompt`, true),
    config: config as Record<string, JsonValue>,
  };
}

export function parseProjectSnapshot(value: unknown): ProjectSnapshot {
  const snapshot = recordValue(value, "snapshot");
  exactKeys(snapshot, ["project", "skus", "revision"], "snapshot");
  const project = recordValue(snapshot.project, "snapshot.project");
  exactKeys(
    project,
    [...SUMMARY_KEYS, "semanticState", "layoutState"],
    "snapshot.project",
  );
  const summary = summaryFromRecord(project, "snapshot.project");
  const parsedState = parseProjectState({
    schemaVersion: summary.schemaVersion,
    semanticState: project.semanticState,
    layoutState: project.layoutState,
  });
  const revision = integerValue(snapshot.revision, "snapshot.revision", 1);
  if (revision !== summary.revision) {
    throw new Error("snapshot.revision must equal snapshot.project.revision");
  }
  if (!Array.isArray(snapshot.skus)) {
    throw new Error("snapshot.skus must be an array");
  }
  const skus = snapshot.skus.map((sku, index) => parseSku(sku, `snapshot.skus[${index}]`));
  if (skus.some((sku) => sku.projectId !== summary.id)) {
    throw new Error("snapshot SKU belongs to another project");
  }
  return {
    project: {
      ...summary,
      semanticState: parsedState.semanticState,
      layoutState: parsedState.layoutState,
    },
    skus,
    revision,
  };
}

function parseExpectedProjectSnapshot(
  value: unknown,
  expectedProjectId: string,
): ProjectSnapshot {
  const snapshot = parseProjectSnapshot(value);
  if (snapshot.project.id !== expectedProjectId) {
    throw new Error("snapshot belongs to another project");
  }
  return snapshot;
}

function invalidResponse(error: unknown): ApiFailure {
  return {
    ok: false,
    kind: "server",
    message: error instanceof Error ? `Invalid Canvas response: ${error.message}` : "Invalid Canvas response",
  };
}

function isAbortError(error: unknown): boolean {
  return (
    (error instanceof DOMException && error.name === "AbortError") ||
    (typeof error === "object" && error !== null && "name" in error && error.name === "AbortError")
  );
}

function networkFailure(error: unknown): ApiFailure {
  return {
    ok: false,
    kind: "offline",
    message: error instanceof Error ? error.message : "Network unavailable",
  };
}

async function responseBody(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

function serverMessage(response: Response, body: unknown): string {
  if (
    typeof body === "object" &&
    body !== null &&
    "detail" in body &&
    typeof body.detail === "string"
  ) {
    return body.detail;
  }
  return `Canvas request failed (${response.status})`;
}

function conflictResult(response: Response, body: unknown): SaveResult | null {
  if (
    response.status === 409 &&
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

export function createCanvasApi({
  apiBase,
  fetcher = (input, init) => fetch(input, init),
}: CanvasApiOptions): CanvasApi {
  const base = apiBase.replace(/\/+$/, "");
  const projectUrl = (projectId: string): string =>
    `${base}/projects/${encodeURIComponent(projectId)}`;

  const request = async (
    url: string,
    init: RequestInit = {},
  ): Promise<TransportResult> => {
    try {
      const response = await fetcher(url, init);
      return { ok: true, response, body: await responseBody(response) };
    } catch (error) {
      if (isAbortError(error)) {
        throw error;
      }
      return networkFailure(error);
    }
  };

  const jsonInit = (
    method: string,
    body: Record<string, unknown>,
    signal?: AbortSignal,
  ): RequestInit => ({
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });

  const read = async <Value>(
    url: string,
    init?: RequestInit,
  ): Promise<ReadResult<Value>> => {
    const result = await request(url, init);
    if (!result.ok) {
      return result;
    }
    if (!result.response.ok) {
      return {
        ok: false,
        kind: "server",
        message: serverMessage(result.response, result.body),
      };
    }
    return { ok: true, value: result.body as Value };
  };

  const writeSnapshot = async (
    url: string,
    init: RequestInit,
    expectedProjectId: string,
  ): Promise<SaveResult> => {
    const result = await request(url, init);
    if (!result.ok) {
      return result;
    }
    if (!result.response.ok) {
      return (
        conflictResult(result.response, result.body) ?? {
          ok: false,
          kind: "server",
          message: serverMessage(result.response, result.body),
        }
      );
    }
    try {
      return {
        ok: true,
        snapshot: parseExpectedProjectSnapshot(result.body, expectedProjectId),
      };
    } catch (error) {
      return invalidResponse(error);
    }
  };

  return {
    listProjects: async (options = {}) => {
      const query = new URLSearchParams();
      if (options.query !== undefined && options.query !== "") {
        query.set("q", options.query);
      }
      if (options.includeArchived !== undefined) {
        query.set("includeArchived", String(options.includeArchived));
      }
      const suffix = query.size === 0 ? "" : `?${query.toString()}`;
      const result = await read<unknown>(
        `${base}/projects${suffix}`,
        { signal: options.signal },
      );
      if (!result.ok) {
        return result;
      }
      try {
        const body = recordValue(result.value, "list response");
        exactKeys(body, ["projects"], "list response");
        if (!Array.isArray(body.projects)) {
          throw new Error("list response.projects must be an array");
        }
        return { ok: true, value: body.projects.map(parseProjectSummary) };
      } catch (error) {
        return invalidResponse(error);
      }
    },
    createProject: async (name) => {
      const result = await read<unknown>(
        `${base}/projects`,
        jsonInit("POST", { name }),
      );
      if (!result.ok) {
        return result;
      }
      try {
        return { ok: true, value: parseProjectSnapshot(result.value) };
      } catch (error) {
        return invalidResponse(error);
      }
    },
    getProject: async (projectId, signal) => {
      const result = await read<unknown>(projectUrl(projectId), { signal });
      if (!result.ok) {
        return result;
      }
      try {
        return {
          ok: true,
          value: parseExpectedProjectSnapshot(result.value, projectId),
        };
      } catch (error) {
        return invalidResponse(error);
      }
    },
    saveProjectState: ({ projectId, revision, semanticState, layoutState }) =>
      writeSnapshot(
        `${projectUrl(projectId)}/state`,
        jsonInit("PUT", { revision, semanticState, layoutState }),
        projectId,
      ),
    renameProject: (projectId, revision, name) =>
      writeSnapshot(
        projectUrl(projectId),
        jsonInit("PATCH", { revision, name }),
        projectId,
      ),
    archiveProject: (projectId, revision) =>
      writeSnapshot(
        `${projectUrl(projectId)}/archive`,
        jsonInit("POST", { revision }),
        projectId,
      ),
    restoreProject: (projectId, revision) =>
      writeSnapshot(
        `${projectUrl(projectId)}/restore`,
        jsonInit("POST", { revision }),
        projectId,
      ),
    deleteProject: (projectId, revision) =>
      writeSnapshot(
        projectUrl(projectId),
        jsonInit("DELETE", { revision }),
        projectId,
      ),
  };
}
