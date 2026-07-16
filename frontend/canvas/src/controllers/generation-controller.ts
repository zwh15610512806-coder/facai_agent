import type { AutosaveController, FlushResult } from "./autosave-controller";
import {
  buildGenerationRequest,
  type CanvasGenerationCreate,
  type GenerationRequestResult,
} from "../domain/generation";
import type { ModelProfile } from "../domain/providers";
import type { ProjectStore } from "../state/project-store";

export interface GenerationApi {
  create(
    projectId: string,
    request: CanvasGenerationCreate,
    idempotencyKey: string,
  ): Promise<
    | { ok: true; value: { id: string } }
    | { ok: false; kind: "unauthorized" | "offline" | "server" | "busy"; message: string }
  >;
}

export type GenerationSubmitResult =
  | { ok: true; generationId: string }
  | { ok: false; kind: "validation" | "save_failed" | "request_failed"; message: string };

export interface PendingSubmission {
  projectId: string;
  fingerprint: string;
  idempotencyKey: string;
  createdAt: string;
}

export interface PendingSubmissionStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

export interface GenerationController {
  submit(): Promise<GenerationSubmitResult>;
  getPending(): PendingSubmission | null;
  retirePending(): void;
}

export interface GenerationControllerOptions {
  store: ProjectStore;
  autosave: Pick<AutosaveController, "flush">;
  api: GenerationApi;
  catalog?: () => ModelProfile[];
  build?: (project: ReturnType<ProjectStore["getState"]>["project"], catalog: ModelProfile[], revision: number) => GenerationRequestResult;
  randomId?: () => string;
  now?: () => Date;
  storage?: PendingSubmissionStorage | null;
  pendingTtlMs?: number;
}

const PENDING_STORAGE_KEY = "canvas:generation-pending:v1";

function readPending(storage: PendingSubmissionStorage | null): Map<string, PendingSubmission> {
  if (storage === null) return new Map();
  try {
    const raw = storage.getItem(PENDING_STORAGE_KEY);
    if (raw === null) return new Map();
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return new Map();
    return new Map(parsed.flatMap((value): Array<[string, PendingSubmission]> => {
      if (
        typeof value !== "object" || value === null || Array.isArray(value) ||
        typeof value.projectId !== "string" || typeof value.fingerprint !== "string" ||
        typeof value.idempotencyKey !== "string" || typeof value.createdAt !== "string"
      ) return [];
      return [[value.projectId, {
        projectId: value.projectId,
        fingerprint: value.fingerprint,
        idempotencyKey: value.idempotencyKey,
        createdAt: value.createdAt,
      }]];
    }));
  } catch {
    return new Map();
  }
}

function writePending(storage: PendingSubmissionStorage | null, pending: Map<string, PendingSubmission>): void {
  if (storage === null) return;
  try {
    if (pending.size === 0) storage.removeItem(PENDING_STORAGE_KEY);
    else storage.setItem(PENDING_STORAGE_KEY, JSON.stringify([...pending.values()]));
  } catch {
    // Private browsing storage failures must not block a server-idempotent retry.
  }
}

function canonical(value: unknown): string {
  if (value === null || typeof value === "boolean" || typeof value === "string") return JSON.stringify(value);
  if (typeof value === "number") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (typeof value !== "object") throw new Error("generation request must be JSON");
  const record = value as Record<string, unknown>;
  return `{${Object.keys(record).sort().map((key) => `${JSON.stringify(key)}:${canonical(record[key])}`).join(",")}}`;
}

function defaultRandomId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function flushFailure(result: Exclude<FlushResult, { ok: true }>): GenerationSubmitResult {
  return {
    ok: false,
    kind: "save_failed",
    message: result.kind === "conflict" ? "项目版本冲突，请刷新后重试" : result.message,
  };
}

export function createGenerationController({
  store,
  autosave,
  api,
  catalog = () => [],
  build = buildGenerationRequest,
  randomId = defaultRandomId,
  now = () => new Date(),
  storage = typeof sessionStorage === "undefined" ? null : sessionStorage,
  pendingTtlMs = 30 * 60 * 1_000,
}: GenerationControllerOptions): GenerationController {
  const pending = readPending(storage);
  let inFlight: Promise<GenerationSubmitResult> | null = null;

  const submit = (): Promise<GenerationSubmitResult> => {
    if (inFlight !== null) return inFlight;
    const submission: Promise<GenerationSubmitResult> = (async (): Promise<GenerationSubmitResult> => {
      const flushed = await autosave.flush();
      if (!flushed.ok) return flushFailure(flushed);
      const current = store.getState();
      const projection = build(current.project, catalog(), current.runtime.revision);
      if (!projection.ok) {
        return { ok: false, kind: "validation", message: projection.reasons[0]?.message ?? "生成配置无效" };
      }
      const fingerprint = canonical(projection.request);
      const existing = pending.get(current.runtime.projectId);
      const createdAt = existing === undefined ? Number.NaN : Date.parse(existing.createdAt);
      const reusable = existing !== undefined && existing.fingerprint === fingerprint &&
        Number.isFinite(createdAt) && now().getTime() - createdAt <= pendingTtlMs;
      if (!reusable) {
        pending.set(current.runtime.projectId, {
          projectId: current.runtime.projectId,
          fingerprint,
          idempotencyKey: `canvas:${randomId()}`,
          createdAt: now().toISOString(),
        });
        writePending(storage, pending);
      }
      const activePending = pending.get(current.runtime.projectId);
      if (activePending === undefined) throw new Error("generation pending submission is unavailable");
      const response = await api.create(
        current.runtime.projectId,
        projection.request,
        activePending.idempotencyKey,
      );
      if (!response.ok) {
        return { ok: false, kind: "request_failed", message: response.message };
      }
      pending.delete(current.runtime.projectId);
      writePending(storage, pending);
      return { ok: true, generationId: response.value.id };
    })().finally(() => {
      inFlight = null;
    });
    inFlight = submission;
    return submission;
  };

  return {
    submit,
    getPending: () => {
      const current = store.getState().runtime.projectId;
      const value = pending.get(current);
      return value === undefined ? null : { ...value };
    },
    retirePending: () => {
      pending.delete(store.getState().runtime.projectId);
      writePending(storage, pending);
    },
  };
}
