import type { TextLayerPatch, TextLineSnapshot, TextSnapshot } from "../domain/types";
import {
  patchTextContentWithoutReflow,
  patchTextLineHeight,
} from "../domain/text-layout";
import { canvasUserMessage } from "../domain/user-message";

export interface TextInspectorState {
  layers: TextSnapshot[];
  selectedLayerId: string | null;
  disabled: boolean;
}

export interface TextInspectorOptions {
  onSelect?(layerId: string | null): void;
  onUpdate(layerId: string, patch: TextLayerPatch): void;
}

export interface TextInspector {
  element: HTMLElement;
  update(state: TextInspectorState): void;
  dispose(): void;
}

function inputField(
  testid: string,
  value: string,
  disabled: boolean,
  onChange: (value: string) => void,
  type = "text",
): HTMLInputElement {
  const input = document.createElement("input");
  input.type = type;
  input.value = value;
  input.disabled = disabled;
  input.dataset.testid = testid;
  input.addEventListener("change", () => onChange(input.value));
  return input;
}

export function createTextInspector({ onSelect, onUpdate }: TextInspectorOptions): TextInspector {
  let state: TextInspectorState = { layers: [], selectedLayerId: null, disabled: true };
  let disposed = false;
  const element = document.createElement("section");
  element.className = "canvas-text-inspector";
  element.dataset.testid = "canvas-text-inspector";

  const render = (): void => {
    const heading = document.createElement("h3");
    heading.textContent = "文字图层";
    const selector = document.createElement("select");
    selector.dataset.testid = "canvas-text-layer-select";
    selector.disabled = state.disabled || state.layers.length === 0;
    selector.append(
      ...state.layers.map((layer, index) => Object.assign(document.createElement("option"), {
        value: layer.id,
        textContent: `${index + 1}. ${layer.content || layer.id}`,
      })),
    );
    const selected = state.layers.find((layer) => layer.id === state.selectedLayerId)
      ?? state.layers[0]
      ?? null;
    selector.value = selected?.id ?? "";
    selector.addEventListener("change", () => onSelect?.(selector.value || null));
    if (selected === null) {
      const empty = document.createElement("p");
      empty.textContent = "暂无文字图层";
      element.replaceChildren(heading, selector, empty);
      return;
    }
    const form = document.createElement("div");
    form.className = "canvas-text-fields";
    const add = (labelText: string, control: HTMLElement): void => {
      const label = document.createElement("label");
      label.append(labelText, control);
      form.append(label);
    };
    const content = document.createElement("textarea");
    content.value = selected.content;
    content.disabled = state.disabled;
    content.dataset.testid = "canvas-text-content";
    const contentFeedback = document.createElement("p");
    contentFeedback.className = "canvas-text-feedback";
    contentFeedback.dataset.testid = "canvas-text-content-feedback";
    contentFeedback.setAttribute("role", "alert");
    content.addEventListener("change", () => {
      try {
        onUpdate(selected.id, patchTextContentWithoutReflow(selected, content.value));
        contentFeedback.textContent = "";
      } catch (error) {
        content.value = selected.content;
        contentFeedback.textContent = canvasUserMessage(
          error instanceof Error ? error.message : null,
          "文字内容更新失败",
        );
      }
    });
    add("内容", content);
    form.append(contentFeedback);
    const numeric = (
      label: string,
      testid: string,
      value: number,
      field: keyof TextLayerPatch,
    ): void => add(label, inputField(testid, String(value), state.disabled, (raw) => {
      const parsed = Number(raw);
      if (Number.isFinite(parsed)) onUpdate(selected.id, { [field]: parsed });
    }, "number"));
    numeric("文本框宽度", "canvas-text-box-width", selected.boxWidth, "boxWidth");
    const fontSize = inputField(
      "canvas-text-font-size",
      String(selected.fontSize),
      state.disabled,
      (raw) => {
        const parsed = Number(raw);
        if (Number.isInteger(parsed) && parsed > 0) {
          onUpdate(selected.id, { fontSize: parsed });
        }
      },
      "number",
    );
    fontSize.min = "1";
    fontSize.max = "10000";
    fontSize.step = "1";
    add("字号", fontSize);
    add("颜色", inputField("canvas-text-color", selected.color, state.disabled, (value) => {
      onUpdate(selected.id, { color: value });
    }, "color"));
    numeric("字间距", "canvas-text-letter-spacing", selected.letterSpacing, "letterSpacing");
    add("行距", inputField(
      "canvas-text-line-height",
      String(selected.lineHeight),
      state.disabled,
      (raw) => {
        const parsed = Number(raw);
        if (Number.isFinite(parsed) && parsed > 0) {
          onUpdate(selected.id, patchTextLineHeight(selected, parsed));
        }
      },
      "number",
    ));
    const selectField = <Value extends string>(
      label: string,
      testid: string,
      value: Value,
      values: readonly Value[],
      patch: (value: Value) => TextLayerPatch,
    ): void => {
      const select = document.createElement("select");
      select.dataset.testid = testid;
      select.disabled = state.disabled;
      select.append(...values.map((candidate) => Object.assign(document.createElement("option"), {
        value: candidate,
        textContent: candidate,
      })));
      select.value = value;
      select.addEventListener("change", () => onUpdate(selected.id, patch(select.value as Value)));
      add(label, select);
    };
    selectField("对齐", "canvas-text-align", selected.align, ["left", "center", "right"],
      (align) => ({ align }));
    selectField("基线", "canvas-text-baseline", selected.baseline,
      ["alphabetic", "top", "middle", "bottom"], (baseline) => ({ baseline }));
    selectField("层级", "canvas-text-z-band", selected.zBand,
      ["below-product", "above-product"], (zBand) => ({ zBand }));
    const lines = document.createElement("div");
    lines.className = "canvas-text-lines";
    selected.lines.forEach((line, index) => {
      const row = document.createElement("fieldset");
      const updateLine = (patch: Partial<TextLineSnapshot>): void => {
        const next = selected.lines.map((candidate, candidateIndex) =>
          candidateIndex === index ? { ...candidate, ...patch } : { ...candidate });
        onUpdate(selected.id, { lines: next });
      };
      row.append(
        inputField(`canvas-text-line-text-${index}`, line.text, state.disabled,
          (text) => updateLine({ text })),
        inputField(`canvas-text-line-x-${index}`, String(line.x), state.disabled,
          (raw) => { const value = Number(raw); if (Number.isFinite(value)) updateLine({ x: value }); }, "number"),
        inputField(`canvas-text-line-y-${index}`, String(line.y), state.disabled,
          (raw) => { const value = Number(raw); if (Number.isFinite(value)) updateLine({ y: value }); }, "number"),
        inputField(`canvas-text-line-width-${index}`, String(line.width), state.disabled,
          (raw) => { const value = Number(raw); if (Number.isFinite(value)) updateLine({ width: value }); }, "number"),
      );
      lines.append(row);
    });
    form.append(lines);
    element.replaceChildren(heading, selector, form);
  };
  render();
  return {
    element,
    update: (next) => {
      if (disposed) return;
      state = structuredClone(next);
      render();
    },
    dispose: () => {
      disposed = true;
      element.replaceChildren();
    },
  };
}
