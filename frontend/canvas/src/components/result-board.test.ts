import { expect, test, vi } from "vitest";

import type { ResultVersion } from "../api/generations";
import type { OutputBoard } from "../domain/types";
import { createResultBoard } from "./result-board";

const board: OutputBoard = {
  id: "board-main", outputNodeId: "output-main", outputType: "main", skuId: null,
  sortOrder: 0, selectedResultAssetId: "composed-a",
};

const version = {
  versionId: "version-a", generationId: "generation-a", itemId: "item-a", attemptId: "attempt-a",
  boardId: "board-main", outputType: "main", skuId: null,
  backgroundAssetId: "background-a", backgroundPreviewAssetId: "background-preview-a",
  composedAssetId: "composed-a", composedPreviewAssetId: "composed-preview-a",
  width: 1024, height: 1024, modelProfileId: "model-a", modelDisplayName: "Seedream",
  modelConfigVersion: 1, createdAt: "2026-07-15T00:00:00Z",
} satisfies ResultVersion;

test("result board can clear only its saved selection reference", () => {
  const resultBoard = createResultBoard();
  const onSelect = vi.fn();
  resultBoard.update(board, [version], false, onSelect);

  const select = resultBoard.element.querySelector<HTMLSelectElement>('select[aria-label="选择结果版本"]');
  if (select === null) throw new Error("missing version selector");
  select.value = "";
  select.dispatchEvent(new Event("change", { bubbles: true }));

  expect(onSelect).toHaveBeenCalledWith(null);
});
