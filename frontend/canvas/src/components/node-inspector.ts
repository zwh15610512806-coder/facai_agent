import type { ModelProfile } from "../domain/providers";
import type { CanvasNode, CanvasNodePatch } from "../domain/types";
import { compatibleEdgeKinds } from "../domain/node-ports";

export interface NodeInspector {
  element: HTMLElement;
  update(
    nodes: readonly CanvasNode[],
    models: readonly ModelProfile[],
    disabled: boolean,
    onPatch: (nodeId: string, patch: CanvasNodePatch) => void,
    onConnect?: (sourceNodeId: string, targetNodeId: string) => void,
  ): void;
}

export function createNodeInspector(): NodeInspector {
  const element = document.createElement("section");
  element.className = "canvas-node-inspector";
  let selectedNodeId: string | null = null;
  const update: NodeInspector["update"] = (nodes, models, disabled, onPatch, onConnect) => {
    const heading = document.createElement("h3");
    heading.textContent = "节点检查器";
    const select = document.createElement("select");
    select.setAttribute("aria-label", "选择高级节点");
    const isImmutable = (node: CanvasNode): boolean =>
      node.managedBy !== null || node.id === "main-product-source" || node.id === "main-product-cutout";
    const endpointNodes = [...nodes];
    const editableNodes = endpointNodes.filter((node) => !isImmutable(node));
    for (const node of endpointNodes) {
      select.append(Object.assign(document.createElement("option"), { value: node.id, textContent: `${node.kind} · ${node.id}` }));
    }
    if (!endpointNodes.some((node) => node.id === selectedNodeId)) {
      selectedNodeId = endpointNodes[0]?.id ?? null;
    }
    select.value = selectedNodeId ?? "";
    const selected = endpointNodes.find((node) => node.id === selectedNodeId) ?? null;
    const selectedImmutable = selected !== null && isImmutable(selected);
    const prompt = document.createElement("textarea");
    prompt.value = selected?.prompt ?? "";
    prompt.disabled = disabled || selected === null || selectedImmutable;
    prompt.setAttribute("aria-label", "节点提示词");
    prompt.addEventListener("input", () => {
      if (selected !== null && !selectedImmutable) onPatch(selected.id, { prompt: prompt.value });
    });
    const controls: HTMLElement[] = [heading, select, prompt];
    if (selected?.kind === "model_generation") {
      const modelSelect = document.createElement("select");
      modelSelect.setAttribute("aria-label", "节点模型");
      modelSelect.disabled = disabled || selectedImmutable;
      modelSelect.append(Object.assign(document.createElement("option"), { value: "", textContent: "选择模型" }));
      for (const model of models.filter((model) => model.enabled && model.availability === "available")) {
        modelSelect.append(Object.assign(document.createElement("option"), {
          value: model.id,
          textContent: model.displayName,
        }));
      }
      modelSelect.value = selected.modelProfileId ?? "";
      modelSelect.addEventListener("change", () => {
        onPatch(selected.id, { modelProfileId: modelSelect.value || null });
      });
      const dimension = (label: string, value: unknown): HTMLInputElement => {
        const input = document.createElement("input");
        input.type = "number";
        input.min = "1";
        input.step = "1";
        input.value = typeof value === "number" ? String(value) : "";
        input.disabled = disabled || selectedImmutable;
        input.setAttribute("aria-label", label);
        return input;
      };
      const width = dimension("生成宽度", selected.parameters.width);
      const height = dimension("生成高度", selected.parameters.height);
      const patchDimensions = (): void => {
        const widthValue = Number(width.value);
        const heightValue = Number(height.value);
        onPatch(selected.id, {
          parameters: {
            ...(Number.isInteger(widthValue) && widthValue > 0 ? { width: widthValue } : {}),
            ...(Number.isInteger(heightValue) && heightValue > 0 ? { height: heightValue } : {}),
          },
        });
      };
      width.addEventListener("change", patchDimensions);
      height.addEventListener("change", patchDimensions);
      controls.push(modelSelect, width, height);
    }
    if (
      selected?.kind === "sku_reference" ||
      selected?.kind === "auto_cutout" ||
      selected?.kind === "product_source"
    ) {
      const asset = document.createElement("input");
      asset.type = "text";
      asset.value = selected.assetId ?? "";
      asset.disabled = disabled || selectedImmutable;
      asset.setAttribute("aria-label", "节点资源 ID");
      asset.addEventListener("change", () => onPatch(selected.id, { assetId: asset.value.trim() || null }));
      controls.push(asset);
    }
    if (selected?.kind === "sku_reference" || selected?.kind === "auto_cutout") {
      const sku = document.createElement("input");
      sku.type = "text";
      sku.value = selected.skuId ?? "";
      sku.disabled = disabled || selectedImmutable;
      sku.setAttribute("aria-label", "节点 SKU ID");
      sku.addEventListener("change", () => onPatch(selected.id, { skuId: sku.value.trim() || null }));
      controls.push(sku);
    }
    if (selected?.kind === "composition_group") {
      const group = document.createElement("input");
      group.type = "text";
      group.value = selected.compositionGroupId ?? "";
      group.disabled = disabled || selectedImmutable;
      group.setAttribute("aria-label", "节点构图组 ID");
      group.addEventListener("change", () => onPatch(selected.id, { compositionGroupId: group.value.trim() || null }));
      controls.push(group);
    }
    select.addEventListener("change", () => {
      selectedNodeId = select.value || null;
      update(nodes, models, disabled, onPatch, onConnect);
    });
    if (onConnect !== undefined) {
      const source = document.createElement("select");
      const target = document.createElement("select");
      source.setAttribute("aria-label", "连线来源");
      target.setAttribute("aria-label", "连线目标");
      for (const node of endpointNodes) {
        source.append(Object.assign(document.createElement("option"), { value: node.id, textContent: `${node.kind} · ${node.id}` }));
        target.append(Object.assign(document.createElement("option"), { value: node.id, textContent: `${node.kind} · ${node.id}` }));
      }
      const initialSource = endpointNodes[0];
      const initialTarget = initialSource === undefined
        ? undefined
        : endpointNodes.find(
            (candidate) =>
              candidate.id !== initialSource.id &&
              compatibleEdgeKinds(initialSource.kind, candidate.kind).length > 0,
          );
      source.value = initialSource?.id ?? "";
      target.value = initialTarget?.id ?? initialSource?.id ?? "";
      const connect = document.createElement("button");
      connect.type = "button";
      connect.textContent = "连接节点";
      const refreshConnectability = (): void => {
        const sourceNode = endpointNodes.find((node) => node.id === source.value);
        const targetNode = endpointNodes.find((node) => node.id === target.value);
        connect.disabled = disabled || sourceNode === undefined || targetNode === undefined ||
          sourceNode.id === targetNode.id || compatibleEdgeKinds(sourceNode.kind, targetNode.kind).length === 0;
      };
      source.addEventListener("change", refreshConnectability);
      target.addEventListener("change", refreshConnectability);
      connect.addEventListener("click", () => {
        const sourceNode = endpointNodes.find((node) => node.id === source.value);
        const targetNode = endpointNodes.find((node) => node.id === target.value);
        if (
          sourceNode !== undefined &&
          targetNode !== undefined &&
          sourceNode.id !== targetNode.id &&
          compatibleEdgeKinds(sourceNode.kind, targetNode.kind).length > 0
        ) {
          onConnect(source.value, target.value);
        }
      });
      refreshConnectability();
      controls.push(source, target, connect);
    }
    element.replaceChildren(...controls);
  };
  return {
    element,
    update,
  };
}
