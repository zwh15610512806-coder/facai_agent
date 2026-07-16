import { expect, test, vi } from "vitest";

import type { ModelProfile } from "../domain/providers";
import type { CanvasNode } from "../domain/types";
import { createNodeInspector } from "./node-inspector";

const model = {
  id: "model-1",
  displayName: "Seedream 5.0 Pro",
  enabled: true,
  availability: "available",
} as ModelProfile;

const promptNode: CanvasNode = {
  id: "prompt", kind: "prompt", managedBy: null, skuId: null, assetId: null,
  modelProfileId: null, prompt: "白底", compositionGroupId: null, textSnapshotId: null,
  outputBoardId: null, parameters: {},
};

const generationNode: CanvasNode = {
  id: "generation", kind: "model_generation", managedBy: null, skuId: null, assetId: null,
  modelProfileId: null, prompt: null, compositionGroupId: null, textSnapshotId: null,
  outputBoardId: null, parameters: {},
};

test("node inspector configures a selected generation node with an interactive model and dimensions", () => {
  const inspector = createNodeInspector();
  const onPatch = vi.fn();
  inspector.update([promptNode, generationNode], [model], false, onPatch);

  const node = inspector.element.querySelector<HTMLSelectElement>('select[aria-label="选择高级节点"]');
  if (node === null) throw new Error("missing node selection");
  node.value = "generation";
  node.dispatchEvent(new Event("change", { bubbles: true }));

  const modelSelect = inspector.element.querySelector<HTMLSelectElement>('select[aria-label="节点模型"]');
  const width = inspector.element.querySelector<HTMLInputElement>('input[aria-label="生成宽度"]');
  const height = inspector.element.querySelector<HTMLInputElement>('input[aria-label="生成高度"]');
  if (modelSelect === null || width === null || height === null) throw new Error("missing generation controls");

  modelSelect.value = "model-1";
  modelSelect.dispatchEvent(new Event("change", { bubbles: true }));
  width.value = "1024";
  width.dispatchEvent(new Event("change", { bubbles: true }));
  height.value = "1536";
  height.dispatchEvent(new Event("change", { bubbles: true }));

  expect(onPatch).toHaveBeenCalledWith("generation", { modelProfileId: "model-1" });
  expect(onPatch).toHaveBeenCalledWith("generation", { parameters: { width: 1024 } });
  expect(onPatch).toHaveBeenCalledWith("generation", { parameters: { width: 1024, height: 1536 } });
});

test("node inspector lets users connect only the chosen advanced graph nodes", () => {
  const inspector = createNodeInspector();
  const onConnect = vi.fn();
  (inspector.update as unknown as (...args: unknown[]) => void)(
    [promptNode, generationNode],
    [model],
    false,
    vi.fn(),
    onConnect,
  );

  const source = inspector.element.querySelector<HTMLSelectElement>('select[aria-label="连线来源"]');
  const target = inspector.element.querySelector<HTMLSelectElement>('select[aria-label="连线目标"]');
  const connect = [...inspector.element.querySelectorAll<HTMLButtonElement>("button")]
    .find((button) => button.textContent === "连接节点");
  if (source === null || target === null || connect === undefined) throw new Error("missing connection controls");
  source.value = "prompt";
  target.value = "generation";
  connect.click();

  expect(onConnect).toHaveBeenCalledWith("prompt", "generation");
});

test("node inspector exposes immutable system and managed output nodes only as graph endpoints", () => {
  const inspector = createNodeInspector();
  const onPatch = vi.fn();
  const onConnect = vi.fn();
  const systemProduct: CanvasNode = {
    ...promptNode, id: "main-product-source", kind: "product_source", assetId: "working-main",
  };
  const systemCutout: CanvasNode = {
    ...promptNode, id: "main-product-cutout", kind: "auto_cutout", assetId: "cutout-main",
  };
  const output: CanvasNode = {
    ...promptNode, id: "board-output", kind: "main_output", managedBy: "complete-set", outputBoardId: "board-main",
  };
  inspector.update([systemProduct, systemCutout, generationNode, output], [model], false, onPatch, onConnect);

  const selected = inspector.element.querySelector<HTMLSelectElement>('select[aria-label="选择高级节点"]');
  const source = inspector.element.querySelector<HTMLSelectElement>('select[aria-label="连线来源"]');
  const target = inspector.element.querySelector<HTMLSelectElement>('select[aria-label="连线目标"]');
  if (selected === null || source === null || target === null) throw new Error("missing inspector selectors");
  expect([...selected.options].map((option) => option.value)).toEqual(expect.arrayContaining([
    "main-product-source", "main-product-cutout", "generation", "board-output",
  ]));
  expect([...source.options].map((option) => option.value)).toEqual(expect.arrayContaining([
    "main-product-source", "main-product-cutout", "board-output",
  ]));

  selected.value = "main-product-cutout";
  selected.dispatchEvent(new Event("change", { bubbles: true }));
  expect(inspector.element.querySelector<HTMLTextAreaElement>('textarea[aria-label="节点提示词"]')?.disabled).toBe(true);
  expect(onPatch).not.toHaveBeenCalled();
});
