import type { CompositionLayout } from "../domain/types";

export interface CompositionInspectorState {
  groupId: string;
  layout: CompositionLayout;
  disabled: boolean;
}

export interface CompositionInspectorOptions {
  onUpdate(groupId: string, layout: CompositionLayout): void;
}

export interface CompositionInspector {
  element: HTMLElement;
  update(state: CompositionInspectorState | null): void;
  dispose(): void;
}

type NumericField =
  | "slot.x"
  | "slot.y"
  | "slot.width"
  | "slot.height"
  | "anchor.x"
  | "anchor.y"
  | "baseline"
  | "relativeProductFraction"
  | "safeArea.top"
  | "safeArea.right"
  | "safeArea.bottom"
  | "safeArea.left"
  | "rotation";

const FIELD_LABELS: ReadonlyArray<[NumericField, string, number, number, number]> = [
  ["slot.x", "槽位 X", 0, 1, 0.01],
  ["slot.y", "槽位 Y", 0, 1, 0.01],
  ["slot.width", "槽位宽度", 0.01, 1, 0.01],
  ["slot.height", "槽位高度", 0.01, 1, 0.01],
  ["anchor.x", "锚点 X", 0, 1, 0.01],
  ["anchor.y", "锚点 Y", 0, 1, 0.01],
  ["baseline", "基线", 0, 1, 0.01],
  ["relativeProductFraction", "商品相对占比", 0.01, 1, 0.01],
  ["safeArea.top", "安全区上", 0, 0.99, 0.01],
  ["safeArea.right", "安全区右", 0, 0.99, 0.01],
  ["safeArea.bottom", "安全区下", 0, 0.99, 0.01],
  ["safeArea.left", "安全区左", 0, 0.99, 0.01],
  ["rotation", "允许旋转", -180, 180, 1],
];

function readField(layout: CompositionLayout, field: NumericField): number {
  switch (field) {
    case "slot.x": return layout.slot.x;
    case "slot.y": return layout.slot.y;
    case "slot.width": return layout.slot.width;
    case "slot.height": return layout.slot.height;
    case "anchor.x": return layout.anchor.x;
    case "anchor.y": return layout.anchor.y;
    case "baseline": return layout.baseline;
    case "relativeProductFraction": return layout.relativeProductFraction;
    case "safeArea.top": return layout.safeArea.top;
    case "safeArea.right": return layout.safeArea.right;
    case "safeArea.bottom": return layout.safeArea.bottom;
    case "safeArea.left": return layout.safeArea.left;
    case "rotation": return layout.rotation;
  }
}

function writeField(layout: CompositionLayout, field: NumericField, value: number): void {
  switch (field) {
    case "slot.x": layout.slot.x = value; break;
    case "slot.y": layout.slot.y = value; break;
    case "slot.width": layout.slot.width = value; break;
    case "slot.height": layout.slot.height = value; break;
    case "anchor.x": layout.anchor.x = value; break;
    case "anchor.y": layout.anchor.y = value; break;
    case "baseline": layout.baseline = value; break;
    case "relativeProductFraction": layout.relativeProductFraction = value; break;
    case "safeArea.top": layout.safeArea.top = value; break;
    case "safeArea.right": layout.safeArea.right = value; break;
    case "safeArea.bottom": layout.safeArea.bottom = value; break;
    case "safeArea.left": layout.safeArea.left = value; break;
    case "rotation": layout.rotation = value; break;
  }
}

export function createCompositionInspector({
  onUpdate,
}: CompositionInspectorOptions): CompositionInspector {
  let state: CompositionInspectorState | null = null;
  let disposed = false;
  const element = document.createElement("section");
  element.className = "canvas-composition-inspector";
  element.dataset.testid = "canvas-composition-inspector";

  const render = (): void => {
    const heading = document.createElement("h3");
    heading.textContent = "共享构图";
    if (state === null) {
      const empty = document.createElement("p");
      empty.textContent = "选择构图组后调整 SKU 统一构图。";
      element.replaceChildren(heading, empty);
      return;
    }
    const grid = document.createElement("div");
    grid.className = "canvas-composition-grid";
    for (const [field, copy, minimum, maximum, step] of FIELD_LABELS) {
      const label = document.createElement("label");
      label.textContent = copy;
      const input = document.createElement("input");
      input.type = "number";
      input.min = String(minimum);
      input.max = String(maximum);
      input.step = String(step);
      input.value = String(readField(state.layout, field));
      input.disabled = state.disabled;
      input.dataset.field = field === "baseline" ? "baseline" : field;
      input.addEventListener("change", () => {
        if (disposed || state === null || state.disabled) return;
        const value = Number(input.value);
        if (!Number.isFinite(value)) return;
        const next = structuredClone(state.layout);
        writeField(next, field, value);
        onUpdate(state.groupId, next);
      });
      label.append(input);
      grid.append(label);
    }
    const containLabel = document.createElement("label");
    containLabel.textContent = "保持比例（contain）";
    const contain = document.createElement("input");
    contain.type = "checkbox";
    contain.checked = true;
    contain.disabled = true;
    containLabel.append(contain);
    element.replaceChildren(heading, grid, containLabel);
  };

  render();
  return {
    element,
    update: (next) => {
      if (disposed) return;
      state = next === null
        ? null
        : { ...next, layout: structuredClone(next.layout) };
      render();
    },
    dispose: () => {
      disposed = true;
      state = null;
      element.replaceChildren();
    },
  };
}
