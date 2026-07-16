import type { ProviderManagementApi, ProvidersApi } from "../api/providers";
import type { ModelProfile, ProviderProfile } from "../domain/providers";
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
  const title = document.createElement("h2"); title.textContent = "第三方模型管理";
  const notice = document.createElement("p"); notice.textContent = "密钥仅写入受保护接口，不会从目录返回或显示。ComfyUI 与本地权重不在此版本支持范围内。";
  const feedback = document.createElement("p"); feedback.dataset.testid = "canvas-model-manager-feedback";
  const providerList = document.createElement("div");
  const providerChoice = document.createElement("select"); providerChoice.setAttribute("aria-label", "模型所属提供方");
  const modelList = document.createElement("div");
  let providers: ProviderProfile[] = [];
  let models: ModelProfile[] = [];
  const refresh = (): void => {
    void Promise.all([
      options.managementApi.loadProviders(),
      options.catalogApi.loadCatalog(),
    ]).then(([providerResult, modelResult]) => {
      if (!providerResult.ok) { feedback.textContent = providerResult.message; return; }
      if (!modelResult.ok) { feedback.textContent = modelResult.message; return; }
      providers = providerResult.value;
      models = modelResult.value;
      providerChoice.replaceChildren(Object.assign(document.createElement("option"), { value: "", textContent: "选择提供方以添加模型" }), ...providers.map((provider) => Object.assign(document.createElement("option"), { value: provider.id, textContent: provider.name })));
      providerList.replaceChildren(...providers.map((provider) => {
        const row = document.createElement("p");
        const count = models.filter((model) => model.providerId === provider.id).length;
        row.textContent = `${provider.name}：${count} 个模型`;
        const probe = document.createElement("button"); probe.type = "button"; probe.textContent = "检测连接";
        probe.addEventListener("click", () => {
          if (!window.confirm("本次检测将发送 1 次可能计费的提供方请求；具体费用由供应商计费规则决定。是否继续？")) return;
          void options.managementApi.probeProvider(provider.id, true).then((response) => {
            if (response.ok) { feedback.textContent = response.value.status === "configuration_ready" ? "连接配置已就绪" : "连接当前不可用"; return; }
            if (response.kind === "unauthorized") { options.onUnauthorized(() => probe.click()); return; }
            if (response.kind === "unconfigured") options.onUnconfigured();
            feedback.textContent = response.message;
          });
        });
        row.append(" ", probe); return row;
      }));
      modelList.replaceChildren(...models.map((model) => Object.assign(document.createElement("p"), { textContent: `${model.displayName} · ${model.availability === "available" && model.enabled ? "可用" : model.availabilityReason ?? "不可用"}` })));
      options.onCatalog(models);
    }).catch(() => { feedback.textContent = "模型目录加载失败"; });
  };
  const providerEditor = createProviderEditor({ api: options.managementApi, onSaved: refresh, onUnauthorized: options.onUnauthorized, onUnconfigured: options.onUnconfigured });
  const modelEditor = createModelProfileEditor({ api: options.managementApi, providerId: () => providerChoice.value || null, onSaved: refresh, onUnauthorized: options.onUnauthorized, onUnconfigured: options.onUnconfigured });
  element.append(title, notice, providerEditor.element, providerChoice, modelEditor.element, feedback, providerList, modelList);
  refresh();
  return { element, refresh, clearSensitive: providerEditor.clear };
}
