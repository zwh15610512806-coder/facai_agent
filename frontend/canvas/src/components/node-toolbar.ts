import type { CanvasNode } from "../domain/types";

export interface NodeToolbarOptions {
  disabled: boolean;
  onAdd(node: CanvasNode): void;
  nextId(kind: CanvasNode["kind"]): string;
}

const PRESET_KINDS: Array<CanvasNode["kind"]> = [
  "prompt", "model_generation", "composition_group", "text_layer",
];

function createNode(kind: CanvasNode["kind"], id: string): CanvasNode {
  return {
    id,
    kind,
    managedBy: null,
    skuId: null,
    assetId: null,
    modelProfileId: null,
    prompt: kind === "prompt" ? "" : null,
    compositionGroupId: null,
    textSnapshotId: null,
    outputBoardId: null,
    parameters: {},
  };
}

export function createNodeToolbar({ disabled, onAdd, nextId }: NodeToolbarOptions): HTMLElement {
  const element = document.createElement("section");
  element.className = "canvas-node-toolbar";
  element.append(Object.assign(document.createElement("h3"), { textContent: "高级节点" }));
  for (const kind of PRESET_KINDS) {
    const button = document.createElement("button");
    button.type = "button";
    button.disabled = disabled;
    button.textContent = `添加 ${kind}`;
    button.addEventListener("click", () => {
      onAdd(createNode(kind, nextId(kind)));
    });
    element.append(button);
  }
  return element;
}
