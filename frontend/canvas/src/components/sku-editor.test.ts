import { expect, test, vi } from "vitest";

import type { ProjectSku, ProjectSnapshot } from "../api/client";
import type { SkusApi, SkuUpdatePatch } from "../api/skus";
import { createEmptyProjectState } from "../domain/types";
import { createSkuEditor } from "./sku-editor";

function sku(id: string, name: string, sortOrder: number): ProjectSku {
  return {
    id,
    projectId: "project-a",
    name,
    sortOrder,
    referenceAssetId: null,
    prompt: "",
    config: {},
  };
}

function snapshot(revision: number, skus: ProjectSku[]): ProjectSnapshot {
  const project = createEmptyProjectState();
  return {
    project: {
      id: "project-a",
      name: "Project A",
      status: "active",
      schemaVersion: 1,
      revision,
      createdAt: null,
      updatedAt: null,
      archivedAt: null,
      semanticState: project.semanticState,
      layoutState: project.layoutState,
    },
    skus,
    revision,
  };
}

async function settle(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
}

function input(label: string): HTMLInputElement {
  const element = document.querySelector<HTMLInputElement>(`input[aria-label="${label}"]`);
  if (element === null) throw new Error(`missing input ${label}`);
  return element;
}

function button(label: string): HTMLButtonElement {
  const element = [...document.querySelectorAll<HTMLButtonElement>("button")].find(
    (candidate) => candidate.getAttribute("aria-label") === label || candidate.textContent === label,
  );
  if (element === undefined) throw new Error(`missing button ${label}`);
  return element;
}

test("SKU editor adopts successful revisions across create/edit/reorder/reference/delete", async () => {
  let revision = 1;
  let skus = [sku("sku-a", "Red", 10), sku("sku-b", "Blue", 20)];
  const createSku = vi.fn<SkusApi["createSku"]>(async (_projectId, requestRevision, data) => {
    expect(requestRevision).toBe(revision);
    revision += 1;
    skus = [...skus, sku("sku-c", data.name, 30)];
    return { ok: true, snapshot: snapshot(revision, skus) };
  });
  const updateSku = vi.fn<SkusApi["updateSku"]>(async (_projectId, skuId, requestRevision, patch: SkuUpdatePatch) => {
    expect(requestRevision).toBe(revision);
    revision += 1;
    skus = skus.map((item) => item.id === skuId ? { ...item, ...patch } : item);
    return { ok: true, snapshot: snapshot(revision, skus) };
  });
  const deleteSku = vi.fn<SkusApi["deleteSku"]>(async (_projectId, skuId, requestRevision) => {
    expect(requestRevision).toBe(revision);
    revision += 1;
    skus = skus.filter((item) => item.id !== skuId);
    return { ok: true, snapshot: snapshot(revision, skus) };
  });
  const api = { createSku, updateSku, deleteSku } as SkusApi;
  const onSnapshot = vi.fn();
  const editor = createSkuEditor({ api, onSnapshot });
  document.body.append(editor.element);
  editor.update({
    projectId: "project-a",
    revision,
    skus,
    mainProductAssetId: "working-main",
    referenceAssets: [{ id: "working-b", label: "Blue package" }],
    disabled: false,
  });

  expect(editor.element.textContent).toContain("沿用主商品素材 working-main");
  const createName = input("新 SKU 名称");
  createName.value = "Green";
  button("新增 SKU").click();
  await settle();
  expect(createSku).toHaveBeenCalledWith("project-a", 1, { name: "Green" });

  const name = input("SKU Red 名称");
  name.value = "Crimson";
  name.dispatchEvent(new Event("change", { bubbles: true }));
  await settle();
  expect(updateSku).toHaveBeenLastCalledWith("project-a", "sku-a", 2, { name: "Crimson" });

  const prompt = document.querySelector<HTMLTextAreaElement>('textarea[aria-label="SKU Crimson 提示词"]');
  if (prompt === null) throw new Error("missing prompt");
  prompt.value = "front pack";
  prompt.dispatchEvent(new Event("change", { bubbles: true }));
  await settle();
  expect(updateSku).toHaveBeenLastCalledWith("project-a", "sku-a", 3, { prompt: "front pack" });

  const reference = document.querySelector<HTMLSelectElement>('select[aria-label="SKU Crimson 参考素材"]');
  if (reference === null) throw new Error("missing reference select");
  reference.value = "working-b";
  reference.dispatchEvent(new Event("change", { bubbles: true }));
  await settle();
  expect(updateSku).toHaveBeenLastCalledWith("project-a", "sku-a", 4, {
    referenceAssetId: "working-b",
  });

  button("下移 SKU Crimson").click();
  await settle();
  expect(updateSku).toHaveBeenLastCalledWith("project-a", "sku-a", 5, { sortOrder: 20 });
  button("删除 SKU Crimson").click();
  await settle();
  expect(deleteSku).toHaveBeenLastCalledWith("project-a", "sku-a", 6);
  expect(onSnapshot).toHaveBeenCalledTimes(6);
  editor.dispose();
});

test("SKU 409 keeps the local edit and surfaces conflict without overwriting", async () => {
  const api = {
    createSku: vi.fn(),
    updateSku: vi.fn(async () => ({
      ok: false as const,
      kind: "conflict" as const,
      currentRevision: 9,
    })),
    deleteSku: vi.fn(),
  } as unknown as SkusApi;
  const onSnapshot = vi.fn();
  const editor = createSkuEditor({ api, onSnapshot });
  document.body.append(editor.element);
  editor.update({
    projectId: "project-a",
    revision: 3,
    skus: [sku("sku-a", "Server name", 0)],
    mainProductAssetId: "working-main",
    referenceAssets: [],
    disabled: false,
  });
  const name = input("SKU Server name 名称");
  name.value = "Local name";
  name.dispatchEvent(new Event("change", { bubbles: true }));
  await settle();

  expect(name.value).toBe("Local name");
  expect(editor.element.textContent).toContain("版本冲突");
  expect(editor.element.textContent).toContain("9");
  expect(onSnapshot).not.toHaveBeenCalled();

  editor.update({
    projectId: "project-a",
    revision: 4,
    skus: [sku("sku-a", "Server name", 0)],
    mainProductAssetId: "working-main",
    referenceAssets: [],
    disabled: false,
  });
  expect(input("SKU Server name 名称").value).toBe("Local name");
  editor.dispose();
});

test("same-project updates do not cancel an in-flight SKU revision adoption", async () => {
  let resolveUpdate!: (result: Awaited<ReturnType<SkusApi["updateSku"]>>) => void;
  const api = {
    createSku: vi.fn(),
    updateSku: vi.fn(() => new Promise((resolve) => {
      resolveUpdate = resolve;
    })),
    deleteSku: vi.fn(),
  } as unknown as SkusApi;
  const onSnapshot = vi.fn();
  const editor = createSkuEditor({ api, onSnapshot });
  document.body.append(editor.element);
  const initial = {
    projectId: "project-a",
    revision: 3,
    skus: [sku("sku-a", "Server name", 0)],
    mainProductAssetId: "working-main",
    referenceAssets: [],
    disabled: false,
  };
  editor.update(initial);
  const name = input("SKU Server name 名称");
  name.value = "Saved name";
  name.dispatchEvent(new Event("change", { bubbles: true }));

  editor.update({ ...initial });
  resolveUpdate({
    ok: true,
    snapshot: snapshot(4, [sku("sku-a", "Saved name", 0)]),
  });
  await settle();

  expect(onSnapshot).toHaveBeenCalledWith(snapshot(4, [sku("sku-a", "Saved name", 0)]));
  expect(editor.element.textContent).toContain("SKU 已保存");
  editor.dispose();
});
