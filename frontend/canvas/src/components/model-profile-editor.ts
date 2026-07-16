import type { ModelProfileCreateRequest, ProviderManagementApi } from "../api/providers";

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
  heading.textContent = "添加模型能力配置";
  const form = document.createElement("form");
  const input = (label: string): HTMLInputElement => {
    const field = document.createElement("label"); field.textContent = label;
    const control = document.createElement("input"); control.required = true; control.setAttribute("aria-label", label);
    field.append(control); form.append(field); return control;
  };
  const modelId = input("模型 ID");
  const displayName = input("模型显示名称");
  const area = (label: string, value: object): HTMLTextAreaElement => {
    const field = document.createElement("label"); field.textContent = label;
    const control = document.createElement("textarea"); control.setAttribute("aria-label", label); control.value = JSON.stringify(value, null, 2);
    field.append(control); form.append(field); return control;
  };
  const capabilities = area("模型能力 JSON", DEFAULT_CAPABILITIES);
  const config = area("协议配置 JSON", {});
  const feedback = document.createElement("p"); feedback.dataset.testid = "canvas-model-profile-feedback";
  const save = document.createElement("button"); save.type = "submit"; save.textContent = "保存模型配置";
  form.append(feedback, save); element.append(heading, form);
  const submit = (): void => {
    const providerId = options.providerId();
    if (providerId === null) { feedback.textContent = "请先选择一个第三方提供方"; return; }
    let payload: ModelProfileCreateRequest;
    try {
      const cap = JSON.parse(capabilities.value) as unknown;
      const settings = JSON.parse(config.value) as unknown;
      if (typeof cap !== "object" || cap === null || Array.isArray(cap) || typeof settings !== "object" || settings === null || Array.isArray(settings)) throw new Error();
      payload = { modelId: modelId.value.trim(), displayName: displayName.value.trim(), capabilities: cap as Record<string, unknown>, config: settings as Record<string, unknown> };
    } catch { feedback.textContent = "模型能力和协议配置必须是 JSON 对象"; return; }
    if (!form.reportValidity()) return;
    save.disabled = true;
    void options.api.createModelProfile(providerId, payload).then((result) => {
      save.disabled = false;
      if (result.ok) { form.reset(); capabilities.value = JSON.stringify(DEFAULT_CAPABILITIES, null, 2); config.value = "{}"; feedback.textContent = ""; options.onSaved(); return; }
      if (result.kind === "unauthorized") { feedback.textContent = "请解锁后立即重试"; options.onUnauthorized(submit); return; }
      if (result.kind === "unconfigured") { feedback.textContent = result.message; options.onUnconfigured(); return; }
      feedback.textContent = result.message;
    }).catch(() => { save.disabled = false; feedback.textContent = "保存请求失败，请重试"; });
  };
  form.addEventListener("submit", (event) => { event.preventDefault(); submit(); });
  return { element };
}
