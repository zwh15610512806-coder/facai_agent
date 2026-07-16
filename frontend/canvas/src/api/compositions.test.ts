import { expect, test, vi } from "vitest";

import { createCompositionsApi } from "./compositions";

test("composition API posts saved revision, board, explicit background and returns operation id", async () => {
  const fetcher = vi.fn(async () => new Response(JSON.stringify({
    id: "operation-compose",
    projectId: "project-a",
    operationType: "compose",
    status: "queued",
    attemptCount: 0,
    inputAssetId: "background-a",
    outputAssetId: null,
    safeError: null,
  }), { status: 202, headers: { "Content-Type": "application/json" } }));
  const api = createCompositionsApi({ apiBase: "/api/canvas", fetcher });

  const result = await api.enqueueCompose({
    projectId: "project-a",
    revision: 9,
    boardId: "board-main",
    backgroundAssetId: "background-a",
    clientRequestId: "compose-request-a",
  });

  expect(result.ok && result.value.id).toBe("operation-compose");
  expect(fetcher).toHaveBeenCalledWith(
    "/api/canvas/projects/project-a/compose",
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({
        revision: 9,
        boardId: "board-main",
        backgroundAssetId: "background-a",
        idempotencyKey: "compose-request-a",
      }),
    }),
  );
});

test("composition API exposes a 409 revision conflict without retrying or losing the revision", async () => {
  const fetcher = vi.fn(async () => new Response(JSON.stringify({
    code: "canvas_revision_conflict",
    currentRevision: 12,
  }), { status: 409, headers: { "Content-Type": "application/json" } }));
  const api = createCompositionsApi({ apiBase: "/api/canvas", fetcher });

  await expect(api.enqueueCompose({
    projectId: "project-a",
    revision: 9,
    boardId: "board-main",
    backgroundAssetId: "background-a",
    clientRequestId: "compose-request-conflict",
  })).resolves.toEqual({ ok: false, kind: "conflict", currentRevision: 12 });
  expect(fetcher).toHaveBeenCalledTimes(1);
});
