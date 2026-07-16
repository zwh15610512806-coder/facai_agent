import type { ResultVersion } from "../api/generations";
import type { OutputBoard } from "../domain/types";

export interface ResultBoard {
  element: HTMLElement;
  update(board: OutputBoard | null, versions: readonly ResultVersion[], disabled: boolean, onSelect: (assetId: string | null) => void): void;
}

export function createResultBoard(previewUrl?: (assetId: string) => string): ResultBoard {
  const element = document.createElement("section");
  element.className = "canvas-result-board";
  return {
    element,
    update: (board, versions, disabled, onSelect) => {
      const heading = document.createElement("h3");
      heading.textContent = "结果版本";
      if (board === null) {
        element.replaceChildren(heading, Object.assign(document.createElement("p"), { textContent: "暂无输出画板" }));
        return;
      }
      const boardVersions = versions.filter((version) => version.boardId === board.id);
      const hint = document.createElement("p");
      hint.className = "canvas-result-board-hint";
      hint.textContent = boardVersions.length === 0
        ? "生成完成后，成功版本会出现在这里。"
        : "对比版本并显式选择一个成功结果，才能继续导出。";
      const grid = document.createElement("div");
      grid.className = "canvas-result-version-grid";
      grid.setAttribute("role", "listbox");
      grid.setAttribute("aria-label", "选择结果版本");
      for (const version of boardVersions) {
        const card = document.createElement("button");
        card.type = "button";
        card.className = "canvas-result-version";
        card.disabled = disabled;
        card.dataset.assetId = version.composedAssetId;
        card.setAttribute("role", "option");
        card.setAttribute("aria-selected", version.composedAssetId === board.selectedResultAssetId ? "true" : "false");
        if (version.composedAssetId === board.selectedResultAssetId) card.classList.add("is-selected");
        if (previewUrl !== undefined) {
          const image = document.createElement("img");
          image.src = previewUrl(version.composedPreviewAssetId || version.composedAssetId);
          image.alt = `${version.modelDisplayName} 生成版本预览`;
          image.loading = "lazy";
          card.append(image);
        }
        const model = document.createElement("strong");
        model.textContent = version.modelDisplayName;
        const meta = document.createElement("span");
        meta.textContent = `${version.width} × ${version.height} · ${new Date(version.createdAt).toLocaleString("zh-CN", { hour12: false })}`;
        const selected = document.createElement("span");
        selected.className = "canvas-result-selected-label";
        selected.textContent = version.composedAssetId === board.selectedResultAssetId ? "已选版本" : "选择此版本";
        card.append(model, meta, selected);
        card.addEventListener("click", () => onSelect(version.composedAssetId));
        grid.append(card);
      }
      const clear = document.createElement("button");
      clear.type = "button";
      clear.className = "canvas-result-clear";
      clear.textContent = "取消当前选择";
      clear.hidden = board.selectedResultAssetId === null;
      clear.disabled = disabled;
      clear.addEventListener("click", () => onSelect(null));
      element.replaceChildren(heading, hint, grid, clear);
    },
  };
}
