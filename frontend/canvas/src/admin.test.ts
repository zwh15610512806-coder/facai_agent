import { afterEach, expect, test, vi } from "vitest";

import { mountCanvasModelManager } from "./admin";

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.replaceChildren();
});

test("independent AI config entry mounts image provider management outside Canvas", async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify([]), {
    status: 200,
    headers: { "content-type": "application/json" },
  }));
  vi.stubGlobal("fetch", fetcher);
  const root = document.createElement("div");
  document.body.append(root);

  const mounted = mountCanvasModelManager({ root, apiBase: "/api/canvas" });

  expect(root.querySelector('[data-testid="canvas-model-manager"]')).not.toBeNull();
  expect(root.textContent).toContain("第三方图像模型");
  await vi.waitFor(() => expect(fetcher).toHaveBeenCalled());
  expect(fetcher.mock.calls.every(([url]) => String(url).includes("/api/canvas/model-providers"))).toBe(true);

  mounted.dispose();
  expect(root.childElementCount).toBe(0);
});
