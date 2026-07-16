import { expect, test, vi } from "vitest";

import {
  PINNED_CANVAS_FONT,
  digestSha256,
  lineTopFromAnchor,
  loadPinnedCanvasFont,
  patchTextLineHeight,
  patchTextContentWithoutReflow,
} from "./text-layout";
import type { TextSnapshot } from "./types";

const snapshot: TextSnapshot = {
  id: "text-a",
  nodeId: "node-a",
  content: "old content",
  fontAssetId: null,
  fontFamily: "Noto Sans CJK SC",
  fontVersion: "sha256:2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b",
  boxWidth: 320,
  lines: [{ text: "saved line", x: 10, y: 20, width: 100 }],
  fontSize: 24,
  color: "#112233",
  letterSpacing: 0,
  lineHeight: 1.2,
  align: "left",
  baseline: "alphabetic",
  zBand: "above-product",
  sortOrder: 0,
};

test("content changes synchronize same-count explicit lines without changing metrics", () => {
  const patch = patchTextContentWithoutReflow(snapshot, "new saved line");
  expect(patch).toEqual({
    content: "new saved line",
    lines: [{ text: "new saved line", x: 10, y: 20, width: 100 }],
  });
  expect(snapshot.lines).toEqual([{ text: "saved line", x: 10, y: 20, width: 100 }]);
});

test("content changes reject a different explicit line count instead of auto-layout", () => {
  expect(() => patchTextContentWithoutReflow(snapshot, "first\nsecond")).toThrowError(
    "文字行数变化需要逐行设置位置和宽度",
  );
});

test("four baselines map line.y to one shared logical em box", () => {
  expect(lineTopFromAnchor(100, 20, "top")).toBe(100);
  expect(lineTopFromAnchor(100, 20, "middle")).toBe(90);
  expect(lineTopFromAnchor(100, 20, "bottom")).toBe(80);
  expect(lineTopFromAnchor(100, 20, "alphabetic")).toBe(84);
});

test("lineHeight preserves the first y and deterministically updates later explicit lines", () => {
  const multi = {
    ...snapshot,
    content: "first\nsecond\nthird",
    lines: [
      { text: "first", x: 10, y: 20, width: 100 },
      { text: "second", x: 10, y: 99, width: 100 },
      { text: "third", x: 10, y: 199, width: 100 },
    ],
  };
  expect(patchTextLineHeight(multi, 1.5)).toEqual({
    lineHeight: 1.5,
    lines: [
      { text: "first", x: 10, y: 20, width: 100 },
      { text: "second", x: 10, y: 56, width: 100 },
      { text: "third", x: 10, y: 92, width: 100 },
    ],
  });
  expect(patchTextLineHeight(snapshot, 2).lines).toEqual(snapshot.lines);
});

test("font bytes are digest verified before the exact font is loaded", async () => {
  const order: string[] = [];
  const bytes = new Uint8Array([1, 2, 3]).buffer;
  const fetcher = vi.fn(async () => ({ ok: true, arrayBuffer: async () => bytes }));
  const digest = vi.fn(async () => {
    order.push("digest");
    return PINNED_CANVAS_FONT.sha256;
  });
  const register = vi.fn(async () => {
    order.push("register");
  });

  await loadPinnedCanvasFont({ fetcher, digest, register });

  expect(fetcher).toHaveBeenCalledWith(PINNED_CANVAS_FONT.url, { cache: "force-cache" });
  expect(order).toEqual(["digest", "register"]);
});

test("font digest falls back when the LAN HTTP origin has no Web Crypto", async () => {
  vi.stubGlobal("crypto", undefined);
  try {
    await expect(digestSha256(new Uint8Array([1, 2, 3]).buffer)).resolves.toBe(
      "039058c6f2c0cb492c533b0a4d14ef77cc0f78abccced5287d84a1a2011cfb81",
    );
  } finally {
    vi.unstubAllGlobals();
  }
});
