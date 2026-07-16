import { expect, test, vi } from "vitest";

import { createTextInspector } from "./text-inspector";
import type { TextSnapshot } from "../domain/types";

const layer: TextSnapshot = {
  id: "text-a",
  nodeId: "node-a",
  content: "标题",
  fontAssetId: null,
  fontFamily: "Noto Sans CJK SC",
  fontVersion: "sha256:2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b",
  boxWidth: 320,
  lines: [{ text: "标题", x: 20, y: 40, width: 80 }],
  fontSize: 24,
  color: "#112233",
  letterSpacing: 1,
  lineHeight: 1.2,
  align: "left",
  baseline: "alphabetic",
  zBand: "above-product",
  sortOrder: 0,
};

test("text inspector exposes every authoritative field and emits typed patches", () => {
  const onUpdate = vi.fn();
  const inspector = createTextInspector({ onUpdate });
  inspector.update({ layers: [layer], selectedLayerId: "text-a", disabled: false });

  for (const testid of [
    "canvas-text-layer-select",
    "canvas-text-content",
    "canvas-text-box-width",
    "canvas-text-font-size",
    "canvas-text-color",
    "canvas-text-align",
    "canvas-text-letter-spacing",
    "canvas-text-line-height",
    "canvas-text-baseline",
    "canvas-text-z-band",
    "canvas-text-line-text-0",
    "canvas-text-line-x-0",
    "canvas-text-line-y-0",
    "canvas-text-line-width-0",
  ]) {
    expect(inspector.element.querySelector(`[data-testid="${testid}"]`)).not.toBeNull();
  }
  const color = inspector.element.querySelector<HTMLInputElement>(
    '[data-testid="canvas-text-color"]',
  );
  const lineX = inspector.element.querySelector<HTMLInputElement>(
    '[data-testid="canvas-text-line-x-0"]',
  );
  if (color === null || lineX === null) throw new Error("missing text controls");
  color.value = "#abcdef";
  color.dispatchEvent(new Event("change", { bubbles: true }));
  lineX.value = "42";
  lineX.dispatchEvent(new Event("change", { bubbles: true }));

  expect(onUpdate).toHaveBeenNthCalledWith(1, "text-a", { color: "#abcdef" });
  expect(onUpdate).toHaveBeenNthCalledWith(2, "text-a", {
    lines: [{ text: "标题", x: 42, y: 40, width: 80 }],
  });
  inspector.dispose();
});

test("text inspector visibly rejects content edits that would auto-create a line", () => {
  const onUpdate = vi.fn();
  const inspector = createTextInspector({ onUpdate });
  inspector.update({ layers: [layer], selectedLayerId: "text-a", disabled: false });
  const content = inspector.element.querySelector<HTMLTextAreaElement>(
    '[data-testid="canvas-text-content"]',
  );
  if (content === null) throw new Error("missing content editor");
  content.value = "标题\n副标题";
  content.dispatchEvent(new Event("change", { bubbles: true }));

  expect(onUpdate).not.toHaveBeenCalled();
  expect(
    inspector.element.querySelector('[data-testid="canvas-text-content-feedback"]')?.textContent,
  ).toContain("逐行设置位置和宽度");
  expect(content.value).toBe("标题");
  inspector.dispose();
});

test("font size rejects fractions and lineHeight emits persisted explicit y positions", () => {
  const onUpdate = vi.fn();
  const inspector = createTextInspector({ onUpdate });
  inspector.update({
    layers: [{
      ...layer,
      content: "标题\n副标题",
      lines: [
        { text: "标题", x: 20, y: 40, width: 80 },
        { text: "副标题", x: 20, y: 100, width: 80 },
      ],
    }],
    selectedLayerId: "text-a",
    disabled: false,
  });
  const fontSize = inspector.element.querySelector<HTMLInputElement>(
    '[data-testid="canvas-text-font-size"]',
  );
  const lineHeight = inspector.element.querySelector<HTMLInputElement>(
    '[data-testid="canvas-text-line-height"]',
  );
  if (fontSize === null || lineHeight === null) throw new Error("missing metric controls");
  expect(fontSize.step).toBe("1");
  expect(fontSize.min).toBe("1");
  fontSize.value = "24.5";
  fontSize.dispatchEvent(new Event("change", { bubbles: true }));
  expect(onUpdate).not.toHaveBeenCalled();

  lineHeight.value = "1.5";
  lineHeight.dispatchEvent(new Event("change", { bubbles: true }));
  expect(onUpdate).toHaveBeenCalledWith("text-a", {
    lineHeight: 1.5,
    lines: [
      { text: "标题", x: 20, y: 40, width: 80 },
      { text: "副标题", x: 20, y: 76, width: 80 },
    ],
  });
  inspector.dispose();
});
