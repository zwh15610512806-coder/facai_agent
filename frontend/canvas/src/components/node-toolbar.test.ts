import { expect, test, vi } from "vitest";

import type { CanvasNode } from "../domain/types";
import { createNodeToolbar, type NodeToolbarOptions } from "./node-toolbar";

test("node toolbar delegates node IDs to its mounted workspace", () => {
  const onAdd = vi.fn<(node: CanvasNode) => void>();
  const nextId = vi.fn(() => "advanced:prompt:7");
  const toolbar = createNodeToolbar({
    disabled: false,
    onAdd,
    nextId,
  } as NodeToolbarOptions & { nextId(kind: CanvasNode["kind"]): string });

  [...toolbar.querySelectorAll<HTMLButtonElement>("button")]
    .find((button) => button.textContent === "添加 prompt")
    ?.click();

  expect(nextId).toHaveBeenCalledWith("prompt");
  expect(onAdd).toHaveBeenCalledWith(expect.objectContaining({
    id: "advanced:prompt:7",
    kind: "prompt",
  }));
});

test("node toolbar never offers a fake auto-cutout node", () => {
  const toolbar = createNodeToolbar({
    disabled: false,
    onAdd: vi.fn(),
    nextId: vi.fn(() => "advanced:node:1"),
  });

  expect([...toolbar.querySelectorAll("button")].map((button) => button.textContent)).not.toContain(
    "添加 auto_cutout",
  );
});
