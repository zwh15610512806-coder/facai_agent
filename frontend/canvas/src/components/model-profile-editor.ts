import type { ModelProfileCreateRequest, ProviderManagementApi } from "../api/providers";
import { canvasUserMessage } from "../domain/user-message";

export interface ModelProfileEditorOptions {
  api: Pick<ProviderManagementApi, "createModelProfile">;
  providerId(): string | null;
  onSaved(): void;
  onUnauthorized(retry: () => void): void;
  onUnconfigured(): void;
}

export interface ModelProfileEditor { element: HTMLElement; }

const DEFAULT_CAPABILITIES = {
  text_to_image: true, image_to_image: true, mask_edit: false, allowed_ratios: [], allowed_sizes: [],
  min_width: null, max_width: null, min_height: null, max_height: null, max_quantity: 1,
  max_reference_images: 1, reference_transfer: "bytes", protocol: "sync", supports_cancel: false,
  supports_idempotency: true, supports_idempotency_lookup: false, concurrency_limit: 1, price_metadata: null,
};

export function createModelProfileEditor(options: ModelProfileEditorOptions): ModelProfileEditor {
  const element = document.createElement("section");
  element.className = "canvas-model-profile-editor";
  element.dataset.testid = "canvas-model-profile-editor";
  const heading = document.createElement("h3");
  heading.textContent = "添加图像模型";
  const form = document.createElement("form");
  const basics = document.createElement("div");
  basics.className = "canvas-model-basic-fields";
  const field = (label: string, control: HTMLElement, target = basics): void => {
    const wrapper = document.createElement("label");
    wrapper.textContent = label;
    wrapper.append(control);
    target.append(wrapper);
  };
  const textInput = (label: string): HTMLInputElement => {
    const control = document.createElement("input");
    control.required = true;
    control.setAttribute("aria-label", label);
    field(label, control);
    return control;
  };
  const modelId = textInput("模型 ID / Endpoint ID");
  const displayName = textInput("模型显示名称");

  const capabilityFields = document.createElement("fieldset");
  capabilityFields.className = "canvas-model-capability-fields";
  capabilityFields.append(Object.assign(document.createElement("legend"), { textContent: "常用模型能力" }));
  const checkbox = (label: string, checked: boolean): HTMLInputElement => {
    const wrapper = document.createElement("label");
    const control = document.createElement("input");
    control.type = "checkbox";
    control.checked = checked;
    wrapper.append(control, label);
    capabilityFields.append(wrapper);
    return control;
  };
  const textToImage = checkbox("支持文生图", true);
  const imageToImage = checkbox("支持参考图生成", true);
  const maskEdit = checkbox("支持蒙版编辑", false);
  const supportsCancel = checkbox("支持取消任务", false);
  const supportsIdempotency = checkbox("支持幂等请求", true);
  const supportsLookup = checkbox("支持幂等查询", false);

  const capabilityGrid = document.createElement("div");
  capabilityGrid.className = "canvas-model-capability-grid";
  const numberInput = (label: string, value: number, minimum: number): HTMLInputElement => {
    const control = document.createElement("input");
    control.type = "number";
    control.min = String(minimum);
    control.value = String(value);
    field(label, control, capabilityGrid);
    return control;
  };
  const maxQuantity = numberInput("单次最大数量", 1, 1);
  const maxReferences = numberInput("最大参考图数量", 1, 0);
  const concurrency = numberInput("并发限制", 1, 1);
  const ratioInput = document.createElement("input");
  ratioInput.placeholder = "例如 1:1, 3:4, 16:9";
  field("支持比例（逗号分隔）", ratioInput, capabilityGrid);
  const sizeInput = document.createElement("input");
  sizeInput.placeholder = "例如 1024x1024, 1440x1920";
  field("支持尺寸（逗号分隔）", sizeInput, capabilityGrid);
  const transfer = document.createElement("select");
  for (const [value, label] of [["bytes", "文件字节"], ["base64", "Base64"], ["public_url", "公网 URL"], ["none", "不支持参考图"]] as const) {
    transfer.append(Object.assign(document.createElement("option"), { value, textContent: label }));
  }
  field("参考图传输方式", transfer, capabilityGrid);
  const protocol = document.createElement("select");
  for (const [value, label] of [["sync", "同步"], ["async", "异步"], ["both", "同步与异步"]] as const) {
    protocol.append(Object.assign(document.createElement("option"), { value, textContent: label }));
  }
  field("任务协议", protocol, capabilityGrid);

  const advanced = document.createElement("details");
  advanced.className = "canvas-model-advanced";
  advanced.append(Object.assign(document.createElement("summary"), { textContent: "高级 JSON 配置" }));
  const advancedHint = document.createElement("p");
  advancedHint.textContent = "仅在供应商需要特殊能力或协议字段时展开。启用能力覆盖后，将使用下方完整 JSON。";
  const advancedToggle = document.createElement("input");
  advancedToggle.type = "checkbox";
  const advancedToggleLabel = document.createElement("label");
  advancedToggleLabel.append(advancedToggle, "使用高级能力 JSON 覆盖上方字段");
  const capabilities = document.createElement("textarea");
  capabilities.setAttribute("aria-label", "高级模型能力 JSON");
  capabilities.value = JSON.stringify(DEFAULT_CAPABILITIES, null, 2);
  const capabilitiesField = document.createElement("label");
  capabilitiesField.textContent = "完整能力 JSON";
  capabilitiesField.append(capabilities);
  const config = document.createElement("textarea");
  config.setAttribute("aria-label", "协议配置 JSON");
  config.value = "{}";
  const configField = document.createElement("label");
  configField.textContent = "协议配置 JSON";
  configField.append(config);
  advanced.append(advancedHint, advancedToggleLabel, capabilitiesField, configField);

  const feedback = document.createElement("p"); feedback.dataset.testid = "canvas-model-profile-feedback";
  feedback.setAttribute("role", "status");
  const save = document.createElement("button"); save.type = "submit"; save.textContent = "保存模型配置";
  form.append(basics, capabilityFields, capabilityGrid, advanced, feedback, save);
  element.append(heading, form);
  const csv = (value: string): string[] => value.split(",").map((item) => item.trim()).filter(Boolean);
  const structuredCapabilities = (): Record<string, unknown> => ({
    ...DEFAULT_CAPABILITIES,
    text_to_image: textToImage.checked,
    image_to_image: imageToImage.checked,
    mask_edit: maskEdit.checked,
    allowed_ratios: csv(ratioInput.value),
    allowed_sizes: csv(sizeInput.value),
    max_quantity: Number(maxQuantity.value),
    max_reference_images: Number(maxReferences.value),
    reference_transfer: transfer.value,
    protocol: protocol.value,
    supports_cancel: supportsCancel.checked,
    supports_idempotency: supportsIdempotency.checked,
    supports_idempotency_lookup: supportsLookup.checked,
    concurrency_limit: Number(concurrency.value),
  });
  const submit = (): void => {
    const providerId = options.providerId();
    if (providerId === null) { feedback.textContent = "请先选择一个第三方提供方"; return; }
    let payload: ModelProfileCreateRequest;
    try {
      const cap = advancedToggle.checked
        ? JSON.parse(capabilities.value) as unknown
        : structuredCapabilities();
      const settings = JSON.parse(config.value) as unknown;
      if (typeof cap !== "object" || cap === null || Array.isArray(cap) || typeof settings !== "object" || settings === null || Array.isArray(settings)) throw new Error();
      payload = { modelId: modelId.value.trim(), displayName: displayName.value.trim(), capabilities: cap as Record<string, unknown>, config: settings as Record<string, unknown> };
    } catch { feedback.textContent = "高级模型能力和协议配置必须是 JSON 对象"; return; }
    if (!form.reportValidity()) return;
    save.disabled = true;
    void options.api.createModelProfile(providerId, payload).then((result) => {
      save.disabled = false;
      if (result.ok) {
        form.reset();
        textToImage.checked = true;
        imageToImage.checked = true;
        supportsIdempotency.checked = true;
        maxQuantity.value = "1";
        maxReferences.value = "1";
        concurrency.value = "1";
        capabilities.value = JSON.stringify(DEFAULT_CAPABILITIES, null, 2);
        config.value = "{}";
        feedback.textContent = "";
        options.onSaved();
        return;
      }
      if (result.kind === "unauthorized") { feedback.textContent = "请解锁后立即重试"; options.onUnauthorized(submit); return; }
      if (result.kind === "unconfigured") { feedback.textContent = canvasUserMessage(result.message, "请先解锁图像模型管理"); options.onUnconfigured(); return; }
      feedback.textContent = canvasUserMessage(result.message, "模型档案保存失败，请重试");
    }).catch(() => { save.disabled = false; feedback.textContent = "保存请求失败，请重试"; });
  };
  form.addEventListener("submit", (event) => { event.preventDefault(); submit(); });
  return { element };
}
