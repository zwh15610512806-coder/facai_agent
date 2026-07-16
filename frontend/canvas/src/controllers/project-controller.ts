import type {
  CanvasApi,
  ProjectSnapshot,
  ProjectSummary,
  SaveProjectStateRequest,
  SaveResult,
} from "../api/client";
import {
  isCanvasRevisionEvent,
  type CanvasProjectEvent,
  type ProjectEventStream,
} from "../api/events";
import type { CanvasAdapter } from "../canvas/canvas-adapter";
import type { CanvasProjectState } from "../domain/types";
import { createEmptyProjectState } from "../domain/types";
import type { ProjectStore } from "../state/project-store";
import type {
  AutosaveController,
  AutosaveState,
  FlushResult,
} from "./autosave-controller";

export type ProjectSwitchResult =
  | { ok: true }
  | { ok: false; kind: "stale" }
  | { ok: false; kind: "load"; message: string }
  | { ok: false; kind: "decision"; failure: Exclude<FlushResult, { ok: true }> };

export interface PendingProjectSwitch {
  projectId: string;
  failure: Exclude<FlushResult, { ok: true }>;
}

export interface RemoteSyncState {
  status: "idle" | "syncing" | "failed";
  pendingRevision: number | null;
  message: string | null;
}

export interface ProjectControllerState {
  pendingSwitch: PendingProjectSwitch | null;
  projects: ProjectSummary[];
  query: string;
  includeArchived: boolean;
  activeProjectId: string | null;
  deleteCandidateId: string | null;
  loading: boolean;
  error: string | null;
  save: AutosaveState;
  remoteSync: RemoteSyncState;
}

export interface ProjectController {
  initialize(snapshot: ProjectSnapshot): void;
  getActiveSnapshot(): ProjectSnapshot | null;
  adoptMutationSnapshot(snapshot: ProjectSnapshot): boolean;
  getState(): ProjectControllerState;
  subscribe(listener: (state: ProjectControllerState) => void): () => void;
  switchProject(projectId: string): Promise<ProjectSwitchResult>;
  retrySwitch(): Promise<ProjectSwitchResult>;
  stayOnProject(): void;
  discardAndSwitch(): Promise<ProjectSwitchResult>;
  renameActiveProject(name: string): Promise<SaveResult>;
  searchProjects(query: string, includeArchived: boolean): Promise<void>;
  createProject(name: string): Promise<SaveResult>;
  archiveProject(projectId: string): Promise<SaveResult>;
  restoreProject(projectId: string): Promise<SaveResult>;
  requestDeleteProject(projectId: string): void;
  cancelDeleteProject(): void;
  confirmDeleteProject(): Promise<SaveResult>;
  flushSave(): Promise<FlushResult>;
  retrySave(): Promise<FlushResult>;
  retryRemoteSync(): Promise<void>;
  dispose(): void;
}

export interface CreateProjectControllerOptions {
  api: CanvasApi;
  store: ProjectStore;
  adapter: CanvasAdapter;
  createAutosave(
    store: ProjectStore,
    save: (request: SaveProjectStateRequest) => Promise<SaveResult>,
  ): AutosaveController;
  openEvents(
    projectId: string,
    onEvent: (event: CanvasProjectEvent) => void,
  ): ProjectEventStream;
}

function canvasState(snapshot: ProjectSnapshot): CanvasProjectState {
  return {
    schemaVersion: snapshot.project.schemaVersion,
    semanticState: snapshot.project.semanticState,
    layoutState: snapshot.project.layoutState,
  };
}

function projectSummary(snapshot: ProjectSnapshot): ProjectSummary {
  const {
    semanticState: _semanticState,
    layoutState: _layoutState,
    ...summary
  } = snapshot.project;
  return summary;
}

export function createProjectController({
  api,
  store,
  adapter,
  createAutosave,
  openEvents,
}: CreateProjectControllerOptions): ProjectController {
  let autosave: AutosaveController | null = null;
  let unsubscribeAutosave: (() => void) | null = null;
  let events: ProjectEventStream | null = null;
  let switchEpoch = 0;
  let activeSessionEpoch = 0;
  let loadAbort: AbortController | null = null;
  let refreshAbort: AbortController | null = null;
  let refreshInFlight: Promise<void> | null = null;
  let disposed = false;
  let activeSnapshot: ProjectSnapshot | null = null;
  let revisionLane: Promise<void> = Promise.resolve();
  let revisionWritesPending = 0;
  let bufferedRemote: {
    projectId: string;
    revision: number;
    session: number;
  } | null = null;
  let searchEpoch = 0;
  let searchAbort: AbortController | null = null;
  let state: ProjectControllerState = {
    pendingSwitch: null,
    projects: [],
    query: "",
    includeArchived: false,
    activeProjectId: null,
    deleteCandidateId: null,
    loading: false,
    error: null,
    save: {
      status: "saved",
      dirty: false,
      message: null,
      currentRevision: null,
    },
    remoteSync: {
      status: "idle",
      pendingRevision: null,
      message: null,
    },
  };
  const listeners = new Set<(next: ProjectControllerState) => void>();

  const publish = (next: ProjectControllerState): void => {
    state = next;
    for (const listener of [...listeners]) {
      listener({ ...state });
    }
  };

  const update = (patch: Partial<ProjectControllerState>): void => {
    publish({ ...state, ...patch });
  };

  const upsertProject = (summary: ProjectSummary): void => {
    const projects = state.projects.filter((project) => project.id !== summary.id);
    const normalizedQuery = state.query.trim().toLocaleLowerCase();
    const statusMatches =
      summary.status === "active" ||
      (state.includeArchived && summary.status === "archived");
    const queryMatches =
      normalizedQuery === "" ||
      summary.name.toLocaleLowerCase().includes(normalizedQuery);
    if (statusMatches && queryMatches) {
      projects.unshift(summary);
    }
    update({ projects });
  };

  const enqueueRevisioned = (
    projectId: string,
    operation: (revision: number) => Promise<SaveResult>,
  ): Promise<SaveResult> => {
    revisionWritesPending += 1;
    const run = revisionLane.then(async () => {
      const active = activeSnapshot?.project.id === projectId;
      const operationSession = active ? activeSessionEpoch : null;
      const listed = state.projects.find((project) => project.id === projectId);
      if (disposed || (!active && listed === undefined)) {
        return {
          ok: false,
          kind: "server",
          message: "Project changed before write",
        } as const;
      }
      const revision = active ? store.getState().runtime.revision : listed?.revision;
      if (revision === undefined) {
        return {
          ok: false,
          kind: "server",
          message: "Project revision is unavailable",
        } as const;
      }
      const result = await operation(revision);
      if (result.ok && !disposed) {
        if (
          operationSession !== null &&
          operationSession === activeSessionEpoch &&
          activeSnapshot?.project.id === projectId
        ) {
          store.acknowledgeRevision(result.snapshot.revision);
          activeSnapshot = result.snapshot;
        }
        upsertProject(projectSummary(result.snapshot));
      }
      return result;
    });
    revisionLane = run.then(
      () => undefined,
      () => undefined,
    );
    return run.finally(() => {
      revisionWritesPending -= 1;
      if (revisionWritesPending === 0 && bufferedRemote !== null) {
        handleRemoteRevision();
      }
    });
  };

  let activate: (snapshot: ProjectSnapshot) => void;

  const clearRemoteSync = (): void => {
    bufferedRemote = null;
    update({
      remoteSync: {
        status: "idle",
        pendingRevision: null,
        message: null,
      },
    });
  };

  const failRemoteSync = (message: string): void => {
    const pending = bufferedRemote;
    if (
      pending === null ||
      pending.session !== activeSessionEpoch ||
      pending.projectId !== activeSnapshot?.project.id
    ) {
      return;
    }
    update({
      remoteSync: {
        status: "failed",
        pendingRevision: pending.revision,
        message,
      },
    });
  };

  const refreshCleanProject = (): Promise<void> => {
    if (refreshInFlight !== null) {
      return refreshInFlight;
    }
    const snapshot = activeSnapshot;
    const pending = bufferedRemote;
    if (
      snapshot === null ||
      pending === null ||
      disposed ||
      pending.session !== activeSessionEpoch ||
      pending.projectId !== snapshot.project.id
    ) {
      return Promise.resolve();
    }
    const projectId = snapshot.project.id;
    const session = activeSessionEpoch;
    const controller = new AbortController();
    refreshAbort = controller;
    update({
      remoteSync: {
        status: "syncing",
        pendingRevision: pending.revision,
        message: null,
      },
    });

    const run = (async (): Promise<void> => {
      try {
        const loaded = await api.getProject(projectId, controller.signal);
        if (
          disposed ||
          session !== activeSessionEpoch ||
          activeSnapshot?.project.id !== projectId
        ) {
          return;
        }
        if (!loaded.ok) {
          failRemoteSync(loaded.message);
          return;
        }
        const latest = bufferedRemote;
        if (
          latest === null ||
          latest.session !== session ||
          latest.projectId !== projectId
        ) {
          return;
        }
        if (loaded.value.revision < latest.revision) {
          failRemoteSync("Remote project revision is not available yet");
          return;
        }
        if (loaded.value.revision <= store.getState().runtime.revision) {
          clearRemoteSync();
          return;
        }
        if (revisionWritesPending > 0) {
          return;
        }
        if (autosave?.hasUnconfirmedChanges()) {
          autosave.markConflict(latest.revision);
          clearRemoteSync();
          return;
        }
        autosave?.dispose();
        events?.close();
        adapter.cancelPendingLoads();
        activate(loaded.value);
      } catch (error) {
        const abortError =
          typeof error === "object" &&
          error !== null &&
          "name" in error &&
          error.name === "AbortError";
        if (!abortError && !disposed && session === activeSessionEpoch) {
          failRemoteSync(
            error instanceof Error ? error.message : "Remote project refresh failed",
          );
        }
      }
    })();
    refreshInFlight = run;
    void run.finally(() => {
      if (refreshInFlight === run) {
        refreshInFlight = null;
        refreshAbort = null;
      }
    });
    return run;
  };

  const handleRemoteRevision = (): void => {
    const pending = bufferedRemote;
    if (
      pending === null ||
      pending.session !== activeSessionEpoch ||
      pending.projectId !== activeSnapshot?.project.id
    ) {
      return;
    }
    if (pending.revision <= store.getState().runtime.revision) {
      clearRemoteSync();
      return;
    }
    if (revisionWritesPending > 0) {
      return;
    }
    if (autosave?.hasUnconfirmedChanges()) {
      autosave.markConflict(pending.revision);
      clearRemoteSync();
      return;
    }
    void refreshCleanProject();
  };

  const handleProjectEvent = (event: CanvasProjectEvent, session: number): void => {
    if (
      disposed ||
      session !== activeSessionEpoch ||
      activeSnapshot === null ||
      !isCanvasRevisionEvent(event)
    ) {
      return;
    }
    const revision = event.type === "snapshot" ? event.snapshot.revision : event.revision;
    const projectId =
      event.type === "snapshot" ? event.snapshot.project.id : event.projectId;
    if (
      projectId !== activeSnapshot.project.id ||
      revision <= store.getState().runtime.revision
    ) {
      return;
    }
    if (
      bufferedRemote === null ||
      bufferedRemote.session !== session ||
      revision > bufferedRemote.revision
    ) {
      bufferedRemote = { projectId, revision, session };
      update({
        remoteSync: {
          status: "syncing",
          pendingRevision: revision,
          message: null,
        },
      });
    }
    handleRemoteRevision();
  };

  activate = (snapshot: ProjectSnapshot): void => {
    refreshAbort?.abort();
    refreshAbort = null;
    refreshInFlight = null;
    activeSessionEpoch += 1;
    bufferedRemote = null;
    activeSnapshot = snapshot;
    const project = canvasState(snapshot);
    store.replaceProject(project, {
      projectId: snapshot.project.id,
      revision: snapshot.revision,
    });
    adapter.project(null, project);
    unsubscribeAutosave?.();
    autosave = createAutosave(store, (request) =>
      enqueueRevisioned(request.projectId, (revision) =>
        api.saveProjectState({ ...request, revision }),
      ),
    );
    update({
      save: autosave.getState(),
      remoteSync: {
        status: "idle",
        pendingRevision: null,
        message: null,
      },
    });
    unsubscribeAutosave = autosave.subscribe((save) => {
      update({ save });
    });
    const activeSession = activeSessionEpoch;
    events = openEvents(snapshot.project.id, (event) => {
      handleProjectEvent(event, activeSession);
    });
    upsertProject(projectSummary(snapshot));
    update({ activeProjectId: snapshot.project.id, error: null });
  };

  const loadTarget = async (
    projectId: string,
    epoch: number,
  ): Promise<ProjectSwitchResult> => {
    const controller = new AbortController();
    loadAbort = controller;
    let loaded: Awaited<ReturnType<CanvasApi["getProject"]>>;
    try {
      loaded = await api.getProject(projectId, controller.signal);
    } catch (error) {
      if (
        disposed ||
        epoch !== switchEpoch ||
        (error instanceof DOMException && error.name === "AbortError")
      ) {
        return { ok: false, kind: "stale" };
      }
      return {
        ok: false,
        kind: "load",
        message: error instanceof Error ? error.message : "Project load failed",
      };
    }
    if (disposed || epoch !== switchEpoch) {
      return { ok: false, kind: "stale" };
    }
    if (!loaded.ok) {
      return { ok: false, kind: "load", message: loaded.message };
    }

    const oldAutosave = autosave;
    const oldEvents = events;
    oldAutosave?.dispose();
    oldEvents?.close();
    adapter.cancelPendingLoads();
    activate(loaded.value);
    update({ pendingSwitch: null });
    return { ok: true };
  };

  const switchProject = async (projectId: string): Promise<ProjectSwitchResult> => {
    if (disposed) {
      return { ok: false, kind: "stale" };
    }
    switchEpoch += 1;
    const epoch = switchEpoch;
    loadAbort?.abort();
    update({ pendingSwitch: null });

    const flushed = await (autosave?.flush() ?? Promise.resolve({ ok: true as const }));
    if (disposed || epoch !== switchEpoch) {
      return { ok: false, kind: "stale" };
    }
    if (!flushed.ok) {
      update({ pendingSwitch: { projectId, failure: flushed } });
      return { ok: false, kind: "decision", failure: flushed };
    }
    return loadTarget(projectId, epoch);
  };

  const mutateProject = async (
    projectId: string,
    operation: (revision: number) => Promise<SaveResult>,
  ): Promise<SaveResult> => {
    if (activeSnapshot?.project.id === projectId) {
      const flushed = await (autosave?.flush() ?? Promise.resolve({ ok: true as const }));
      if (!flushed.ok) {
        return flushed;
      }
    }
    return enqueueRevisioned(projectId, operation);
  };

  const searchProjects = async (
    query: string,
    includeArchived: boolean,
  ): Promise<void> => {
    searchEpoch += 1;
    const epoch = searchEpoch;
    searchAbort?.abort();
    const controller = new AbortController();
    searchAbort = controller;
    update({ query, includeArchived, loading: true, error: null });
    try {
      const result = await api.listProjects({
        query,
        includeArchived,
        signal: controller.signal,
      });
      if (disposed || epoch !== searchEpoch) {
        return;
      }
      if (!result.ok) {
        update({ loading: false, error: result.message });
        return;
      }
      update({ projects: result.value, loading: false, error: null });
    } catch (error) {
      if (
        disposed ||
        epoch !== searchEpoch ||
        (error instanceof DOMException && error.name === "AbortError")
      ) {
        return;
      }
      update({
        loading: false,
        error: error instanceof Error ? error.message : "Project search failed",
      });
    }
  };

  const createProject = async (name: string): Promise<SaveResult> => {
    const intentEpoch = switchEpoch;
    const intentSession = activeSessionEpoch;
    const flushed = await (autosave?.flush() ?? Promise.resolve({ ok: true as const }));
    if (!flushed.ok) {
      return flushed;
    }
    if (
      disposed ||
      intentEpoch !== switchEpoch ||
      intentSession !== activeSessionEpoch
    ) {
      return {
        ok: false,
        kind: "server",
        message: "Project selection changed before creation",
      };
    }
    const result = await api.createProject(name);
    if (!result.ok) {
      return result;
    }
    if (disposed) {
      return { ok: true, snapshot: result.value };
    }
    if (
      intentEpoch !== switchEpoch ||
      intentSession !== activeSessionEpoch
    ) {
      upsertProject(projectSummary(result.value));
      return { ok: true, snapshot: result.value };
    }
    switchEpoch += 1;
    loadAbort?.abort();
    refreshAbort?.abort();
    autosave?.dispose();
    events?.close();
    adapter.cancelPendingLoads();
    activate(result.value);
    return { ok: true, snapshot: result.value };
  };

  const deactivate = (): void => {
    switchEpoch += 1;
    activeSessionEpoch += 1;
    bufferedRemote = null;
    loadAbort?.abort();
    refreshAbort?.abort();
    refreshAbort = null;
    refreshInFlight = null;
    autosave?.dispose();
    autosave = null;
    unsubscribeAutosave?.();
    unsubscribeAutosave = null;
    events?.close();
    events = null;
    adapter.cancelPendingLoads();
    activeSnapshot = null;
    const empty = createEmptyProjectState();
    store.replaceProject(empty, { projectId: "local-project", revision: 0 });
    adapter.project(null, empty);
    update({
      activeProjectId: null,
      pendingSwitch: null,
      save: {
        status: "saved",
        dirty: false,
        message: null,
        currentRevision: null,
      },
      remoteSync: {
        status: "idle",
        pendingRevision: null,
        message: null,
      },
    });
  };

  return {
    initialize: (snapshot) => {
      if (disposed) {
        throw new Error("ProjectController has been disposed");
      }
      activate(snapshot);
    },
    getActiveSnapshot: () =>
      activeSnapshot === null ? null : structuredClone(activeSnapshot),
    adoptMutationSnapshot: (snapshot) => {
      if (
        disposed ||
        activeSnapshot === null ||
        snapshot.project.id !== activeSnapshot.project.id ||
        snapshot.revision < store.getState().runtime.revision
      ) {
        return false;
      }
      const localProject = store.getState().project;
      activeSnapshot = {
        ...structuredClone(snapshot),
        project: {
          ...structuredClone(snapshot.project),
          semanticState: localProject.semanticState,
          layoutState: localProject.layoutState,
        },
      };
      store.acknowledgeRevision(snapshot.revision);
      upsertProject(projectSummary(activeSnapshot));
      return true;
    },
    getState: () => ({
      ...state,
      projects: state.projects.map((project) => ({ ...project })),
      pendingSwitch:
        state.pendingSwitch === null ? null : { ...state.pendingSwitch },
      remoteSync: { ...state.remoteSync },
    }),
    subscribe: (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    switchProject,
    retrySwitch: () => {
      const pending = state.pendingSwitch;
      return pending === null
        ? Promise.resolve({ ok: false, kind: "stale" })
        : switchProject(pending.projectId);
    },
    stayOnProject: () => {
      switchEpoch += 1;
      loadAbort?.abort();
      update({ pendingSwitch: null });
    },
    discardAndSwitch: () => {
      const pending = state.pendingSwitch;
      if (pending === null || disposed) {
        return Promise.resolve({ ok: false, kind: "stale" });
      }
      switchEpoch += 1;
      const epoch = switchEpoch;
      loadAbort?.abort();
      update({ pendingSwitch: null });
      return loadTarget(pending.projectId, epoch);
    },
    renameActiveProject: async (name) => {
      const snapshot = activeSnapshot;
      if (snapshot === null) {
        return { ok: false, kind: "server", message: "No active project" };
      }
      return mutateProject(snapshot.project.id, (revision) =>
        api.renameProject(snapshot.project.id, revision, name),
      );
    },
    searchProjects,
    createProject,
    archiveProject: async (projectId) => {
      const archivingActive = activeSnapshot?.project.id === projectId;
      const result = await mutateProject(projectId, (revision) =>
        api.archiveProject(projectId, revision),
      );
      if (
        result.ok &&
        archivingActive &&
        activeSnapshot?.project.id === projectId &&
        result.snapshot.project.status === "archived"
      ) {
        deactivate();
      }
      return result;
    },
    restoreProject: (projectId) =>
      mutateProject(projectId, (revision) =>
        api.restoreProject(projectId, revision),
      ),
    requestDeleteProject: (projectId) => {
      if (
        activeSnapshot?.project.id === projectId ||
        state.projects.some((project) => project.id === projectId)
      ) {
        update({ deleteCandidateId: projectId });
      }
    },
    cancelDeleteProject: () => {
      update({ deleteCandidateId: null });
    },
    confirmDeleteProject: async () => {
      const projectId = state.deleteCandidateId;
      if (projectId === null) {
        return { ok: false, kind: "server", message: "No project selected for deletion" };
      }
      const result = await mutateProject(projectId, (revision) =>
        api.deleteProject(projectId, revision),
      );
      if (result.ok) {
        const deletingActive = activeSnapshot?.project.id === projectId;
        if (deletingActive) {
          deactivate();
        }
        update({
          projects: state.projects.filter((project) => project.id !== projectId),
          deleteCandidateId: null,
        });
      }
      return result;
    },
    flushSave: () =>
      autosave?.flush() ?? Promise.resolve({ ok: true as const }),
    retrySave: () =>
      autosave?.retry() ?? Promise.resolve({ ok: true as const }),
    retryRemoteSync: () => refreshCleanProject(),
    dispose: () => {
      if (disposed) {
        return;
      }
      disposed = true;
      switchEpoch += 1;
      activeSessionEpoch += 1;
      bufferedRemote = null;
      loadAbort?.abort();
      loadAbort = null;
      refreshAbort?.abort();
      refreshAbort = null;
      refreshInFlight = null;
      searchAbort?.abort();
      searchAbort = null;
      autosave?.dispose();
      autosave = null;
      unsubscribeAutosave?.();
      unsubscribeAutosave = null;
      events?.close();
      events = null;
      listeners.clear();
    },
  };
}
