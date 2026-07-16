import {
  Canvas,
  type CanvasEvents,
  type FabricObject,
} from "fabric";

import type {
  CanvasProjectState,
  CanvasViewport,
  OutputBoardId,
  OutputType,
  ProjectAction,
} from "../domain/types";
import {
  createPresentationPlan,
  PRESENTATION_METADATA,
  type CanvasPresentationMetadata,
  type PresentationDescriptor,
  type PresentationRole,
} from "./object-factory";
import { panViewport, zoomViewport } from "./viewport";

export type ProjectState = CanvasProjectState;
export type WorkspaceMode = ProjectState["semanticState"]["mode"];
export type Dispatch = (action: ProjectAction) => void;

export interface CanvasAdapter {
  mount(element: HTMLCanvasElement, dispatch: Dispatch): void;
  project(previous: ProjectState | null, next: ProjectState): void;
  setMode(mode: WorkspaceMode): void;
  focusBoard(boardId: OutputBoardId): void;
  setResultBackgroundPreview?(assetId: string | null): void;
  cancelPendingLoads(): void;
  dispose(): void;
}

interface MountedPresentation {
  object: FabricObject;
  fingerprint: string;
  role: PresentationRole;
}

interface PendingPresentation {
  controller: AbortController;
  descriptor: PresentationDescriptor;
  epoch: number;
  surface: Canvas;
}

function outputTypeForNode(
  metadata: CanvasPresentationMetadata,
): OutputType | undefined {
  if (metadata.outputType !== undefined) {
    return metadata.outputType;
  }
  switch (metadata.node?.kind) {
    case "main_output":
      return "main";
    case "sku_output":
      return "sku";
    case "detail_output":
      return "detail";
    default:
      return undefined;
  }
}

function metadataFor(
  object: FabricObject | undefined,
): CanvasPresentationMetadata | undefined {
  if (object === undefined) {
    return undefined;
  }
  const value = object.get(PRESENTATION_METADATA) as unknown;
  if (typeof value !== "object" || value === null) {
    return undefined;
  }
  const candidate = value as Partial<CanvasPresentationMetadata>;
  if (
    typeof candidate.key !== "string" ||
    typeof candidate.domainId !== "string" ||
    typeof candidate.role !== "string"
  ) {
    return undefined;
  }
  return candidate as CanvasPresentationMetadata;
}

function isLockedSystemNodeKind(kind: string | undefined): boolean {
  return kind === "product_source" || kind === "auto_cutout";
}

function sameProject(
  previous: ProjectState,
  current: ProjectState,
): boolean {
  return JSON.stringify(previous) === JSON.stringify(current);
}

export function createCanvasAdapter(): CanvasAdapter {
  let element: HTMLCanvasElement | null = null;
  let dispatch: Dispatch | null = null;
  let surface: Canvas | null = null;
  let mounted = false;
  let disposed = false;
  let projectionDepth = 0;
  let loadEpoch = 0;
  let currentProject: ProjectState | null = null;
  let currentMode: WorkspaceMode = "complete-set";
  let currentViewport: CanvasViewport = { x: 0, y: 0, zoom: 1 };
  let selectedBackgroundPreviewAssetId: string | null = null;
  let lastPanPoint: { x: number; y: number } | null = null;
  let boardToNodeId = new Map<OutputBoardId, string>();
  let presentationOrder: string[] = [];
  const presentations = new Map<string, MountedPresentation>();
  const pending = new Map<string, PendingPresentation>();
  let listenerDisposers: Array<() => void> = [];

  const requireSurface = (): Canvas => {
    if (!mounted || surface === null) {
      throw new Error("CanvasAdapter must be mounted before use");
    }
    if (disposed) {
      throw new Error("CanvasAdapter has been disposed");
    }
    return surface;
  };

  const whileProjecting = <Result>(operation: () => Result): Result => {
    projectionDepth += 1;
    try {
      return operation();
    } finally {
      projectionDepth -= 1;
    }
  };

  const safeDispatch = (action: ProjectAction): void => {
    if (projectionDepth !== 0 || disposed) {
      return;
    }
    dispatch?.(structuredClone(action));
  };

  const bindListeners = (canvas: Canvas): void => {
    const authoritativePresentationFor = (
      target: FabricObject,
    ): {
      descriptor: PresentationDescriptor;
      nodeKind: string | undefined;
    } | undefined => {
      if (currentProject === null) return undefined;
      const registered = [...presentations.entries()].find(
        ([, presentation]) => presentation.object === target,
      );
      if (registered === undefined) return undefined;
      const [key, presentation] = registered;
      const plan = createPresentationPlan(currentProject);
      const descriptor = plan.descriptors.find(
        (candidate) => candidate.key === key && candidate.role === presentation.role,
      );
      if (descriptor === undefined) return undefined;
      const node = descriptor.role === "node"
        ? plan.project.semanticState.nodes.find(
            (candidate) => candidate.id === descriptor.domainId,
          )
        : undefined;
      return { descriptor, nodeKind: node?.kind };
    };
    const restoreAuthoritativeProjection = (
      target: FabricObject,
      descriptor: PresentationDescriptor,
    ): void => {
      whileProjecting(() => {
        target.set(descriptor.properties);
        target.setCoords();
        canvas.requestRenderAll();
      });
    };
    const restoreRemovedPresentation = (
      target: FabricObject,
      descriptor: PresentationDescriptor,
    ): void => {
      restoreAuthoritativeProjection(target, descriptor);
      whileProjecting(() => {
        if (!canvas.contains(target)) {
          canvas.add(target);
        }
      });
      reorderPresentations(canvas);
      canvas.requestRenderAll();
    };
    const onAdded = ({ target }: { target: FabricObject }): void => {
      const metadata = metadataFor(target);
      if (metadata?.role === "node" && metadata.node !== undefined) {
        safeDispatch({ type: "node/add", node: structuredClone(metadata.node) });
      }
    };
    const onModified = ({ target }: { target: FabricObject }): void => {
      if (projectionDepth !== 0) return;
      const metadata = metadataFor(target);
      const authoritative = authoritativePresentationFor(target);
      if (authoritative?.descriptor.role === "product") {
        restoreAuthoritativeProjection(target, authoritative.descriptor);
        return;
      }
      if (metadata?.role !== "node") {
        return;
      }
      const x = target.left;
      const y = target.top;
      if (!Number.isFinite(x) || !Number.isFinite(y)) {
        return;
      }
      safeDispatch({
        type: "node/move",
        nodeId: metadata.domainId,
        position: { x, y },
      });
    };
    const onRemoved = ({ target }: { target: FabricObject }): void => {
      if (projectionDepth !== 0) return;
      const authoritative = authoritativePresentationFor(target);
      if (authoritative?.descriptor.role === "product") {
        restoreRemovedPresentation(target, authoritative.descriptor);
        return;
      }
      if (
        authoritative?.descriptor.role === "node" &&
        isLockedSystemNodeKind(authoritative.nodeKind)
      ) {
        restoreRemovedPresentation(target, authoritative.descriptor);
        return;
      }
      const metadata = metadataFor(target);
      if (metadata?.role !== "node" || metadata.node?.managedBy !== "complete-set") {
        return;
      }
      const outputType = outputTypeForNode(metadata);
      if (outputType !== undefined) {
        safeDispatch({ type: "output/disable", outputType });
      }
    };

    const pointerPosition = (event: unknown): { x: number; y: number } | null => {
      if (typeof event !== "object" || event === null) {
        return null;
      }
      const candidate = event as Record<string, unknown>;
      if (
        typeof candidate.clientX === "number" &&
        typeof candidate.clientY === "number"
      ) {
        return { x: candidate.clientX, y: candidate.clientY };
      }
      const touches = candidate.touches;
      if (!Array.isArray(touches) || touches.length === 0) {
        return null;
      }
      const touch = touches[0];
      if (typeof touch !== "object" || touch === null) {
        return null;
      }
      const touchPoint = touch as Record<string, unknown>;
      return typeof touchPoint.clientX === "number" &&
        typeof touchPoint.clientY === "number"
        ? { x: touchPoint.clientX, y: touchPoint.clientY }
        : null;
    };
    const onMouseDown = (event: CanvasEvents["mouse:down"]): void => {
      const raw = event.e as unknown as Record<string, unknown>;
      if (raw.altKey !== true && raw.button !== 1) {
        return;
      }
      lastPanPoint = pointerPosition(event.e);
    };
    const onMouseMove = (event: CanvasEvents["mouse:move"]): void => {
      if (lastPanPoint === null) {
        return;
      }
      const nextPoint = pointerPosition(event.e);
      if (nextPoint === null) {
        return;
      }
      const nextViewport = panViewport(currentViewport, {
        x: nextPoint.x - lastPanPoint.x,
        y: nextPoint.y - lastPanPoint.y,
      });
      lastPanPoint = nextPoint;
      applyViewport(canvas, nextViewport);
      canvas.requestRenderAll();
      safeDispatch({ type: "viewport/set", viewport: nextViewport });
    };
    const onMouseUp = (): void => {
      lastPanPoint = null;
    };
    const onMouseWheel = (event: CanvasEvents["mouse:wheel"]): void => {
      const delta = event.e.deltaY;
      if (!Number.isFinite(delta)) {
        throw new Error("wheel delta must be finite");
      }
      event.e.preventDefault();
      const exponent = Math.min(20, Math.max(-20, -delta * 0.001));
      const nextViewport = zoomViewport(
        currentViewport,
        currentViewport.zoom * Math.exp(exponent),
      );
      applyViewport(canvas, nextViewport);
      canvas.requestRenderAll();
      safeDispatch({ type: "viewport/set", viewport: nextViewport });
    };

    listenerDisposers = [
      canvas.on("object:added", onAdded),
      canvas.on("object:modified", onModified),
      canvas.on("object:removed", onRemoved),
      canvas.on("mouse:down", onMouseDown),
      canvas.on("mouse:move", onMouseMove),
      canvas.on("mouse:up", onMouseUp),
      canvas.on("mouse:wheel", onMouseWheel),
    ];
  };

  const mountSurface = (): void => {
    if (element === null) {
      throw new Error("CanvasAdapter mount element is unavailable");
    }
    const canvas = new Canvas(element, {
      preserveObjectStacking: true,
      selection: true,
    });
    surface = canvas;
    bindListeners(canvas);
  };

  const cancelLoads = (): void => {
    loadEpoch += 1;
    for (const load of pending.values()) {
      load.controller.abort();
    }
    pending.clear();
  };

  const disposeSurface = (): void => {
    cancelLoads();
    lastPanPoint = null;
    for (const removeListener of listenerDisposers) {
      removeListener();
    }
    listenerDisposers = [];
    const oldSurface = surface;
    surface = null;
    presentations.clear();
    presentationOrder = [];
    boardToNodeId.clear();
    if (oldSurface !== null) {
      void oldSurface.dispose().catch(() => undefined);
    }
  };

  const remountSurface = (): Canvas => {
    disposeSurface();
    mountSurface();
    currentProject = null;
    return requireSurface();
  };

  const applyViewport = (
    canvas: Canvas,
    viewport: CanvasViewport,
  ): void => {
    currentViewport = zoomViewport(viewport, viewport.zoom);
    whileProjecting(() => {
      canvas.setViewportTransform([
        currentViewport.zoom,
        0,
        0,
        currentViewport.zoom,
        currentViewport.x,
        currentViewport.y,
      ]);
    });
  };

  const applyModeVisibility = (canvas: Canvas): void => {
    const advanced = currentMode === "advanced";
    whileProjecting(() => {
      for (const presentation of presentations.values()) {
        if (presentation.role === "edge" || presentation.role === "port") {
          presentation.object.set("visible", advanced);
          presentation.object.setCoords();
        }
      }
    });
    canvas.requestRenderAll();
  };

  const removeMissingPresentations = (
    canvas: Canvas,
    descriptors: readonly PresentationDescriptor[],
  ): void => {
    const desiredKeys = new Set(descriptors.map((descriptor) => descriptor.key));
    for (const [key, load] of pending) {
      const desired = descriptors.find((descriptor) => descriptor.key === key);
      if (
        !desiredKeys.has(key) ||
        desired?.fingerprint !== load.descriptor.fingerprint
      ) {
        load.controller.abort();
        pending.delete(key);
      }
    }
    const removed: FabricObject[] = [];
    for (const [key, presentation] of presentations) {
      if (!desiredKeys.has(key)) {
        removed.push(presentation.object);
        presentations.delete(key);
      }
    }
    if (removed.length > 0) {
      whileProjecting(() => canvas.remove(...removed));
    }
  };

  const reorderPresentations = (canvas: Canvas): void => {
    let index = 0;
    whileProjecting(() => {
      for (const key of presentationOrder) {
        const presentation = presentations.get(key);
        if (presentation === undefined) continue;
        canvas.moveObjectTo(presentation.object, index);
        index += 1;
      }
    });
  };

  const startImageLoad = (
    canvas: Canvas,
    descriptor: Extract<PresentationDescriptor, { kind: "image" }>,
  ): void => {
    const controller = new AbortController();
    const epoch = loadEpoch;
    const load: PendingPresentation = {
      controller,
      descriptor,
      epoch,
      surface: canvas,
    };
    pending.set(descriptor.key, load);
    void descriptor
      .load(controller.signal)
      .then((object) => {
        const active = pending.get(descriptor.key);
        if (
          disposed ||
          controller.signal.aborted ||
          active !== load ||
          load.epoch !== loadEpoch ||
          surface !== load.surface
        ) {
          object.dispose();
          return;
        }
        pending.delete(descriptor.key);
        object.set(
          "visible",
          descriptor.role === "edge" || descriptor.role === "port"
            ? currentMode === "advanced"
            : descriptor.properties.visible ?? true,
        );
        object.setCoords();
        presentations.set(descriptor.key, {
          object,
          fingerprint: descriptor.fingerprint,
          role: descriptor.role,
        });
        whileProjecting(() => canvas.add(object));
        reorderPresentations(canvas);
        canvas.requestRenderAll();
      })
      .catch(() => {
        if (pending.get(descriptor.key) === load) {
          pending.delete(descriptor.key);
        }
      });
  };

  const addOrUpdatePresentations = (
    canvas: Canvas,
    descriptors: readonly PresentationDescriptor[],
  ): void => {
    for (const descriptor of descriptors) {
      const existing = presentations.get(descriptor.key);
      if (existing !== undefined) {
        if (existing.fingerprint !== descriptor.fingerprint) {
          if (descriptor.kind === "image") {
            presentations.delete(descriptor.key);
            whileProjecting(() => canvas.remove(existing.object));
            existing.object.dispose();
            startImageLoad(canvas, descriptor);
            continue;
          }
          whileProjecting(() => {
            existing.object.set(descriptor.properties);
            existing.object.setCoords();
          });
          existing.fingerprint = descriptor.fingerprint;
          existing.role = descriptor.role;
        }
        continue;
      }
      const existingLoad = pending.get(descriptor.key);
      if (existingLoad !== undefined) {
        if (existingLoad.descriptor.fingerprint === descriptor.fingerprint) {
          continue;
        }
        existingLoad.controller.abort();
        pending.delete(descriptor.key);
      }
      if (descriptor.kind === "image") {
        startImageLoad(canvas, descriptor);
        continue;
      }
      const object = descriptor.create();
      presentations.set(descriptor.key, {
        object,
        fingerprint: descriptor.fingerprint,
        role: descriptor.role,
      });
      whileProjecting(() => canvas.add(object));
    }
  };

  const mount = (nextElement: HTMLCanvasElement, nextDispatch: Dispatch): void => {
    if (disposed) {
      throw new Error("CanvasAdapter has been disposed");
    }
    if (mounted) {
      throw new Error("CanvasAdapter is already mounted");
    }
    element = nextElement;
    dispatch = nextDispatch;
    mounted = true;
    mountSurface();
  };

  const project = (
    previous: ProjectState | null,
    next: ProjectState,
  ): void => {
    let canvas = requireSurface();
    const plan = createPresentationPlan(
      next,
      next.semanticState.mode,
      selectedBackgroundPreviewAssetId,
    );
    const switchingProject =
      currentProject !== null &&
      (previous === null || !sameProject(previous, currentProject));
    if (switchingProject) {
      canvas = remountSurface();
    }

    presentationOrder = plan.descriptors.map((descriptor) => descriptor.key);
    currentMode = plan.project.semanticState.mode;
    removeMissingPresentations(canvas, plan.descriptors);
    addOrUpdatePresentations(canvas, plan.descriptors);
    reorderPresentations(canvas);
    boardToNodeId = new Map(plan.boardToNodeId);
    applyModeVisibility(canvas);
    applyViewport(canvas, plan.project.layoutState.viewport);
    currentProject = plan.project;
    canvas.requestRenderAll();
  };

  const setMode = (mode: WorkspaceMode): void => {
    const canvas = requireSurface();
    if (mode !== "complete-set" && mode !== "advanced") {
      throw new Error(`unsupported workspace mode ${String(mode)}`);
    }
    currentMode = mode;
    applyModeVisibility(canvas);
  };

  const focusBoard = (boardId: OutputBoardId): void => {
    const canvas = requireSurface();
    const nodeId = boardToNodeId.get(boardId);
    if (nodeId === undefined) {
      throw new Error(`unknown output board ${boardId}`);
    }
    const presentation = presentations.get(`node:${nodeId}`);
    if (presentation === undefined) {
      throw new Error(`output board ${boardId} has no domain presentation`);
    }
    const center = presentation.object.getCenterPoint();
    const zoom = currentViewport.zoom;
    const viewport = zoomViewport(
      {
        x: canvas.getWidth() / 2 - center.x * zoom,
        y: canvas.getHeight() / 2 - center.y * zoom,
        zoom,
      },
      zoom,
    );
    applyViewport(canvas, viewport);
    canvas.requestRenderAll();
  };

  const setResultBackgroundPreview = (assetId: string | null): void => {
    if (selectedBackgroundPreviewAssetId === assetId) return;
    selectedBackgroundPreviewAssetId = assetId;
    if (currentProject !== null) {
      project(currentProject, currentProject);
    }
  };

  const cancelPendingLoads = (): void => {
    cancelLoads();
  };

  const dispose = (): void => {
    if (disposed) {
      return;
    }
    disposed = true;
    disposeSurface();
    currentProject = null;
    dispatch = null;
    element = null;
  };

  return {
    mount,
    project,
    setMode,
    focusBoard,
    setResultBackgroundPreview,
    cancelPendingLoads,
    dispose,
  };
}
