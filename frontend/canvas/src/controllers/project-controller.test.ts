import { describe, expect, test, vi } from "vitest";

import type { CanvasApi, ProjectSnapshot } from "../api/client";
import type {
  CanvasProjectEvent,
  ProjectEventStream,
} from "../api/events";
import type { CanvasAdapter } from "../canvas/canvas-adapter";
import { createEmptyProjectState } from "../domain/types";
import { createProjectStore } from "../state/project-store";
import type { AutosaveController } from "./autosave-controller";
import { createProjectController } from "./project-controller";

function snapshot(id: string, revision = 1): ProjectSnapshot {
  const state = createEmptyProjectState();
  return {
    project: {
      id,
      name: `Project ${id.toUpperCase()}`,
      status: "active",
      schemaVersion: 1,
      revision,
      createdAt: null,
      updatedAt: null,
      archivedAt: null,
      semanticState: state.semanticState,
      layoutState: state.layoutState,
    },
    skus: [],
    revision,
  };
}

function projectState(value: ProjectSnapshot) {
  return {
    schemaVersion: value.project.schemaVersion,
    semanticState: value.project.semanticState,
    layoutState: value.project.layoutState,
  };
}

function withStatus(
  value: ProjectSnapshot,
  status: ProjectSnapshot["project"]["status"],
  revision: number,
): ProjectSnapshot {
  value.project.status = status;
  value.project.revision = revision;
  value.revision = revision;
  return value;
}

function deferred<Value>() {
  let resolve!: (value: Value) => void;
  const promise = new Promise<Value>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

function harness(
  getProject: CanvasApi["getProject"],
  flush: AutosaveController["flush"] = vi.fn(async () => ({ ok: true as const })),
  apiOverrides: Partial<CanvasApi> = {},
) {
  const store = createProjectStore();
  const api = { getProject, ...apiOverrides } as CanvasApi;
  const adapter = {
    project: vi.fn(),
    cancelPendingLoads: vi.fn(),
  } as unknown as CanvasAdapter;
  const oldAutosave = {
    flush,
    dispose: vi.fn(),
    hasUnconfirmedChanges: vi.fn(() => false),
    markConflict: vi.fn(),
    getState: vi.fn(() => ({
      status: "saved" as const,
      dirty: false,
      message: null,
      currentRevision: null,
    })),
    subscribe: vi.fn(() => vi.fn()),
    retry: vi.fn(async () => ({ ok: true as const })),
  } as unknown as AutosaveController;
  const nextAutosave = {
    flush: vi.fn(async () => ({ ok: true as const })),
    dispose: vi.fn(),
    hasUnconfirmedChanges: vi.fn(() => false),
    markConflict: vi.fn(),
    getState: vi.fn(() => ({
      status: "saved" as const,
      dirty: false,
      message: null,
      currentRevision: null,
    })),
    subscribe: vi.fn(() => vi.fn()),
    retry: vi.fn(async () => ({ ok: true as const })),
  } as unknown as AutosaveController;
  const autosaves = [oldAutosave, nextAutosave];
  const oldStream = { close: vi.fn() } satisfies ProjectEventStream;
  const nextStream = { close: vi.fn() } satisfies ProjectEventStream;
  const streams = [oldStream, nextStream];
  const eventHandlers: Array<(event: CanvasProjectEvent) => void> = [];
  const autosaveSaves: Array<CanvasApi["saveProjectState"]> = [];
  const controller = createProjectController({
    api,
    store,
    adapter,
    createAutosave: (_store, save) => {
      autosaveSaves.push(save);
      return autosaves.shift() ?? nextAutosave;
    },
    openEvents: (_projectId, onEvent) => {
      eventHandlers.push(onEvent);
      return streams.shift() ?? nextStream;
    },
  });
  controller.initialize(snapshot("a"));
  vi.mocked(adapter.project).mockClear();
  return {
    controller,
    store,
    api,
    adapter,
    oldAutosave,
    oldStream,
    eventHandlers,
    autosaveSaves,
  };
}

describe("project controller", () => {
  test("keeps the old project, store and SSE until the target GET succeeds", async () => {
    const target = deferred<Awaited<ReturnType<CanvasApi["getProject"]>>>();
    const getProject = vi.fn(() => target.promise);
    const { controller, store, adapter, oldAutosave, oldStream } = harness(getProject);

    const switching = controller.switchProject("b");
    await Promise.resolve();

    expect(oldAutosave.flush).toHaveBeenCalledTimes(1);
    expect(store.getState().runtime.projectId).toBe("a");
    expect(oldStream.close).not.toHaveBeenCalled();
    expect(adapter.project).not.toHaveBeenCalled();

    target.resolve({ ok: true, value: snapshot("b") });
    await expect(switching).resolves.toEqual({ ok: true });

    expect(store.getState().runtime.projectId).toBe("b");
    expect(oldStream.close).toHaveBeenCalledTimes(1);
    expect(oldAutosave.dispose).toHaveBeenCalledTimes(1);
    expect(adapter.project).toHaveBeenCalledWith(null, projectState(snapshot("b")));
    controller.dispose();
  });

  test("ignores a late A to B load after A to C has committed", async () => {
    const b = deferred<Awaited<ReturnType<CanvasApi["getProject"]>>>();
    const c = deferred<Awaited<ReturnType<CanvasApi["getProject"]>>>();
    const getProject = vi.fn((id: string) => (id === "b" ? b.promise : c.promise));
    const { controller, store, adapter, oldStream } = harness(getProject);

    const toB = controller.switchProject("b");
    await Promise.resolve();
    const toC = controller.switchProject("c");
    await Promise.resolve();

    c.resolve({ ok: true, value: snapshot("c") });
    await expect(toC).resolves.toEqual({ ok: true });
    b.resolve({ ok: true, value: snapshot("b") });
    await expect(toB).resolves.toEqual({ ok: false, kind: "stale" });

    expect(store.getState().runtime.projectId).toBe("c");
    expect(adapter.project).toHaveBeenCalledTimes(1);
    expect(adapter.project).toHaveBeenCalledWith(null, projectState(snapshot("c")));
    expect(oldStream.close).toHaveBeenCalledTimes(1);
    controller.dispose();
  });

  test("offers retry and keeps the old project after a failed switch flush", async () => {
    const getProject = vi.fn(async () => ({ ok: true as const, value: snapshot("b") }));
    const flush = vi
      .fn<AutosaveController["flush"]>()
      .mockResolvedValueOnce({ ok: false, kind: "offline", message: "offline" })
      .mockResolvedValueOnce({ ok: true });
    const { controller, store, oldStream } = harness(getProject, flush);

    await expect(controller.switchProject("b")).resolves.toEqual({
      ok: false,
      kind: "decision",
      failure: { ok: false, kind: "offline", message: "offline" },
    });
    expect(controller.getState().pendingSwitch?.projectId).toBe("b");
    expect(getProject).not.toHaveBeenCalled();
    expect(store.getState().runtime.projectId).toBe("a");
    expect(oldStream.close).not.toHaveBeenCalled();

    await expect(controller.retrySwitch()).resolves.toEqual({ ok: true });
    expect(flush).toHaveBeenCalledTimes(2);
    expect(store.getState().runtime.projectId).toBe("b");
    controller.dispose();
  });

  test("stay preserves dirty A while discard loads and atomically replaces it with B", async () => {
    const getProject = vi.fn(async () => ({ ok: true as const, value: snapshot("b") }));
    const failure = { ok: false as const, kind: "conflict" as const, currentRevision: 4 };
    const flush = vi.fn(async () => failure);
    const { controller, store, oldAutosave, oldStream } = harness(getProject, flush);

    await controller.switchProject("b");
    controller.stayOnProject();
    expect(controller.getState().pendingSwitch).toBeNull();
    expect(store.getState().runtime.projectId).toBe("a");
    expect(oldAutosave.dispose).not.toHaveBeenCalled();

    await controller.switchProject("b");
    await expect(controller.discardAndSwitch()).resolves.toEqual({ ok: true });
    expect(store.getState().runtime.projectId).toBe("b");
    expect(oldAutosave.dispose).toHaveBeenCalledTimes(1);
    expect(oldStream.close).toHaveBeenCalledTimes(1);
    controller.dispose();
  });

  test("keeps the active SSE session valid after a failed flush and stay", async () => {
    const failure = { ok: false as const, kind: "offline" as const, message: "offline" };
    const flush = vi.fn(async () => failure);
    const {
      controller,
      oldAutosave,
      eventHandlers,
    } = harness(vi.fn(), flush);

    await controller.switchProject("b");
    controller.stayOnProject();
    vi.mocked(oldAutosave.hasUnconfirmedChanges).mockReturnValue(true);
    eventHandlers[0]?.({
      type: "project.updated",
      projectId: "a",
      revision: 2,
      status: "active",
    });

    expect(oldAutosave.markConflict).toHaveBeenCalledWith(2);
    controller.dispose();
  });

  test("keeps the active SSE session valid after the target GET fails", async () => {
    const getProject = vi.fn(async () => ({
      ok: false as const,
      kind: "server" as const,
      message: "load failed",
    }));
    const {
      controller,
      oldAutosave,
      eventHandlers,
    } = harness(getProject);

    await expect(controller.switchProject("b")).resolves.toEqual({
      ok: false,
      kind: "load",
      message: "load failed",
    });
    vi.mocked(oldAutosave.hasUnconfirmedChanges).mockReturnValue(true);
    eventHandlers[0]?.({
      type: "project.updated",
      projectId: "a",
      revision: 2,
      status: "active",
    });

    expect(oldAutosave.markConflict).toHaveBeenCalledWith(2);
    controller.dispose();
  });

  test("serializes autosave and rename through one revision lane", async () => {
    const saving = deferred<Awaited<ReturnType<CanvasApi["saveProjectState"]>>>();
    const renaming = deferred<Awaited<ReturnType<CanvasApi["renameProject"]>>>();
    const saveProjectState = vi.fn(() => saving.promise);
    const renameProject = vi.fn(() => renaming.promise);
    const { controller, store, autosaveSaves } = harness(
      vi.fn(),
      undefined,
      { saveProjectState, renameProject },
    );
    const state = createEmptyProjectState();

    const saveCall = autosaveSaves[0]?.({
      projectId: "a",
      revision: 1,
      semanticState: state.semanticState,
      layoutState: state.layoutState,
    });
    const renameCall = controller.renameActiveProject("Renamed");
    await Promise.resolve();
    expect(saveProjectState).toHaveBeenCalledTimes(1);
    expect(renameProject).not.toHaveBeenCalled();

    saving.resolve({ ok: true, snapshot: snapshot("a", 2) });
    await saveCall;
    await vi.waitFor(() => {
      expect(renameProject).toHaveBeenCalledWith("a", 2, "Renamed");
    });
    renaming.resolve({ ok: true, snapshot: snapshot("a", 3) });
    await expect(renameCall).resolves.toMatchObject({ ok: true });
    expect(store.getState().runtime.revision).toBe(3);
    controller.dispose();
  });

  test("does not let a late active write corrupt a newly switched project", async () => {
    const renaming = deferred<Awaited<ReturnType<CanvasApi["renameProject"]>>>();
    const renameProject = vi.fn(() => renaming.promise);
    const getProject = vi.fn(async (projectId: string) => ({
      ok: true as const,
      value: snapshot(projectId),
    }));
    const { controller, store } = harness(
      getProject,
      undefined,
      { renameProject },
    );

    const renameCall = controller.renameActiveProject("Renamed A");
    await vi.waitFor(() => {
      expect(renameProject).toHaveBeenCalledWith("a", 1, "Renamed A");
    });
    await expect(controller.switchProject("b")).resolves.toEqual({ ok: true });

    renaming.resolve({ ok: true, snapshot: snapshot("a", 2) });
    await expect(renameCall).resolves.toMatchObject({ ok: true });

    expect(store.getState().runtime).toMatchObject({ projectId: "b", revision: 1 });
    expect(controller.getState().activeProjectId).toBe("b");
    controller.dispose();
  });

  test("ignores an in-flight write result after the controller is disposed", async () => {
    const renaming = deferred<Awaited<ReturnType<CanvasApi["renameProject"]>>>();
    const renameProject = vi.fn(() => renaming.promise);
    const { controller, store } = harness(
      vi.fn(),
      undefined,
      { renameProject },
    );

    const renameCall = controller.renameActiveProject("Renamed after dispose");
    await vi.waitFor(() => {
      expect(renameProject).toHaveBeenCalledTimes(1);
    });
    controller.dispose();
    renaming.resolve({ ok: true, snapshot: snapshot("a", 2) });
    await expect(renameCall).resolves.toMatchObject({ ok: true });

    expect(store.getState().runtime).toMatchObject({ projectId: "a", revision: 1 });
  });

  test("does not apply a buffered old-project revision to a new active session", async () => {
    const archiving = deferred<Awaited<ReturnType<CanvasApi["archiveProject"]>>>();
    const archiveProject = vi.fn(() => archiving.promise);
    const listProjects = vi.fn(async () => ({
      ok: true as const,
      value: [snapshot("a").project, snapshot("x").project],
    }));
    const getProject = vi.fn(async (projectId: string) => ({
      ok: true as const,
      value: snapshot(projectId),
    }));
    const {
      controller,
      store,
      eventHandlers,
    } = harness(getProject, undefined, { archiveProject, listProjects });

    await controller.searchProjects("", false);
    const archiveCall = controller.archiveProject("x");
    await vi.waitFor(() => {
      expect(archiveProject).toHaveBeenCalledWith("x", 1);
    });
    eventHandlers[0]?.({
      type: "project.updated",
      projectId: "a",
      revision: 5,
      status: "active",
    });
    await expect(controller.switchProject("b")).resolves.toEqual({ ok: true });

    archiving.resolve({
      ok: true,
      snapshot: withStatus(snapshot("x"), "archived", 2),
    });
    await archiveCall;
    await new Promise<void>((resolve) => setTimeout(resolve, 0));

    expect(getProject).toHaveBeenCalledTimes(1);
    expect(store.getState().runtime).toMatchObject({ projectId: "b", revision: 1 });
    controller.dispose();
  });

  test("does not roll a clean SSE refresh back behind a newer local write", async () => {
    const refreshing = deferred<Awaited<ReturnType<CanvasApi["getProject"]>>>();
    const getProject = vi.fn(() => refreshing.promise);
    const renameProject = vi.fn(async () => ({
      ok: true as const,
      snapshot: snapshot("a", 3),
    }));
    const {
      controller,
      store,
      adapter,
      eventHandlers,
    } = harness(getProject, undefined, { renameProject });

    eventHandlers[0]?.({
      type: "project.updated",
      projectId: "a",
      revision: 2,
      status: "active",
    });
    expect(getProject).toHaveBeenCalledWith("a", expect.any(AbortSignal));

    await controller.renameActiveProject("Renamed at revision 3");
    expect(store.getState().runtime.revision).toBe(3);
    refreshing.resolve({ ok: true, value: snapshot("a", 2) });
    await new Promise<void>((resolve) => setTimeout(resolve, 0));

    expect(store.getState().runtime).toMatchObject({ projectId: "a", revision: 3 });
    expect(adapter.project).not.toHaveBeenCalled();
    controller.dispose();
  });

  test("does not let a late create response override a newer project switch", async () => {
    const creating = deferred<Awaited<ReturnType<CanvasApi["createProject"]>>>();
    const createProject = vi.fn(() => creating.promise);
    const getProject = vi.fn(async (projectId: string) => ({
      ok: true as const,
      value: snapshot(projectId),
    }));
    const { controller, store } = harness(
      getProject,
      undefined,
      { createProject },
    );

    const createCall = controller.createProject("Project C");
    await vi.waitFor(() => {
      expect(createProject).toHaveBeenCalledWith("Project C");
    });
    await expect(controller.switchProject("b")).resolves.toEqual({ ok: true });
    creating.resolve({ ok: true, value: snapshot("c") });
    await expect(createCall).resolves.toMatchObject({ ok: true });

    expect(store.getState().runtime).toMatchObject({ projectId: "b", revision: 1 });
    expect(controller.getState().activeProjectId).toBe("b");
    expect(controller.getState().projects).toContainEqual(
      expect.objectContaining({ id: "c" }),
    );
    controller.dispose();
  });

  test("ignores local SSE echoes in flight and marks dirty newer remote state conflicted", async () => {
    const saving = deferred<Awaited<ReturnType<CanvasApi["saveProjectState"]>>>();
    const saveProjectState = vi.fn(() => saving.promise);
    const getProject = vi.fn();
    const {
      controller,
      oldAutosave,
      eventHandlers,
      autosaveSaves,
    } = harness(getProject, undefined, { saveProjectState });
    const state = createEmptyProjectState();
    const saveCall = autosaveSaves[0]?.({
      projectId: "a",
      revision: 1,
      semanticState: state.semanticState,
      layoutState: state.layoutState,
    });

    vi.mocked(oldAutosave.hasUnconfirmedChanges).mockReturnValue(true);
    eventHandlers[0]?.({
      type: "project.state_saved",
      projectId: "a",
      revision: 2,
      status: "active",
      summary: { nodeCount: 0, edgeCount: 0, outputBoardCount: 0 },
    });
    expect(oldAutosave.markConflict).not.toHaveBeenCalled();
    expect(getProject).not.toHaveBeenCalled();

    saving.resolve({ ok: true, snapshot: snapshot("a", 2) });
    await saveCall;
    expect(getProject).not.toHaveBeenCalled();

    eventHandlers[0]?.({
      type: "project.updated",
      projectId: "a",
      revision: 3,
      status: "active",
    });
    expect(oldAutosave.markConflict).toHaveBeenCalledWith(3);
    expect(getProject).not.toHaveBeenCalled();
    controller.dispose();
  });

  test("coalesces remote revisions and retries an offline refresh without losing the latest", async () => {
    const firstRefresh = deferred<Awaited<ReturnType<CanvasApi["getProject"]>>>();
    const getProject = vi
      .fn<CanvasApi["getProject"]>()
      .mockImplementationOnce(() => firstRefresh.promise)
      .mockResolvedValueOnce({ ok: true, value: snapshot("a", 3) });
    const {
      controller,
      store,
      adapter,
      eventHandlers,
    } = harness(getProject);

    eventHandlers[0]?.({
      type: "project.updated",
      projectId: "a",
      revision: 2,
      status: "active",
    });
    eventHandlers[0]?.({
      type: "project.state_saved",
      projectId: "a",
      revision: 3,
      status: "active",
      summary: { nodeCount: 0, edgeCount: 0, outputBoardCount: 0 },
    });
    expect(getProject).toHaveBeenCalledTimes(1);

    firstRefresh.resolve({ ok: false, kind: "offline", message: "offline" });
    await new Promise<void>((resolve) => setTimeout(resolve, 0));
    expect(controller.getState().remoteSync).toEqual({
      status: "failed",
      pendingRevision: 3,
      message: "offline",
    });

    await controller.retryRemoteSync();
    expect(getProject).toHaveBeenCalledTimes(2);
    expect(store.getState().runtime).toMatchObject({ projectId: "a", revision: 3 });
    expect(adapter.project).toHaveBeenCalledTimes(1);
    expect(controller.getState().remoteSync).toEqual({
      status: "idle",
      pendingRevision: null,
      message: null,
    });
    controller.dispose();
  });

  test("keeps a replica-lag revision pending until a later retry can reconcile it", async () => {
    const getProject = vi
      .fn<CanvasApi["getProject"]>()
      .mockResolvedValueOnce({ ok: true, value: snapshot("a", 2) })
      .mockResolvedValueOnce({ ok: true, value: snapshot("a", 4) });
    const {
      controller,
      store,
      adapter,
      eventHandlers,
    } = harness(getProject);

    eventHandlers[0]?.({
      type: "project.updated",
      projectId: "a",
      revision: 4,
      status: "active",
    });
    await new Promise<void>((resolve) => setTimeout(resolve, 0));

    expect(store.getState().runtime.revision).toBe(1);
    expect(adapter.project).not.toHaveBeenCalled();
    expect(controller.getState().remoteSync).toMatchObject({
      status: "failed",
      pendingRevision: 4,
    });

    await controller.retryRemoteSync();
    expect(store.getState().runtime.revision).toBe(4);
    expect(adapter.project).toHaveBeenCalledTimes(1);
    controller.dispose();
  });

  test("does not apply a pending remote refresh after switching or disposal", async () => {
    const switchingRefresh = deferred<Awaited<ReturnType<CanvasApi["getProject"]>>>();
    const switchGet = vi.fn((projectId: string) =>
      projectId === "a"
        ? switchingRefresh.promise
        : Promise.resolve({ ok: true as const, value: snapshot("b") }),
    );
    const switched = harness(switchGet);
    switched.eventHandlers[0]?.({
      type: "project.updated",
      projectId: "a",
      revision: 3,
      status: "active",
    });
    await switched.controller.switchProject("b");
    switchingRefresh.resolve({ ok: true, value: snapshot("a", 3) });
    await new Promise<void>((resolve) => setTimeout(resolve, 0));
    expect(switched.store.getState().runtime).toMatchObject({ projectId: "b", revision: 1 });
    switched.controller.dispose();

    const disposedRefresh = deferred<Awaited<ReturnType<CanvasApi["getProject"]>>>();
    const disposed = harness(vi.fn(() => disposedRefresh.promise));
    disposed.eventHandlers[0]?.({
      type: "project.updated",
      projectId: "a",
      revision: 3,
      status: "active",
    });
    disposed.controller.dispose();
    disposedRefresh.resolve({ ok: true, value: snapshot("a", 3) });
    await new Promise<void>((resolve) => setTimeout(resolve, 0));
    expect(disposed.store.getState().runtime).toMatchObject({ projectId: "a", revision: 1 });
  });

  test("ignores stale project searches and creates the selected project workspace", async () => {
    const oldSearch = deferred<Awaited<ReturnType<CanvasApi["listProjects"]>>>();
    const newSearch = deferred<Awaited<ReturnType<CanvasApi["listProjects"]>>>();
    const listProjects = vi.fn(({ query }: { query?: string } = {}) =>
      query === "old" ? oldSearch.promise : newSearch.promise,
    );
    const createProject = vi.fn(async () => ({
      ok: true as const,
      value: snapshot("new"),
    }));
    const { controller, store, oldStream } = harness(
      vi.fn(),
      undefined,
      { listProjects, createProject },
    );

    const oldRequest = controller.searchProjects("old", true);
    const newRequest = controller.searchProjects("new", true);
    newSearch.resolve({
      ok: true,
      value: [snapshot("new").project],
    });
    await newRequest;
    oldSearch.resolve({
      ok: true,
      value: [snapshot("old").project],
    });
    await oldRequest;

    expect(controller.getState()).toMatchObject({
      query: "new",
      includeArchived: true,
      projects: [expect.objectContaining({ id: "new" })],
    });

    await expect(controller.createProject("Project New")).resolves.toMatchObject({
      ok: true,
    });
    expect(createProject).toHaveBeenCalledWith("Project New");
    expect(store.getState().runtime.projectId).toBe("new");
    expect(oldStream.close).toHaveBeenCalledTimes(1);
    controller.dispose();
  });

  test("archives, restores and deletes only after explicit confirmation on the shared lane", async () => {
    const archiveProject = vi.fn(async () => ({
      ok: true as const,
      snapshot: withStatus(snapshot("a"), "archived", 2),
    }));
    const restoreProject = vi.fn(async () => ({
      ok: true as const,
      snapshot: withStatus(snapshot("a"), "active", 3),
    }));
    const deleteProject = vi.fn(async () => ({
      ok: true as const,
      snapshot: withStatus(snapshot("a"), "deleting", 4),
    }));
    const listProjects = vi.fn(async () => ({
      ok: true as const,
      value: [snapshot("a").project],
    }));
    const { controller, store } = harness(
      vi.fn(),
      undefined,
      { archiveProject, restoreProject, deleteProject, listProjects },
    );

    await controller.searchProjects("", true);
    await controller.archiveProject("a");
    await controller.restoreProject("a");
    controller.requestDeleteProject("a");
    expect(controller.getState().deleteCandidateId).toBe("a");
    expect(deleteProject).not.toHaveBeenCalled();
    await controller.confirmDeleteProject();

    expect(archiveProject).toHaveBeenCalledWith("a", 1);
    expect(restoreProject).toHaveBeenCalledWith("a", 2);
    expect(deleteProject).toHaveBeenCalledWith("a", 3);
    expect(controller.getState().activeProjectId).toBeNull();
    expect(controller.getState().projects).toEqual([]);
    expect(store.getState().runtime.projectId).toBe("local-project");
    controller.dispose();
  });

  test.each([
    [false, "", false],
    [true, "project", true],
    [true, "missing", false],
  ] as const)(
    "archives the active project into a non-editable empty state and filters it (archived=%s query=%s)",
    async (includeArchived, query, expectListed) => {
      const archiveProject = vi.fn(async () => ({
        ok: true as const,
        snapshot: withStatus(snapshot("a"), "archived", 2),
      }));
      const listProjects = vi.fn(async () => ({
        ok: true as const,
        value: [snapshot("a").project],
      }));
      const {
        controller,
        store,
        oldAutosave,
      } = harness(vi.fn(), undefined, { archiveProject, listProjects });
      await controller.searchProjects(query, includeArchived);

      await expect(controller.archiveProject("a")).resolves.toMatchObject({ ok: true });

      expect(controller.getState().activeProjectId).toBeNull();
      expect(store.getState().runtime).toMatchObject({
        projectId: "local-project",
        revision: 0,
      });
      expect(oldAutosave.dispose).toHaveBeenCalledTimes(1);
      await controller.retrySave();
      expect(oldAutosave.retry).not.toHaveBeenCalled();
      expect(controller.getState().projects.some((project) => project.id === "a")).toBe(
        expectListed,
      );
      controller.dispose();
    },
  );

  test("adopts a successful SKU snapshot revision without replacing dirty local canvas state", () => {
    const { controller, store } = harness(vi.fn());
    store.dispatch({ type: "mode/set", mode: "advanced" });
    const mutation = snapshot("a", 2);
    mutation.skus.push({
      id: "sku-a",
      projectId: "a",
      name: "SKU A",
      sortOrder: 0,
      referenceAssetId: null,
      prompt: "",
      config: {},
    });

    expect(controller.adoptMutationSnapshot(mutation)).toBe(true);
    expect(store.getState().runtime.revision).toBe(2);
    expect(store.getState().project.semanticState.mode).toBe("advanced");
    expect(controller.getActiveSnapshot()).toMatchObject({
      revision: 2,
      skus: [{ id: "sku-a" }],
      project: { semanticState: { mode: "advanced" } },
    });
    expect(controller.adoptMutationSnapshot(snapshot("b", 3))).toBe(false);
    controller.dispose();
  });

  test("ignores non-revision asset operation events in the project refresh lane", () => {
    const getProject = vi.fn();
    const { controller, store, eventHandlers } = harness(getProject);

    eventHandlers[0]?.({
      type: "operation.queued",
      projectId: "a",
      operation: {
        id: "operation-a",
        projectId: "a",
        operationType: "cutout",
        status: "queued",
        inputAssetId: "working-a",
      },
    });

    expect(getProject).not.toHaveBeenCalled();
    expect(store.getState().runtime.revision).toBe(1);
    expect(controller.getState().remoteSync.status).toBe("idle");
    controller.dispose();
  });

  test("exposes the current autosave flush result for authoritative paid operations", async () => {
    const flush = vi.fn(async () => ({
      ok: false as const,
      kind: "offline" as const,
      message: "offline",
    }));
    const { controller } = harness(vi.fn(), flush);

    await expect(controller.flushSave()).resolves.toEqual({
      ok: false,
      kind: "offline",
      message: "offline",
    });
    expect(flush).toHaveBeenCalledTimes(1);
    controller.dispose();
  });
});
