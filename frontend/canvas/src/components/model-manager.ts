import type { ProviderManagementApi, ProvidersApi } from "../api/providers";
import type { ModelProfile, ProviderProfile } from "../domain/providers";
import { canvasUserMessage } from "../domain/user-message";
import { createModelProfileEditor } from "./model-profile-editor";
import { createProviderEditor } from "./provider-editor";

export interface ModelManagerOptions {
  catalogApi: ProvidersApi;
  managementApi: ProviderManagementApi;
  onUnauthorized(retry: () => void): void;
  onUnconfigured(): void;
  onCatalog(models: ModelProfile[]): void;
}

export interface ModelManager { element: HTMLElement; refresh(): void; clearSensitive(): void; }

export function createModelManager(options: ModelManagerOptions): ModelManager {
  const element = document.createElement("section");
  element.className = "canvas-model-manager";
  element.dataset.testid = "canvas-model-manager";
  const title = document.createElement("h2"); title.textContent = "图像生成模型";
  const notice = document.createElement("p");
  notice.className = "canvas-model-manager-notice";
  notice.textContent = "在这里统一管理 Seedream 与第三方图像模型。密钥只会写入受保护接口，不会从目录返回或显示。";
  const feedback = document.createElement("p");
  feedback.dataset.testid = "canvas-model-manager-feedback";
  feedback.setAttribute("role", "status");
  feedback.setAttribute("aria-live", "polite");
  const providerList = document.createElement("div");
  providerList.className = "canvas-provider-list";
  const providerChoice = document.createElement("select"); providerChoice.setAttribute("aria-label", "模型所属提供方");
  const providerChoiceField = document.createElement("label");
  providerChoiceField.className = "canvas-provider-choice";
  providerChoiceField.textContent = "添加模型到提供方";
  providerChoiceField.append(providerChoice);
  const modelList = document.createElement("div");
  modelList.className = "canvas-model-list";
  let providers: ProviderProfile[] = [];
  let models: ModelProfile[] = [];
  const refresh = (): void => {
    void Promise.all([
      options.managementApi.loadProviders(),
      options.catalogApi.loadCatalog(),
    ]).then(([providerResult, modelResult]) => {
      if (!providerResult.ok) { feedback.textContent = canvasUserMessage(providerResult.message, "图像供应商加载失败，请重试"); return; }
      if (!modelResult.ok) { feedback.textContent = canvasUserMessage(modelResult.message, "图像模型加载失败，请重试"); return; }
      providers = providerResult.value;
      models = modelResult.value;
      providerChoice.replaceChildren(Object.assign(document.createElement("option"), { value: "", textContent: "选择提供方以添加模型" }), ...providers.map((provider) => Object.assign(document.createElement("option"), { value: provider.id, textContent: provider.name })));
      providerList.replaceChildren(...providers.map((provider) => {
        const row = document.createElement("article");
        row.className = "canvas-provider-row";
        const count = models.filter((model) => model.providerId === provider.id).length;
        const info = document.createElement("div");
        info.innerHTML = "<strong></strong><span></span>";
        info.querySelector("strong")!.textContent = provider.name;
        info.querySelector("span")!.textContent = `${count} 个模型 · ${provider.enabled ? "已启用" : "已停用"}`;
        const probe = document.createElement("button"); probe.type = "button"; probe.textContent = "检测连接";
        probe.addEventListener("click", () => {
          if (!window.confirm("本次检测将发送 1 次可能计费的提供方请求；具体费用由供应商计费规则决定。是否继续？")) return;
          void options.managementApi.probeProvider(provider.id, true).then((response) => {
            if (response.ok) { feedback.textContent = response.value.status === "configuration_ready" ? "连接配置已就绪" : "连接当前不可用"; return; }
            if (response.kind === "unauthorized") { options.onUnauthorized(() => probe.click()); return; }
            if (response.kind === "unconfigured") options.onUnconfigured();
            feedback.textContent = canvasUserMessage(response.message, "连通性测试失败，请检查配置");
          });
        });
        row.append(info, probe); return row;
      }));
      modelList.replaceChildren(...models.map((model) => {
        const row = document.createElement("article");
        row.className = "canvas-model-row";
        row.innerHTML = "<strong></strong><span></span>";
        row.querySelector("strong")!.textContent = model.displayName;
        const availabilityLabel = model.availability === "available" && model.enabled
          ? "可用"
          : canvasUserMessage(model.availabilityReason, "不可用");
        row.querySelector("span")!.textContent = `${model.modelId} · ${availabilityLabel}`;
        return row;
      }));
      options.onCatalog(models);
    }).catch(() => { feedback.textContent = "模型目录加载失败"; });
  };
  const providerEditor = createProviderEditor({ api: options.managementApi, onSaved: refresh, onUnauthorized: options.onUnauthorized, onUnconfigured: options.onUnconfigured });
  const modelEditor = createModelProfileEditor({ api: options.managementApi, providerId: () => providerChoice.value || null, onSaved: refresh, onUnauthorized: options.onUnauthorized, onUnconfigured: options.onUnconfigured });
  element.append(title, notice, providerList, providerEditor.element, providerChoiceField, modelEditor.element, feedback, modelList);
  refresh();
  return { element, refresh, clearSensitive: providerEditor.clear };
}
