import type { ResultVersion } from "../api/generations";
import type { OutputBoard } from "../domain/types";

export interface ResultBoard {
  element: HTMLElement;
  update(board: OutputBoard | null, versions: readonly ResultVersion[], disabled: boolean, onSelect: (assetId: string | null) => void): void;
}

export function createResultBoard(): ResultBoard {
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
      const select = document.createElement("select");
      select.disabled = disabled;
      select.setAttribute("aria-label", "选择结果版本");
      select.append(Object.assign(document.createElement("option"), { value: "", textContent: "请选择版本" }));
      for (const version of versions.filter((version) => version.boardId === board.id)) {
        select.append(Object.assign(document.createElement("option"), { value: version.composedAssetId, textContent: `${version.modelDisplayName} · ${version.createdAt}` }));
      }
      select.value = board.selectedResultAssetId ?? "";
      select.addEventListener("change", () => {
        onSelect(select.value || null);
      });
      element.replaceChildren(heading, select);
    },
  };
}
