import { describe, expect, it, vi } from "vitest";

import type { ResultVersion } from "../api/generations";
import type { ExportsApi } from "../api/exports";
import { createEmptyProjectState } from "../domain/types";
import { createExportPanel } from "./export-panel";

function fixture() {
  const project = createEmptyProjectState();
  project.semanticState.outputBoards = [
    { id: "board-main", outputNodeId: "node-main", outputType: "main", skuId: null, sortOrder: 0, selectedResultAssetId: "composed-main" },
    { id: "board-sku", outputNodeId: "node-sku", outputType: "sku", skuId: "sku-1", sortOrder: 1, selectedResultAssetId: "composed-sku" },
  ];
  const base = {
    generationId: "generation-1",
    itemId: "item-1",
    attemptId: "attempt-main",
    backgroundAssetId: "background-1",
    backgroundPreviewAssetId: "background-preview-1",
    composedPreviewAssetId: "composed-preview-1",
    width: 1024,
    height: 1024,
    modelProfileId: "model-1",
    modelDisplayName: "Seedream 5.0 Pro",
    modelConfigVersion: 1,
    createdAt: "2026-07-15T10:00:00",
  };
  const versions: ResultVersion[] = [
    { ...base, versionId: "attempt-main", boardId: "board-main", outputType: "main", skuId: null, composedAssetId: "composed-main" },
    { ...base, versionId: "attempt-sku", attemptId: "attempt-sku", boardId: "board-sku", outputType: "sku", skuId: "sku-1", composedAssetId: "composed-sku" },
  ];
  return { project, versions };
}

describe("ExportPanel", () => {
  it("has no default output mode or format and submits the user's ordered selections", async () => {
    const { project, versions } = fixture();
    const create = vi.fn<ExportsApi["create"]>(async () => ({
      ok: true as const,
      value: {
        id: "export-operation",
        projectId: "project-1",
        operationType: "export" as const,
        status: "queued" as const,
        attemptCount: 0,
        inputAssetId: "composed-main",
        outputAssetId: null,
        safeError: null,
      },
    }));
    const panel = createExportPanel({
      api: { create, downloadUrl: (id) => `/download/${id}` },
      getProject: () => project,
      getProjectId: () => "project-1",
      getRevision: () => 7,
      getVersions: () => versions,
      isEditable: () => true,
      flushSave: async () => ({ ok: true }),
      onUnauthorized: vi.fn(),
    });
    panel.update();

    expect(panel.element.querySelector("[aria-pressed='true']")).toBeNull();
    expect(panel.element.querySelector<HTMLButtonElement>("[data-testid='canvas-export-submit']")?.disabled).toBe(true);
    const select = (boardId: string): void => {
      const checkbox = panel.element.querySelector<HTMLInputElement>(`input[data-board-id='${boardId}']`)!;
      checkbox.checked = true;
      checkbox.dispatchEvent(new Event("change"));
    };
    select("board-sku");
    select("board-main");
    panel.element.querySelector<HTMLElement>("[data-export-mode='category_zip']")!.click();
    panel.element.querySelector<HTMLElement>("[data-export-format='png']")!.click();
    panel.element.querySelector<HTMLElement>("[data-testid='canvas-export-submit']")!.click();
    await vi.waitFor(() => expect(create).toHaveBeenCalledOnce());

    expect(create.mock.calls[0]?.[1]).toEqual({
      projectRevision: 7,
      mode: "category_zip",
      format: "png",
      selectedBoards: [
        { boardId: "board-sku", versionId: "attempt-sku", composedAssetId: "composed-sku", order: 0 },
        { boardId: "board-main", versionId: "attempt-main", composedAssetId: "composed-main", order: 1 },
      ],
      jpegBackground: null,
    });
  });

  it("requires detail-only selection for detail exports and exposes download after success", () => {
    const { project, versions } = fixture();
    const panel = createExportPanel({
      api: { create: vi.fn(), downloadUrl: (id) => `/download/${id}` },
      getProject: () => project,
      getProjectId: () => "project-1",
      getRevision: () => 7,
      getVersions: () => versions,
      isEditable: () => true,
      flushSave: async () => ({ ok: true }),
      onUnauthorized: vi.fn(),
    });
    panel.update();
    const checkbox = panel.element.querySelector<HTMLInputElement>("input[data-board-id='board-main']")!;
    checkbox.checked = true;
    checkbox.dispatchEvent(new Event("change"));
    panel.element.querySelector<HTMLElement>("[data-export-mode='detail_long']")!.click();
    panel.element.querySelector<HTMLElement>("[data-export-format='webp']")!.click();
    expect(panel.element.textContent).toContain("详情导出只能选择详情页画板");
    panel.applyOperation({
      id: "export-operation",
      projectId: "project-1",
      operationType: "export",
      status: "succeeded",
      attemptCount: 1,
      inputAssetId: "composed-main",
      outputAssetId: "export-asset",
      safeError: null,
    });
    expect(panel.element.querySelector<HTMLAnchorElement>("[data-testid='canvas-export-download']")?.href).toContain("/download/export-asset");
  });
});
