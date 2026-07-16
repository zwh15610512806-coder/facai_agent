import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import type { ProjectSnapshot, SaveResult } from "../api/client";
import { createEmptyProjectState } from "../domain/types";
import { createProjectStore } from "../state/project-store";
import { createAutosaveController } from "./autosave-controller";

function snapshot(revision: number): ProjectSnapshot {
  const state = createEmptyProjectState();
  return {
    project: {
      id: "project-a",
      name: "Project A",
      status: "active",
      schemaVersion: 1,
      revision,
      createdAt: "2026-07-13T00:00:00",
      updatedAt: "2026-07-13T00:00:00",
      archivedAt: null,
      semanticState: state.semanticState,
      layoutState: state.layoutState,
    },
    skus: [],
    revision,
  };
}

function deferred<Result>() {
  let resolve!: (result: Result) => void;
  const promise = new Promise<Result>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

describe("autosave controller", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      value: "visible",
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  test("debounces a local edit for one second and saves with the current revision", async () => {
    const store = createProjectStore(createEmptyProjectState(), {
      projectId: "project-a",
      revision: 1,
    });
    const save = vi.fn(async (): Promise<SaveResult> => ({
      ok: true,
      snapshot: snapshot(2),
    }));
    const controller = createAutosaveController({ store, save });

    store.dispatch({ type: "mode/set", mode: "advanced" });
    expect(controller.getState().status).toBe("dirty");

    await vi.advanceTimersByTimeAsync(999);
    expect(save).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(1);
    await controller.whenIdle();

    expect(save).toHaveBeenCalledTimes(1);
    expect(save).toHaveBeenCalledWith({
      projectId: "project-a",
      revision: 1,
      semanticState: expect.objectContaining({ mode: "advanced" }),
      layoutState: expect.any(Object),
    });
    expect(store.getState().runtime.revision).toBe(2);
    expect(store.canUndo()).toBe(true);
    expect(controller.getState()).toMatchObject({ status: "saved", dirty: false });

    controller.dispose();
  });

  test("coalesces edits made during a save into one latest follow-up save", async () => {
    const store = createProjectStore(createEmptyProjectState(), {
      projectId: "project-a",
      revision: 1,
    });
    const first = deferred<SaveResult>();
    const save = vi
      .fn<(request: unknown) => Promise<SaveResult>>()
      .mockImplementationOnce(() => first.promise)
      .mockResolvedValueOnce({ ok: true, snapshot: snapshot(3) });
    const controller = createAutosaveController({ store, save });

    store.dispatch({ type: "mode/set", mode: "advanced" });
    await vi.advanceTimersByTimeAsync(1_000);
    expect(save).toHaveBeenCalledTimes(1);

    store.dispatch({ type: "mode/set", mode: "complete-set" });
    store.dispatch({ type: "mode/set", mode: "advanced" });
    store.dispatch({
      type: "node/add",
      node: {
        id: "prompt-node",
        kind: "prompt",
        managedBy: null,
        skuId: null,
        assetId: null,
        modelProfileId: null,
        prompt: "latest prompt",
        compositionGroupId: null,
        textSnapshotId: null,
        outputBoardId: null,
        parameters: {},
      },
    });

    first.resolve({ ok: true, snapshot: snapshot(2) });
    await controller.whenIdle();

    expect(save).toHaveBeenCalledTimes(2);
    expect(save.mock.calls[1]?.[0]).toMatchObject({
      projectId: "project-a",
      revision: 2,
      semanticState: {
        mode: "advanced",
        nodes: [expect.objectContaining({ id: "prompt-node", prompt: "latest prompt" })],
      },
    });
    expect(store.getState().runtime.revision).toBe(3);
    expect(controller.getState().dirty).toBe(false);

    controller.dispose();
  });

  test("keeps local state dirty and exposes the current revision after a conflict", async () => {
    const store = createProjectStore(createEmptyProjectState(), {
      projectId: "project-a",
      revision: 1,
    });
    const save = vi.fn(async (): Promise<SaveResult> => ({
      ok: false,
      kind: "conflict",
      currentRevision: 4,
    }));
    const controller = createAutosaveController({ store, save });

    store.dispatch({ type: "mode/set", mode: "advanced" });
    const result = await controller.flush();

    expect(result).toEqual({ ok: false, kind: "conflict", currentRevision: 4 });
    expect(controller.getState()).toEqual({
      status: "conflict",
      dirty: true,
      message: "Project changed elsewhere",
      currentRevision: 4,
    });
    expect(store.getState().runtime.revision).toBe(1);
    expect(store.getState().project.semanticState.mode).toBe("advanced");

    store.dispatch({ type: "mode/set", mode: "complete-set" });
    await vi.advanceTimersByTimeAsync(5_000);
    expect(save).toHaveBeenCalledTimes(1);
    controller.dispose();
  });

  test("keeps a newer remote conflict after an in-flight save succeeds", async () => {
    const store = createProjectStore(createEmptyProjectState(), {
      projectId: "project-a",
      revision: 1,
    });
    const saving = deferred<SaveResult>();
    const save = vi.fn(() => saving.promise);
    const controller = createAutosaveController({ store, save });

    store.dispatch({ type: "mode/set", mode: "advanced" });
    const flushing = controller.flush();
    await vi.waitFor(() => {
      expect(save).toHaveBeenCalledTimes(1);
    });
    controller.markConflict(3);
    saving.resolve({ ok: true, snapshot: snapshot(2) });

    await expect(flushing).resolves.toEqual({
      ok: false,
      kind: "conflict",
      currentRevision: 3,
    });
    expect(controller.getState()).toMatchObject({
      status: "conflict",
      dirty: true,
      currentRevision: 3,
    });
    expect(controller.hasUnconfirmedChanges()).toBe(true);
    expect(store.getState().runtime.revision).toBe(2);
    controller.dispose();
  });

  test.each([
    ["offline", "offline"],
    ["server", "failed"],
  ] as const)(
    "retains dirty state after a %s failure and saves on explicit retry",
    async (kind, status) => {
      const store = createProjectStore(createEmptyProjectState(), {
        projectId: "project-a",
        revision: 1,
      });
      const save = vi
        .fn<(request: unknown) => Promise<SaveResult>>()
        .mockResolvedValueOnce({ ok: false, kind, message: `${kind} failure` })
        .mockResolvedValueOnce({ ok: true, snapshot: snapshot(2) });
      const controller = createAutosaveController({ store, save });

      store.dispatch({ type: "mode/set", mode: "advanced" });
      expect(await controller.flush()).toEqual({
        ok: false,
        kind,
        message: `${kind} failure`,
      });
      expect(controller.getState()).toMatchObject({ status, dirty: true });

      expect(await controller.retry()).toEqual({ ok: true });
      expect(save).toHaveBeenCalledTimes(2);
      expect(controller.getState()).toMatchObject({ status: "saved", dirty: false });
      controller.dispose();
    },
  );

  test("flushes on hidden visibility and pagehide and warns only while unconfirmed", async () => {
    const store = createProjectStore(createEmptyProjectState(), {
      projectId: "project-a",
      revision: 1,
    });
    const save = vi
      .fn<(request: unknown) => Promise<SaveResult>>()
      .mockResolvedValueOnce({ ok: true, snapshot: snapshot(2) })
      .mockResolvedValueOnce({ ok: true, snapshot: snapshot(3) });
    const controller = createAutosaveController({ store, save });

    const cleanUnload = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(cleanUnload);
    expect(cleanUnload.defaultPrevented).toBe(false);

    store.dispatch({ type: "mode/set", mode: "advanced" });
    const dirtyUnload = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(dirtyUnload);
    expect(dirtyUnload.defaultPrevented).toBe(true);

    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      value: "hidden",
    });
    document.dispatchEvent(new Event("visibilitychange"));
    await controller.whenIdle();
    expect(save).toHaveBeenCalledTimes(1);

    store.dispatch({ type: "mode/set", mode: "complete-set" });
    window.dispatchEvent(new Event("pagehide"));
    await controller.whenIdle();
    expect(save).toHaveBeenCalledTimes(2);

    const savedUnload = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(savedUnload);
    expect(savedUnload.defaultPrevented).toBe(false);
    controller.dispose();
  });

  test("marks a dirty project conflicted from a newer remote event without saving", async () => {
    const store = createProjectStore(createEmptyProjectState(), {
      projectId: "project-a",
      revision: 1,
    });
    const save = vi.fn(async (): Promise<SaveResult> => ({
      ok: true,
      snapshot: snapshot(2),
    }));
    const controller = createAutosaveController({ store, save });

    store.dispatch({ type: "mode/set", mode: "advanced" });
    controller.markConflict(5);
    await vi.advanceTimersByTimeAsync(5_000);

    expect(save).not.toHaveBeenCalled();
    expect(controller.getState()).toMatchObject({
      status: "conflict",
      dirty: true,
      currentRevision: 5,
    });
    controller.dispose();
  });
});
