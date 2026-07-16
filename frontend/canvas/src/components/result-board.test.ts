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

test("result board compares versions and can clear only its saved selection reference", () => {
  const resultBoard = createResultBoard((id) => `/assets/${id}`);
  const onSelect = vi.fn();
  resultBoard.update(board, [version], false, onSelect);

  const versionCard = resultBoard.element.querySelector<HTMLButtonElement>('[data-asset-id="composed-a"]');
  if (versionCard === null) throw new Error("missing version card");
  expect(versionCard.getAttribute("aria-selected")).toBe("true");
  expect(resultBoard.element.querySelector("img")?.getAttribute("src")).toBe("/assets/composed-preview-a");

  resultBoard.element.querySelector<HTMLButtonElement>(".canvas-result-clear")?.click();

  expect(onSelect).toHaveBeenCalledWith(null);
});
