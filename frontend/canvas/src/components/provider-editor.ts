import type { ProviderManagementApi } from "../api/providers";
import { PROVIDER_ADAPTER_CHOICES } from "../domain/providers";
import { canvasUserMessage } from "../domain/user-message";

export interface ProviderEditorOptions {
  api: Pick<ProviderManagementApi, "createProvider">;
  onSaved(): void;
  onUnauthorized(retry: () => void): void;
  onUnconfigured(): void;
}

export interface ProviderEditor {
  element: HTMLElement;
  clear(): void;
}

/**
 * Credential input exists only in this component. It is never populated from a
 * GET response and is cleared after a successful save/cancel/non-retryable error.
 */
export function createProviderEditor(options: ProviderEditorOptions): ProviderEditor {
  const element = document.createElement("section");
  element.className = "canvas-provider-editor";
  element.dataset.testid = "canvas-provider-editor";
  const heading = document.createElement("h3");
  heading.textContent = "添加第三方图像提供方";
  const form = document.createElement("form");
  const adapter = document.createElement("select");
  adapter.setAttribute("aria-label", "提供方协议");
  for (const choice of PROVIDER_ADAPTER_CHOICES.filter((choice) => !choice.builtIn)) {
    adapter.append(Object.assign(document.createElement("option"), { value: choice.type, textContent: choice.label }));
  }
  const namedInput = (label: string, type = "text"): HTMLInputElement => {
    const field = document.createElement("label");
    field.textContent = label;
    const input = document.createElement("input");
    input.type = type;
    input.required = type !== "password";
    input.setAttribute("aria-label", label);
    field.append(input);
    form.append(field);
    return input;
  };
  const adapterField = document.createElement("label");
  adapterField.textContent = "提供方协议";
  adapterField.append(adapter);
  form.append(adapterField);
  const name = namedInput("提供方名称");
  const baseUrl = namedInput("服务地址", "url");
  const auth = document.createElement("select");
  auth.setAttribute("aria-label", "鉴权方式");
  for (const [value, label] of [["bearer", "Bearer"], ["api_key", "API Key"], ["none", "无需鉴权"]] as const) {
    auth.append(Object.assign(document.createElement("option"), { value, textContent: label }));
  }
  const authField = document.createElement("label");
  authField.textContent = "鉴权方式";
  authField.append(auth);
  form.append(authField);
  const secret = namedInput("API 密钥", "password");
  secret.autocomplete = "off";
  const credentialHint = namedInput("密钥说明");
  credentialHint.required = false;
  const feedback = document.createElement("p");
  feedback.dataset.testid = "canvas-provider-editor-feedback";
  const save = document.createElement("button");
  save.type = "submit";
  save.textContent = "安全保存提供方";
  const cancel = document.createElement("button");
  cancel.type = "button";
  cancel.textContent = "取消";
  form.append(feedback, save, cancel);
  element.append(heading, form);

  const clear = (): void => {
    form.reset();
    secret.value = "";
    feedback.textContent = "";
  };
  const submit = (): void => {
    const authType = auth.value as "bearer" | "api_key" | "none";
    if (!form.reportValidity()) return;
    if (authType !== "none" && secret.value === "") {
      feedback.textContent = "请填写仅用于本次保存的 API 密钥";
      return;
    }
    save.disabled = true;
    const payload = {
      adapterType: adapter.value as "openai_images" | "declarative_http",
      name: name.value.trim(), baseUrl: baseUrl.value.trim(), authType,
      ...(authType === "none" ? {} : { credential: { apiKey: secret.value } }),
      ...(credentialHint.value.trim() === "" ? {} : { credentialHint: credentialHint.value.trim() }),
    };
    void options.api.createProvider(payload).then((result) => {
      save.disabled = false;
      if (result.ok) {
        clear();
        options.onSaved();
        return;
      }
      if (result.kind === "unauthorized") {
        feedback.textContent = "请解锁后立即重试；密钥只保留在当前表单内存中";
        options.onUnauthorized(submit);
        return;
      }
      if (result.kind === "unconfigured") {
        feedback.textContent = canvasUserMessage(result.message, "供应商保存失败，请重试");
        options.onUnconfigured();
        return;
      }
      feedback.textContent = canvasUserMessage(result.message, "供应商保存失败，请重试");
      if (result.kind === "validation") secret.value = "";
    }).catch(() => {
      save.disabled = false;
      feedback.textContent = "保存请求失败，请重试";
    });
  };
  form.addEventListener("submit", (event) => { event.preventDefault(); submit(); });
  cancel.addEventListener("click", clear);
  auth.addEventListener("change", () => {
    secret.disabled = auth.value === "none";
    secret.required = auth.value !== "none";
    if (secret.disabled) secret.value = "";
  });
  return { element, clear };
}
