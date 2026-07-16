import type {
  SaveProjectStateRequest,
  SaveResult,
} from "../api/client";
import { serializeProjectState } from "../domain/validation";
import type { ProjectStore } from "../state/project-store";

export type AutosaveStatus =
  | "dirty"
  | "saving"
  | "saved"
  | "offline"
  | "failed"
  | "conflict";

export interface AutosaveState {
  status: AutosaveStatus;
  dirty: boolean;
  message: string | null;
  currentRevision: number | null;
}

export type FlushResult =
  | { ok: true }
  | { ok: false; kind: "conflict"; currentRevision: number }
  | { ok: false; kind: "offline" | "server"; message: string };

export interface AutosaveController {
  getState(): AutosaveState;
  subscribe(listener: (state: AutosaveState) => void): () => void;
  flush(): Promise<FlushResult>;
  retry(): Promise<FlushResult>;
  whenIdle(): Promise<void>;
  hasUnconfirmedChanges(): boolean;
  markConflict(currentRevision: number): void;
  dispose(): void;
}

export interface AutosaveControllerOptions {
  store: ProjectStore;
  save(request: SaveProjectStateRequest): Promise<SaveResult>;
  debounceMs?: number;
  documentTarget?: Document;
  windowTarget?: Window;
}

function projectFingerprint(store: ProjectStore): string {
  return JSON.stringify(serializeProjectState(store.getState().project));
}

export function createAutosaveController({
  store,
  save,
  debounceMs = 1_000,
  documentTarget = typeof document === "undefined" ? undefined : document,
  windowTarget = typeof window === "undefined" ? undefined : window,
}: AutosaveControllerOptions): AutosaveController {
  let generation = 0;
  let acknowledgedGeneration = 0;
  let fingerprint = projectFingerprint(store);
  let state: AutosaveState = {
    status: "saved",
    dirty: false,
    message: null,
    currentRevision: null,
  };
  let debounceTimer: ReturnType<typeof setTimeout> | null = null;
  let inFlight: Promise<FlushResult> | null = null;
  let disposed = false;
  let conflictBlocked = false;
  const listeners = new Set<(next: AutosaveState) => void>();

  const hasUnconfirmedChanges = (): boolean =>
    conflictBlocked || acknowledgedGeneration < generation;

  const publish = (next: AutosaveState): void => {
    state = next;
    for (const listener of [...listeners]) {
      listener({ ...state });
    }
  };

  const clearDebounce = (): void => {
    if (debounceTimer !== null) {
      clearTimeout(debounceTimer);
      debounceTimer = null;
    }
  };

  const schedule = (): void => {
    clearDebounce();
    debounceTimer = setTimeout(() => {
      debounceTimer = null;
      void flush();
    }, debounceMs);
  };

  const onStoreChange = (): void => {
    const nextFingerprint = projectFingerprint(store);
    if (nextFingerprint === fingerprint) {
      return;
    }
    fingerprint = nextFingerprint;
    generation += 1;
    if (conflictBlocked) {
      publish({ ...state, dirty: true });
      return;
    }
    publish({
      status: "dirty",
      dirty: true,
      message: null,
      currentRevision: null,
    });
    schedule();
  };

  const unsubscribeStore = store.subscribe(onStoreChange);

  const performFlush = async (): Promise<FlushResult> => {
    clearDebounce();
    while (!disposed && acknowledgedGeneration < generation) {
      const savingGeneration = generation;
      const current = store.getState();
      publish({
        status: "saving",
        dirty: true,
        message: null,
        currentRevision: null,
      });

      let result: SaveResult;
      try {
        result = await save({
          projectId: current.runtime.projectId,
          revision: current.runtime.revision,
          semanticState: current.project.semanticState,
          layoutState: current.project.layoutState,
        });
      } catch (error) {
        result = {
          ok: false,
          kind: "server",
          message: error instanceof Error ? error.message : "Save failed",
        };
      }

      if (disposed) {
        return { ok: false, kind: "server", message: "Autosave disposed" };
      }
      if (!result.ok) {
        if (result.kind === "conflict") {
          conflictBlocked = true;
          publish({
            status: "conflict",
            dirty: true,
            message: "Project changed elsewhere",
            currentRevision: result.currentRevision,
          });
          return result;
        }
        publish({
          status: result.kind === "offline" ? "offline" : "failed",
          dirty: true,
          message: result.message,
          currentRevision: null,
        });
        return result;
      }

      store.acknowledgeRevision(result.snapshot.revision);
      acknowledgedGeneration = savingGeneration;
      if (conflictBlocked) {
        return {
          ok: false,
          kind: "conflict",
          currentRevision:
            state.currentRevision ?? store.getState().runtime.revision,
        };
      }
    }

    if (!disposed) {
      publish({
        status: "saved",
        dirty: false,
        message: null,
        currentRevision: null,
      });
    }
    return { ok: true };
  };

  const flush = (): Promise<FlushResult> => {
    clearDebounce();
    if (conflictBlocked) {
      return Promise.resolve({
        ok: false,
        kind: "conflict",
        currentRevision: state.currentRevision ?? store.getState().runtime.revision,
      });
    }
    if (inFlight !== null) {
      return inFlight;
    }
    if (acknowledgedGeneration >= generation) {
      return Promise.resolve({ ok: true });
    }
    inFlight = performFlush().finally(() => {
      inFlight = null;
    });
    return inFlight;
  };

  const onVisibilityChange = (): void => {
    if (documentTarget?.visibilityState === "hidden") {
      void flush();
    }
  };
  const onPageHide = (): void => {
    void flush();
  };
  const onBeforeUnload = (event: BeforeUnloadEvent): void => {
    if (!hasUnconfirmedChanges()) {
      return;
    }
    event.preventDefault();
    event.returnValue = "";
  };

  documentTarget?.addEventListener("visibilitychange", onVisibilityChange);
  windowTarget?.addEventListener("pagehide", onPageHide);
  windowTarget?.addEventListener("beforeunload", onBeforeUnload);

  return {
    getState: () => ({ ...state }),
    subscribe: (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    flush,
    retry: flush,
    whenIdle: async () => {
      await inFlight;
    },
    hasUnconfirmedChanges,
    markConflict: (currentRevision) => {
      if (!Number.isInteger(currentRevision) || currentRevision < 1) {
        throw new Error("conflict revision must be a positive integer");
      }
      clearDebounce();
      conflictBlocked = true;
      publish({
        status: "conflict",
        dirty: true,
        message: "Project changed elsewhere",
        currentRevision,
      });
    },
    dispose: () => {
      if (disposed) {
        return;
      }
      disposed = true;
      clearDebounce();
      unsubscribeStore();
      documentTarget?.removeEventListener("visibilitychange", onVisibilityChange);
      windowTarget?.removeEventListener("pagehide", onPageHide);
      windowTarget?.removeEventListener("beforeunload", onBeforeUnload);
      listeners.clear();
    },
  };
}
