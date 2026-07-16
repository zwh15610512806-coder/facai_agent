import { modelCapabilityConflicts, type ModelCapabilityRequirements, type ModelProfile } from "../domain/providers";

export interface ModelSelectorOptions {
  label: string;
  value: string | null;
  models: readonly ModelProfile[];
  disabled: boolean;
  requirements?: ModelCapabilityRequirements;
  onChange(modelId: string | null): void;
}

export function createModelSelector({ label, value, models, disabled, requirements, onChange }: ModelSelectorOptions): HTMLLabelElement {
  const field = document.createElement("label");
  field.className = "canvas-model-selector";
  field.textContent = label;
  const select = document.createElement("select");
  select.setAttribute("aria-label", label);
  select.disabled = disabled;
  select.append(Object.assign(document.createElement("option"), { value: "", textContent: "请选择模型" }));
  for (const model of models) {
    const option = document.createElement("option");
    option.value = model.id;
    option.textContent = model.availability === "available" && model.enabled
      ? model.displayName
      : `${model.displayName}（不可用）`;
    option.disabled = !model.enabled || model.availability !== "available";
    select.append(option);
  }
  select.value = value ?? "";
  select.addEventListener("change", () => onChange(select.value === "" ? null : select.value));
  field.append(select);
  const selected = value === null ? undefined : models.find((model) => model.id === value);
  if (selected !== undefined && requirements !== undefined) {
    const conflicts = modelCapabilityConflicts(selected, requirements);
    if (conflicts.length > 0) {
      const reason = document.createElement("small");
      reason.className = "canvas-model-selector-reason";
      reason.dataset.testid = "canvas-model-capability-reason";
      reason.textContent = conflicts.join("；");
      field.append(reason);
    }
  }
  return field;
}
