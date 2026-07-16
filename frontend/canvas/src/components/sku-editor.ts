import type {
  ProjectSku,
  ProjectSnapshot,
  SaveResult,
} from "../api/client";
import type { SkusApi, SkuUpdatePatch } from "../api/skus";

export interface SkuReferenceOption {
  id: string;
  label: string;
}

export interface SkuEditorState {
  projectId: string;
  revision: number;
  skus: ProjectSku[];
  mainProductAssetId: string | null;
  referenceAssets: SkuReferenceOption[];
  disabled: boolean;
}

export interface SkuEditorOptions {
  api: SkusApi;
  onSnapshot(snapshot: ProjectSnapshot): void;
}

export interface SkuEditor {
  element: HTMLElement;
  update(state: SkuEditorState | null): void;
  dispose(): void;
}

export function createSkuEditor({ api, onSnapshot }: SkuEditorOptions): SkuEditor {
  let state: SkuEditorState | null = null;
  let disposed = false;
  let busy = false;
  let preserveDraft = false;
  let requestEpoch = 0;

  const element = document.createElement("section");
  element.className = "canvas-sku-editor";
  element.dataset.testid = "canvas-sku-editor";
  const feedback = document.createElement("p");
  feedback.className = "canvas-sku-feedback";
  feedback.setAttribute("role", "status");
  feedback.setAttribute("aria-live", "polite");

  const controlsDisabled = (): boolean =>
    busy || state === null || state.disabled || disposed;

  const updateControlDisabledState = (): void => {
    for (const control of element.querySelectorAll<
      HTMLButtonElement | HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement
    >("button,input,select,textarea")) {
      control.disabled = controlsDisabled();
    }
  };

  const adopt = (snapshot: ProjectSnapshot): void => {
    if (state === null || snapshot.project.id !== state.projectId) {
      return;
    }
    state = {
      ...state,
      revision: snapshot.revision,
      skus: snapshot.skus.map((sku) => structuredClone(sku)),
    };
    onSnapshot(snapshot);
  };

  const render = (): void => {
    if (disposed) {
      return;
    }
    const heading = document.createElement("h3");
    heading.textContent = "SKU";
    if (state === null) {
      const empty = document.createElement("p");
      empty.textContent = "选择项目后编辑 SKU。";
      element.replaceChildren(heading, empty, feedback);
      return;
    }

    const createRow = document.createElement("div");
    createRow.className = "canvas-sku-create";
    const createName = document.createElement("input");
    createName.type = "text";
    createName.maxLength = 200;
    createName.setAttribute("aria-label", "新 SKU 名称");
    const create = document.createElement("button");
    create.type = "button";
    create.textContent = "新增 SKU";
    create.setAttribute("aria-label", "新增 SKU");
    create.addEventListener("click", () => {
      const name = createName.value.trim();
      if (name === "") {
        feedback.textContent = "请输入 SKU 名称";
        return;
      }
      void mutate((current) => api.createSku(current.projectId, current.revision, { name }));
    });
    createRow.append(createName, create);

    const list = document.createElement("div");
    list.className = "canvas-sku-list";
    const ordered = [...state.skus].sort(
      (left, right) => left.sortOrder - right.sortOrder || left.id.localeCompare(right.id),
    );
    ordered.forEach((sku, index) => {
      const row = document.createElement("fieldset");
      row.className = "canvas-sku-row";
      row.dataset.skuId = sku.id;
      const legend = document.createElement("legend");
      legend.textContent = sku.name;

      const nameLabel = document.createElement("label");
      nameLabel.textContent = "名称";
      const name = document.createElement("input");
      name.type = "text";
      name.maxLength = 200;
      name.value = sku.name;
      name.setAttribute("aria-label", `SKU ${sku.name} 名称`);
      name.addEventListener("change", () => {
        const value = name.value.trim();
        if (value !== "" && value !== sku.name) {
          void mutate((current) => api.updateSku(current.projectId, sku.id, current.revision, { name: value }));
        }
      });
      nameLabel.append(name);

      const promptLabel = document.createElement("label");
      promptLabel.textContent = "提示词";
      const prompt = document.createElement("textarea");
      prompt.maxLength = 4_000;
      prompt.value = sku.prompt;
      prompt.setAttribute("aria-label", `SKU ${sku.name} 提示词`);
      prompt.addEventListener("change", () => {
        if (prompt.value !== sku.prompt) {
          void mutate((current) => api.updateSku(current.projectId, sku.id, current.revision, { prompt: prompt.value }));
        }
      });
      promptLabel.append(prompt);

      const referenceLabel = document.createElement("label");
      referenceLabel.textContent = "参考素材";
      const reference = document.createElement("select");
      reference.setAttribute("aria-label", `SKU ${sku.name} 参考素材`);
      const fallbackOption = document.createElement("option");
      fallbackOption.value = "";
      fallbackOption.textContent = "沿用主商品素材";
      reference.append(fallbackOption);
      for (const option of state?.referenceAssets ?? []) {
        const element = document.createElement("option");
        element.value = option.id;
        element.textContent = option.label;
        reference.append(element);
      }
      reference.value = sku.referenceAssetId ?? "";
      reference.addEventListener("change", () => {
        const referenceAssetId = reference.value === "" ? null : reference.value;
        if (referenceAssetId !== sku.referenceAssetId) {
          void mutate((current) => api.updateSku(current.projectId, sku.id, current.revision, { referenceAssetId }));
        }
      });
      referenceLabel.append(reference);

      const resolution = document.createElement("p");
      resolution.className = "canvas-sku-reference-resolution";
      resolution.textContent = sku.referenceAssetId === null
        ? state?.mainProductAssetId === null
          ? "缺少主商品素材；SKU 名称不会生成包装图"
          : `沿用主商品素材 ${state?.mainProductAssetId}`
        : `使用 SKU 参考素材 ${sku.referenceAssetId}`;

      const actions = document.createElement("div");
      actions.className = "canvas-sku-actions";
      const up = document.createElement("button");
      up.type = "button";
      up.textContent = "上移";
      up.setAttribute("aria-label", `上移 SKU ${sku.name}`);
      up.disabled = index === 0;
      up.addEventListener("click", () => {
        if (index > 0) {
          void patchSku(sku.id, { sortOrder: ordered[index - 1].sortOrder });
        }
      });
      const down = document.createElement("button");
      down.type = "button";
      down.textContent = "下移";
      down.setAttribute("aria-label", `下移 SKU ${sku.name}`);
      down.disabled = index === ordered.length - 1;
      down.addEventListener("click", () => {
        if (index < ordered.length - 1) {
          void patchSku(sku.id, { sortOrder: ordered[index + 1].sortOrder });
        }
      });
      const remove = document.createElement("button");
      remove.type = "button";
      remove.textContent = "删除";
      remove.setAttribute("aria-label", `删除 SKU ${sku.name}`);
      remove.addEventListener("click", () => {
        void mutate((current) => api.deleteSku(current.projectId, sku.id, current.revision));
      });
      actions.append(up, down, remove);
      row.append(legend, nameLabel, promptLabel, referenceLabel, resolution, actions);
      list.append(row);
    });
    element.replaceChildren(heading, createRow, list, feedback);
    updateControlDisabledState();
  };

  const mutate = async (
    operation: (current: SkuEditorState) => Promise<SaveResult>,
  ): Promise<void> => {
    if (state === null || controlsDisabled()) {
      return;
    }
    const epoch = ++requestEpoch;
    busy = true;
    preserveDraft = true;
    feedback.textContent = "正在保存 SKU…";
    updateControlDisabledState();
    const result = await operation(state);
    if (disposed || epoch !== requestEpoch) {
      return;
    }
    busy = false;
    if (result.ok) {
      preserveDraft = false;
      feedback.textContent = "SKU 已保存";
      adopt(result.snapshot);
      render();
      return;
    }
    if (result.kind === "conflict") {
      feedback.textContent = `版本冲突（服务器版本 ${result.currentRevision}），未覆盖本地编辑`;
    } else {
      feedback.textContent = result.message;
    }
    updateControlDisabledState();
  };

  const patchSku = (skuId: string, patch: SkuUpdatePatch): Promise<void> =>
    mutate((current) => api.updateSku(current.projectId, skuId, current.revision, patch));

  render();
  return {
    element,
    update: (nextState) => {
      const sameProject =
        state !== null &&
        nextState !== null &&
        state.projectId === nextState.projectId;
      const incoming = nextState === null
        ? null
        : {
            ...nextState,
            skus: nextState.skus.map((sku) => structuredClone(sku)),
            referenceAssets: nextState.referenceAssets.map((asset) => ({ ...asset })),
          };
      if (sameProject && (busy || preserveDraft)) {
        state = incoming;
        updateControlDisabledState();
        return;
      }
      if (!sameProject) {
        requestEpoch += 1;
        busy = false;
        preserveDraft = false;
      }
      state = incoming;
      feedback.textContent = "";
      render();
    },
    dispose: () => {
      if (disposed) {
        return;
      }
      disposed = true;
      requestEpoch += 1;
      element.remove();
    },
  };
}
