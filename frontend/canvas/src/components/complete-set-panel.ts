import type { ProjectSku } from "../api/client";
import { previewGenerationRequest } from "../domain/generation";
import type { ModelProfile } from "../domain/providers";
import type { CanvasProjectState, CompleteSetOutput, OutputType, ProjectAction } from "../domain/types";
import { createModelSelector } from "./model-selector";

type OutputConfigurationPatch = Extract<ProjectAction, { type: "output/configure" }>["patch"];

export interface CompleteSetPanelOptions {
  getProject(): CanvasProjectState;
  getRevision(): number;
  getModels(): readonly ModelProfile[];
  getSkus(): readonly ProjectSku[];
  getReferenceAssets(): readonly { id: string; label: string }[];
  isEditable(): boolean;
  dispatch(action: ProjectAction): void;
  onGenerate(): void;
}

export interface CompleteSetPanel {
  element: HTMLElement;
  update(): void;
}

const OUTPUTS: readonly OutputType[] = ["main", "sku", "detail"];
const LABELS: Record<OutputType, string> = { main: "主图", sku: "SKU 图", detail: "详情图" };

function ratio(width: number | null, height: number | null): string | null {
  if (width === null || height === null || width < 1 || height < 1) return null;
  const gcd = (left: number, right: number): number => right === 0 ? left : gcd(right, left % right);
  const divisor = gcd(width, height);
  return `${width / divisor}:${height / divisor}`;
}

function outputFor(project: CanvasProjectState, outputType: OutputType, skuId: string | null): CompleteSetOutput | null {
  return project.semanticState.completeSet.outputs.find(
    (output) => output.outputType === outputType && output.skuId === skuId,
  ) ?? null;
}

function selectField(
  label: string,
  value: string | null,
  options: readonly { id: string; label: string }[],
  disabled: boolean,
  onChange: (value: string | null) => void,
): HTMLLabelElement {
  const field = document.createElement("label");
  field.textContent = label;
  const select = document.createElement("select");
  select.setAttribute("aria-label", label);
  select.disabled = disabled;
  select.append(Object.assign(document.createElement("option"), { value: "", textContent: "自动使用产品图" }));
  for (const optionValue of options) {
    select.append(Object.assign(document.createElement("option"), { value: optionValue.id, textContent: optionValue.label }));
  }
  select.value = value ?? "";
  select.addEventListener("change", () => onChange(select.value || null));
  field.append(select);
  return field;
}

export function createCompleteSetPanel(options: CompleteSetPanelOptions): CompleteSetPanel {
  const element = document.createElement("section");
  element.className = "canvas-complete-set-panel";
  element.dataset.testid = "canvas-complete-set-panel";

  const renderOutput = (
    project: CanvasProjectState,
    outputType: OutputType,
    skuId: string | null,
    output: CompleteSetOutput | null,
  ): HTMLElement => {
    const fieldset = document.createElement("fieldset");
    fieldset.className = "canvas-output-control";
    const legend = document.createElement("legend");
    legend.textContent = skuId === null ? LABELS[outputType] : `${LABELS[outputType]} · ${options.getSkus().find((sku) => sku.id === skuId)?.name ?? skuId}`;
    fieldset.append(legend);
    const disabled = !options.isEditable();
    const selectedModel = output?.modelProfileId === null || output?.modelProfileId === undefined
      ? undefined
      : options.getModels().find((model) => model.id === output.modelProfileId);
    const quantity = document.createElement("input");
    quantity.type = "number";
    quantity.min = "1";
    quantity.max = String(Math.min(20, selectedModel?.capabilities.maxQuantity ?? 20));
    quantity.value = output?.quantity === null || output?.quantity === undefined ? "" : String(output.quantity);
    quantity.disabled = disabled;
    quantity.setAttribute("aria-label", `${legend.textContent}数量`);
    quantity.addEventListener("change", () => {
      const value = quantity.value === "" ? null : Number(quantity.value);
      if (value !== null && (!Number.isInteger(value) || value < 1 || value > 20)) return;
      options.dispatch(outputType === "sku"
        ? { type: "sku/setOutputQuantity", skuId: skuId as string, quantity: value }
        : { type: "output/setQuantity", outputType, quantity: value });
    });
    const quantityField = document.createElement("label");
    quantityField.textContent = "数量";
    quantityField.append(quantity);
    fieldset.append(quantityField);
    if (output === null) return fieldset;

    const configure = (patch: OutputConfigurationPatch): void => {
      options.dispatch({ type: "output/configure", outputType, skuId, patch });
    };
    fieldset.append(createModelSelector({
      label: `${legend.textContent}模型`, value: output.modelProfileId,
      models: options.getModels(), disabled,
      requirements: {
        width: output.width,
        height: output.height,
        quantity: output.quantity,
        referenceCount: 1,
        requiresMask: false,
      },
      onChange: (modelProfileId) => configure({ modelProfileId }),
    }));
    const prompt = document.createElement("textarea");
    prompt.value = output.prompt;
    prompt.disabled = disabled;
    prompt.setAttribute("aria-label", `${legend.textContent}提示词`);
    prompt.addEventListener("input", () => configure({ prompt: prompt.value }));
    const promptField = document.createElement("label");
    promptField.textContent = "提示词";
    promptField.append(prompt);
    fieldset.append(promptField);
    const dimension = (name: "width" | "height", label: string): HTMLLabelElement => {
      const field = document.createElement("label");
      field.textContent = label;
      const input = document.createElement("input");
      input.type = "number";
      const minimum = name === "width" ? selectedModel?.capabilities.minWidth : selectedModel?.capabilities.minHeight;
      const maximum = name === "width" ? selectedModel?.capabilities.maxWidth : selectedModel?.capabilities.maxHeight;
      input.min = String(minimum ?? 1);
      if (maximum !== null && maximum !== undefined) input.max = String(maximum);
      input.value = output[name] === null ? "" : String(output[name]);
      input.disabled = disabled;
      input.addEventListener("change", () => {
        const next = input.value === "" ? null : Number(input.value);
        const width = name === "width" ? next : output.width;
        const height = name === "height" ? next : output.height;
        configure({ width, height, aspectRatio: ratio(width, height) });
      });
      field.append(input);
      return field;
    };
    fieldset.append(dimension("width", "宽"), dimension("height", "高"));
    const groupOptions = project.semanticState.compositionGroups.map((group) => ({ id: group.id, label: group.id }));
    const referenceUnsupported = selectedModel !== undefined && (
      !selectedModel.capabilities.imageToImage
      || selectedModel.capabilities.maxReferenceImages < 1
      || selectedModel.capabilities.referenceTransfer === "none"
    );
    fieldset.append(
      selectField("产品参考图", output.referenceAssetId, options.getReferenceAssets(), disabled || referenceUnsupported, (referenceAssetId) => configure({ referenceAssetId })),
      selectField("构图组", output.compositionGroupId, groupOptions, disabled, (compositionGroupId) => configure({ compositionGroupId })),
    );
    return fieldset;
  };

  const update = (): void => {
    const project = options.getProject();
    const selected = new Set(project.semanticState.completeSet.selectedOutputTypes);
    const heading = document.createElement("h2");
    heading.textContent = "套图生成";
    const choose = document.createElement("p");
    choose.textContent = "按需选择主图、SKU 图和详情图；未选择时不会生成。";
    const selector = document.createElement("div");
    selector.className = "canvas-output-type-selector";
    for (const outputType of OUTPUTS) {
      const enabled = document.createElement("input");
      enabled.type = "checkbox";
      enabled.checked = selected.has(outputType);
      enabled.setAttribute("aria-label", `启用${LABELS[outputType]}`);
      enabled.disabled = !options.isEditable();
      enabled.addEventListener("change", () => options.dispatch({
        type: enabled.checked ? "output/enable" : "output/disable", outputType,
      }));
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.testid = `canvas-output-${outputType}`;
      button.dataset.selected = String(selected.has(outputType));
      button.setAttribute("aria-pressed", String(selected.has(outputType)));
      button.disabled = !options.isEditable();
      button.textContent = selected.has(outputType) ? `已选${LABELS[outputType]}` : `选择${LABELS[outputType]}`;
      button.addEventListener("click", () => {
        enabled.checked = !enabled.checked;
        enabled.dispatchEvent(new Event("change", { bubbles: true }));
      });
      const choice = document.createElement("label");
      choice.className = "canvas-output-choice";
      choice.append(enabled, button);
      selector.append(choice);
    }
    const form = document.createElement("div");
    form.className = "canvas-complete-set-form";
    for (const outputType of ["main", "detail"] as const) {
      if (selected.has(outputType)) form.append(renderOutput(project, outputType, null, outputFor(project, outputType, null)));
    }
    if (selected.has("sku")) {
      const skus = options.getSkus();
      if (skus.length === 0) form.append(Object.assign(document.createElement("p"), { textContent: "请先新增 SKU，再设置 SKU 图数量。" }));
      for (const sku of skus) form.append(renderOutput(project, "sku", sku.id, outputFor(project, "sku", sku.id)));
    }
    const allModels = options.getModels().filter((model) => model.enabled && model.availability === "available");
    const applyRow = document.createElement("div");
    const applySelect = document.createElement("select");
    applySelect.append(Object.assign(document.createElement("option"), { value: "", textContent: "应用同一模型到全部已选类型" }));
    for (const model of allModels) applySelect.append(Object.assign(document.createElement("option"), { value: model.id, textContent: model.displayName }));
    const apply = document.createElement("button");
    apply.type = "button";
    apply.textContent = "确认应用";
    apply.disabled = !options.isEditable();
    apply.addEventListener("click", () => {
      if (applySelect.value === "" || !window.confirm("将覆盖已选输出的模型选择，是否继续？")) return;
      for (const output of project.semanticState.completeSet.outputs) {
        if (selected.has(output.outputType)) {
          options.dispatch({ type: "output/configure", outputType: output.outputType, skuId: output.skuId, patch: { modelProfileId: applySelect.value } });
        }
      }
    });
    applyRow.append(applySelect, apply);
    const outputs = project.semanticState.completeSet.outputs.filter((output) => selected.has(output.outputType));
    const count = outputs.reduce((total, output) => total + (output.quantity ?? 0), 0);
    const total = document.createElement("p");
    total.dataset.testid = "canvas-generation-item-count";
    total.textContent = `实际生成数量：${count}`;
    const prices = outputs.map((output) => options.getModels().find((model) => model.id === output.modelProfileId)?.priceMetadata?.amount);
    if (prices.length > 0 && prices.every((price) => typeof price === "number")) {
      const estimate = prices.reduce((sum, price, index) => sum + (price as number) * (outputs[index]?.quantity ?? 0), 0);
      total.textContent += `；预估价格：${estimate}`;
    }
    const projection = previewGenerationRequest(project, [...options.getModels()], options.getRevision());
    const validation = document.createElement("p");
    validation.dataset.testid = "canvas-generation-validation";
    validation.textContent = projection.ok ? "生成配置已就绪" : projection.reasons.map((reason) => reason.message).join("；");
    const generate = document.createElement("button");
    generate.type = "button";
    generate.dataset.testid = "canvas-generate";
    generate.textContent = "生成已选套图";
    generate.disabled = !options.isEditable() || !projection.ok;
    generate.addEventListener("click", () => options.onGenerate());
    element.replaceChildren(heading, choose, selector, form, applyRow, total, validation, generate);
  };
  update();
  return { element, update };
}
