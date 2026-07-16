import { describe, expect, test, vi } from "vitest";

import { createEmptyProjectState } from "../domain/types";
import {
  createCanvasApi,
  type Fetcher,
  type ProjectSnapshot,
} from "./client";

function snapshot(revision = 1, projectId = "project-a"): ProjectSnapshot {
  const state = createEmptyProjectState();
  return {
    project: {
      id: projectId,
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

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("Canvas API client", () => {
  test("saves canonical state and returns a typed success snapshot", async () => {
    const fetcher = vi.fn<Fetcher>(async () => jsonResponse(snapshot(2, "project a")));
    const api = createCanvasApi({ apiBase: "/api/canvas/", fetcher });
    const state = createEmptyProjectState();

    await expect(
      api.saveProjectState({
        projectId: "project a",
        revision: 1,
        semanticState: state.semanticState,
        layoutState: state.layoutState,
      }),
    ).resolves.toEqual({ ok: true, snapshot: snapshot(2, "project a") });

    expect(fetcher).toHaveBeenCalledTimes(1);
    const [url, init] = fetcher.mock.calls[0] ?? [];
    expect(url).toBe("/api/canvas/projects/project%20a/state");
    expect(init).toMatchObject({ method: "PUT" });
    expect(JSON.parse(String(init?.body))).toEqual({
      revision: 1,
      semanticState: state.semanticState,
      layoutState: state.layoutState,
    });
  });

  test("maps only the revision conflict payload to conflict", async () => {
    const conflict = {
      detail: "Canvas project revision conflict",
      code: "canvas_revision_conflict",
      currentRevision: 7,
    };
    const api = createCanvasApi({
      apiBase: "/api/canvas",
      fetcher: vi.fn(async () => jsonResponse(conflict, 409)),
    });
    const state = createEmptyProjectState();

    await expect(
      api.saveProjectState({
        projectId: "project-a",
        revision: 1,
        semanticState: state.semanticState,
        layoutState: state.layoutState,
      }),
    ).resolves.toEqual({ ok: false, kind: "conflict", currentRevision: 7 });
  });

  test("keeps HTTP and network failures distinct and rethrows AbortError", async () => {
    const state = createEmptyProjectState();
    const request = {
      projectId: "project-a",
      revision: 1,
      semanticState: state.semanticState,
      layoutState: state.layoutState,
    };
    const server = createCanvasApi({
      apiBase: "/api/canvas",
      fetcher: vi.fn(async () => jsonResponse({ detail: "broken" }, 500)),
    });
    await expect(server.saveProjectState(request)).resolves.toEqual({
      ok: false,
      kind: "server",
      message: "broken",
    });

    const offline = createCanvasApi({
      apiBase: "/api/canvas",
      fetcher: vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    });
    await expect(offline.saveProjectState(request)).resolves.toEqual({
      ok: false,
      kind: "offline",
      message: "Failed to fetch",
    });

    const aborted = createCanvasApi({
      apiBase: "/api/canvas",
      fetcher: vi.fn(async () => {
        throw new DOMException("aborted", "AbortError");
      }),
    });
    await expect(aborted.saveProjectState(request)).rejects.toMatchObject({
      name: "AbortError",
    });
  });

  test("encodes list search and serializes every revisioned project write", async () => {
    const fetcher = vi.fn<Fetcher>(async () => jsonResponse(snapshot(2)));
    const api = createCanvasApi({ apiBase: "/api/canvas", fetcher });

    fetcher.mockResolvedValueOnce(jsonResponse({ projects: [] }));
    await api.listProjects({ query: "A & B", includeArchived: true });
    expect(fetcher.mock.calls[0]?.[0]).toBe(
      "/api/canvas/projects?q=A+%26+B&includeArchived=true",
    );

    await api.renameProject("project-a", 1, "Renamed");
    await api.archiveProject("project-a", 2);
    await api.restoreProject("project-a", 3);
    await api.deleteProject("project-a", 4);

    expect(
      fetcher.mock.calls.slice(1).map(([url, init]) => [
        url,
        init?.method,
        JSON.parse(String(init?.body)),
      ]),
    ).toEqual([
      ["/api/canvas/projects/project-a", "PATCH", { revision: 1, name: "Renamed" }],
      ["/api/canvas/projects/project-a/archive", "POST", { revision: 2 }],
      ["/api/canvas/projects/project-a/restore", "POST", { revision: 3 }],
      ["/api/canvas/projects/project-a", "DELETE", { revision: 4 }],
    ]);
  });

  test("rejects snapshot and list response drift at runtime", async () => {
    const mismatched = snapshot(2);
    mismatched.project.revision = 1;
    const saveApi = createCanvasApi({
      apiBase: "/api/canvas",
      fetcher: vi.fn(async () => jsonResponse(mismatched)),
    });
    const state = createEmptyProjectState();
    await expect(
      saveApi.saveProjectState({
        projectId: "project-a",
        revision: 1,
        semanticState: state.semanticState,
        layoutState: state.layoutState,
      }),
    ).resolves.toMatchObject({ ok: false, kind: "server" });

    const malformedState = snapshot();
    (malformedState.project.semanticState as { mode: string }).mode = "drifted";
    const getApi = createCanvasApi({
      apiBase: "/api/canvas",
      fetcher: vi.fn(async () => jsonResponse(malformedState)),
    });
    await expect(getApi.getProject("project-a")).resolves.toMatchObject({
      ok: false,
      kind: "server",
    });

    const wrongProjectApi = createCanvasApi({
      apiBase: "/api/canvas",
      fetcher: vi.fn(async () => jsonResponse(snapshot())),
    });
    await expect(wrongProjectApi.getProject("project-b")).resolves.toMatchObject({
      ok: false,
      kind: "server",
    });

    const invalidSummary = {
      ...snapshot().project,
      status: "unknown",
    };
    delete (invalidSummary as Partial<ProjectSnapshot["project"]>).semanticState;
    delete (invalidSummary as Partial<ProjectSnapshot["project"]>).layoutState;
    const listApi = createCanvasApi({
      apiBase: "/api/canvas",
      fetcher: vi.fn(async () => jsonResponse({ projects: [invalidSummary] })),
    });
    await expect(listApi.listProjects()).resolves.toMatchObject({
      ok: false,
      kind: "server",
    });
  });
});
