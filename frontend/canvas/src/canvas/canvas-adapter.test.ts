import { beforeEach, describe, expect, test, vi } from "vitest";

import domainTypesSource from "../domain/types.ts?raw";
import domainValidationSource from "../domain/validation.ts?raw";
import {
  createEmptyProjectState,
  type CanvasNode,
  type CanvasProjectState,
  type ProjectAction,
  type TypedEdge,
} from "../domain/types";
import mainSource from "../main.ts?raw";
import {
  createCanvasAdapter as createCanvasAdapterFromMain,
  mountCanvas,
} from "../main";
import projectStoreSource from "../state/project-store.ts?raw";
import { createProjectStore } from "../state/project-store";
import { compositionLayoutHash } from "../domain/composition";
import {
  createCanvasAdapter,
  type CanvasAdapter,
  type Dispatch,
} from "./canvas-adapter";
import { createPresentationPlan } from "./object-factory";
import {
  DEFAULT_VIEWPORT_SAFETY,
  panViewport,
  zoomViewport,
} from "./viewport";

const fabricHarness = vi.hoisted(() => {
  type Listener = (event: Record<string, unknown>) => void;

  class FakeFabricObject {
    [key: string]: unknown;

    canvas: FakeCanvas | null = null;
    left = 0;
    top = 0;
    visible = true;
    disposeCalls = 0;

    constructor(options: Record<string, unknown> = {}) {
      Object.assign(this, options);
    }

    set(key: string | Record<string, unknown>, value?: unknown): this {
      if (typeof key === "string") {
        this[key] = value;
      } else {
        Object.assign(this, key);
      }
      this.canvas?.emit("object:modified", { target: this });
      return this;
    }

    get(key: string): unknown {
      return this[key];
    }

    setCoords(): void {}

    getCenterPoint(): { x: number; y: number } {
      return { x: Number(this.left), y: Number(this.top) };
    }

    dispose(): void {
      this.disposeCalls += 1;
    }

    toObject(): never {
      throw new Error("Fabric serialization must not cross CanvasAdapter");
    }

    toJSON(): never {
      throw new Error("Fabric serialization must not cross CanvasAdapter");
    }
  }

  class FakeRect extends FakeFabricObject {}
  class FakeCircle extends FakeFabricObject {}
  class FakeTextbox extends FakeFabricObject {
    constructor(text: string, options: Record<string, unknown> = {}) {
      super({ ...options, text });
    }
  }
  class FakeLine extends FakeFabricObject {
    constructor(points: number[], options: Record<string, unknown> = {}) {
      super({ ...options, points: [...points] });
    }
  }
  class FakePoint {
    constructor(
      readonly x: number,
      readonly y: number,
    ) {}
  }

  interface PendingImageLoad {
    url: string;
    signal: AbortSignal | undefined;
    resolve(image: FakeFabricImage): void;
    reject(error: unknown): void;
  }

  const imageLoads: PendingImageLoad[] = [];

  class FakeFabricImage extends FakeFabricObject {
    static fromURL(
      url: string,
      options: { signal?: AbortSignal } = {},
      imageOptions: Record<string, unknown> = {},
    ): Promise<FakeFabricImage> {
      return new Promise((resolve, reject) => {
        imageLoads.push({
          url,
          signal: options.signal,
          resolve: (image) => {
            image.set(imageOptions);
            resolve(image);
          },
          reject,
        });
      });
    }
  }

  class FakeCanvas {
    static instances: FakeCanvas[] = [];

    readonly objects: FakeFabricObject[] = [];
    readonly listeners = new Map<string, Set<Listener>>();
    readonly addBatches: FakeFabricObject[][] = [];
    readonly removeBatches: FakeFabricObject[][] = [];
    readonly viewportTransforms: number[][] = [];
    clearCalls = 0;
    disposeCalls = 0;
    renderRequests = 0;
    viewportTransform = [1, 0, 0, 1, 0, 0];

    constructor(
      readonly element: HTMLCanvasElement,
      readonly options: Record<string, unknown> = {},
    ) {
      FakeCanvas.instances.push(this);
    }

    on(eventName: string, listener: Listener): () => void {
      const listeners = this.listeners.get(eventName) ?? new Set<Listener>();
      listeners.add(listener);
      this.listeners.set(eventName, listeners);
      return () => {
        listeners.delete(listener);
        if (listeners.size === 0) this.listeners.delete(eventName);
      };
    }

    off(eventName: string, listener?: Listener): void {
      if (listener === undefined) {
        this.listeners.delete(eventName);
      } else {
        this.listeners.get(eventName)?.delete(listener);
      }
    }

    emit(eventName: string, event: Record<string, unknown>): void {
      for (const listener of [...(this.listeners.get(eventName) ?? [])]) {
        listener(event);
      }
    }

    listenerCount(): number {
      return [...this.listeners.values()].reduce(
        (count, listeners) => count + listeners.size,
        0,
      );
    }

    add(...objects: FakeFabricObject[]): number {
      this.addBatches.push(objects);
      for (const object of objects) {
        object.canvas = this;
        this.objects.push(object);
        this.emit("object:added", { target: object });
      }
      return this.objects.length;
    }

    moveObjectTo(object: FakeFabricObject, index: number): boolean {
      const current = this.objects.indexOf(object);
      if (current === -1) return false;
      this.objects.splice(current, 1);
      this.objects.splice(index, 0, object);
      return current !== index;
    }

    contains(object: FakeFabricObject): boolean {
      return this.objects.includes(object);
    }

    remove(...objects: FakeFabricObject[]): FakeFabricObject[] {
      this.removeBatches.push(objects);
      for (const object of objects) {
        const index = this.objects.indexOf(object);
        if (index !== -1) this.objects.splice(index, 1);
        this.emit("object:removed", { target: object });
        object.canvas = null;
      }
      return objects;
    }

    clear(): void {
      this.clearCalls += 1;
      this.objects.length = 0;
    }

    requestRenderAll(): void {
      this.renderRequests += 1;
    }

    setViewportTransform(transform: number[]): void {
      this.viewportTransform = [...transform];
      this.viewportTransforms.push([...transform]);
    }

    getZoom(): number {
      return this.viewportTransform[0] ?? 1;
    }

    getWidth(): number {
      return 800;
    }

    getHeight(): number {
      return 600;
    }

    dispose(): Promise<boolean> {
      this.disposeCalls += 1;
      return Promise.resolve(true);
    }
  }

  function reset(): void {
    FakeCanvas.instances.length = 0;
    imageLoads.length = 0;
  }

  return {
    FakeCanvas,
    FakeCircle,
    FakeFabricImage,
    FakeFabricObject,
    FakeLine,
    FakePoint,
    FakeRect,
    FakeTextbox,
    imageLoads,
    reset,
  };
});

vi.mock("fabric", () => ({
  Canvas: fabricHarness.FakeCanvas,
  Circle: fabricHarness.FakeCircle,
  FabricImage: fabricHarness.FakeFabricImage,
  Line: fabricHarness.FakeLine,
  Point: fabricHarness.FakePoint,
  Rect: fabricHarness.FakeRect,
  FabricText: fabricHarness.FakeTextbox,
  Textbox: fabricHarness.FakeTextbox,
}));

type FakeFabricObject = InstanceType<typeof fabricHarness.FakeFabricObject>;
type FakeCanvas = InstanceType<typeof fabricHarness.FakeCanvas>;

interface PresentationMetadata {
  key: string;
  role: "node" | "edge" | "port" | "board" | "product" | "text" | "background";
  domainId: string;
}

function metadata(object: FakeFabricObject): PresentationMetadata | undefined {
  return object.__canvasPresentation as PresentationMetadata | undefined;
}

function presentationObject(
  canvas: FakeCanvas,
  key: string,
): FakeFabricObject | undefined {
  return canvas.objects.find((object) => metadata(object)?.key === key);
}

function node(
  id: string,
  kind: CanvasNode["kind"] = "prompt",
  managedBy: CanvasNode["managedBy"] = null,
): CanvasNode {
  return {
    id,
    kind,
    managedBy,
    skuId: null,
    assetId: null,
    modelProfileId: null,
    prompt: null,
    compositionGroupId: null,
    textSnapshotId: null,
    outputBoardId: null,
    parameters: {},
  } as CanvasNode;
}

function project(
  nodes: CanvasNode[],
  options: {
    positions?: Record<string, { x: number; y: number }>;
    edges?: TypedEdge[];
    mode?: "complete-set" | "advanced";
  } = {},
): CanvasProjectState {
  const state = createEmptyProjectState();
  state.semanticState.nodes = nodes;
  state.semanticState.edges = options.edges ?? [];
  state.semanticState.mode = options.mode ?? "complete-set";
  state.layoutState.nodePositions = options.positions ?? {};
  return state;
}

function projectWithPendingImage(
  layerId: string,
  renderAssetId: string,
): CanvasProjectState {
  const state = project([node(`node-${layerId}`, "product_source")]);
  const groupId = `group-${layerId}`;
  const layout = {
    slot: { x: 0.1, y: 0.1, width: 0.8, height: 0.8 },
    anchor: { x: 0.5, y: 0.5 },
    baseline: 0.25,
    relativeProductFraction: 0.75,
    contain: true as const,
    safeArea: { top: 0.05, right: 0.05, bottom: 0.05, left: 0.05 },
    rotation: 12,
  };
  state.semanticState.compositionGroups.push({
    id: groupId,
    skuIds: [],
    productLayerIds: [layerId],
    layoutHash: compositionLayoutHash(layout),
    layout,
  });
  state.layoutState.objectTransforms[layerId] = {
    x: 0.5,
    y: 0.25,
    scale: 0.75,
    rotation: 12,
  };
  state.layoutState.productLayers.push({
    id: layerId,
    sourceAssetId: `source-${layerId}`,
    renderAssetId,
    allowOpaqueFallback: false,
    skuId: null,
    compositionGroupId: groupId,
    transformId: layerId,
    locked: true,
  });
  return state;
}

function mount(
  dispatch: (action: ProjectAction) => void = () => {},
): ReturnType<typeof createCanvasAdapter> {
  const adapter = createCanvasAdapter();
  adapter.mount(document.createElement("canvas"), dispatch);
  return adapter;
}

function assertWireSafe(value: unknown): void {
  const visit = (candidate: unknown): void => {
    expect(candidate).not.toBeInstanceOf(fabricHarness.FakeFabricObject);
    expect(candidate).not.toBeInstanceOf(Blob);
    expect(typeof candidate).not.toBe("function");
    if (Array.isArray(candidate)) {
      candidate.forEach(visit);
    } else if (candidate !== null && typeof candidate === "object") {
      Object.values(candidate).forEach(visit);
    }
  };
  visit(value);
  expect(() => JSON.stringify(value)).not.toThrow();
}

describe("CanvasAdapter contract", () => {
  beforeEach(() => {
    fabricHarness.reset();
  });

  test("constructs only the narrow public adapter boundary", () => {
    const adapter = createCanvasAdapter();

    expect(Object.keys(adapter).sort()).toEqual([
      "cancelPendingLoads",
      "dispose",
      "focusBoard",
      "mount",
      "project",
      "setMode",
      "setResultBackgroundPreview",
    ]);
    expect("serialize" in adapter).toBe(false);
    expect("toJSON" in adapter).toBe(false);
  });

  test("the canvas entrypoint publishes the isolated adapter factory", () => {
    expect(createCanvasAdapterFromMain).toBe(createCanvasAdapter);
  });

  test("requires one explicit mount", () => {
    const adapter = createCanvasAdapter();
    const element = document.createElement("canvas");

    expect(() => adapter.project(null, createEmptyProjectState())).toThrow(
      /mount/i,
    );
    adapter.mount(element, () => {});
    expect(() => adapter.mount(element, () => {})).toThrow(/already mounted/i);
  });

  test("projects stable domain IDs through incremental add, move, update, and remove", () => {
    const adapter = mount();
    const previous = project([node("node-a"), node("node-b")], {
      positions: {
        "node-a": { x: 0.1, y: 0.2 },
        "node-b": { x: 0.3, y: 0.4 },
      },
    });
    adapter.project(null, previous);
    const canvas = fabricHarness.FakeCanvas.instances[0];
    if (canvas === undefined) throw new Error("expected fake Fabric canvas");
    const originalA = presentationObject(canvas, "node:node-a");
    const originalB = presentationObject(canvas, "node:node-b");
    if (originalA === undefined || originalB === undefined) {
      throw new Error("expected projected nodes");
    }

    const next = structuredClone(previous);
    next.semanticState.nodes = next.semanticState.nodes.filter(
      (candidate) => candidate.id !== "node-b",
    );
    const updatedA = next.semanticState.nodes.find(
      (candidate) => candidate.id === "node-a",
    );
    if (updatedA === undefined) throw new Error("expected node-a");
    updatedA.prompt = "updated prompt";
    next.semanticState.nodes.push(node("node-c", "model_generation"));
    next.layoutState.nodePositions["node-a"] = { x: 0.75, y: -0.4 };
    next.layoutState.nodePositions["node-c"] = { x: 1.2, y: 1.4 };
    delete next.layoutState.nodePositions["node-b"];

    adapter.project(previous, next);

    expect(canvas.clearCalls).toBe(0);
    expect(presentationObject(canvas, "node:node-a")).toBe(originalA);
    expect(originalA.left).toBe(0.75);
    expect(originalA.top).toBe(-0.4);
    expect(originalA.label).toContain("updated prompt");
    expect(presentationObject(canvas, "node:node-b")).toBeUndefined();
    expect(canvas.removeBatches.flat()).toContain(originalB);
    expect(presentationObject(canvas, "node:node-c")).toBeDefined();
  });

  test("Fabric add, modify, and remove events emit only closed typed actions", () => {
    const actions: ProjectAction[] = [];
    const adapter = mount((action) => actions.push(action));
    const output = node("output-main", "main_output", "complete-set");
    const state = project([output], {
      positions: { "output-main": { x: 0.2, y: 0.3 } },
    });

    adapter.project(null, state);
    const canvas = fabricHarness.FakeCanvas.instances[0];
    const target =
      canvas === undefined
        ? undefined
        : presentationObject(canvas, "node:output-main");
    if (canvas === undefined || target === undefined) {
      throw new Error("expected projected output node");
    }
    expect(actions).toEqual([]);

    canvas.emit("object:added", { target });
    target.set({ left: 0.8, top: -0.4 });
    canvas.emit("object:removed", { target });

    expect(actions).toEqual([
      { type: "node/add", node: output },
      {
        type: "node/move",
        nodeId: "output-main",
        position: { x: 0.8, y: -0.4 },
      },
      { type: "output/disable", outputType: "main" },
    ]);
    actions.forEach(assertWireSafe);
  });

  test("adapter projection events never feed back into dispatch", () => {
    const actions: ProjectAction[] = [];
    const adapter = mount((action) => actions.push(action));
    const previous = project([node("node-a"), node("node-b")], {
      positions: {
        "node-a": { x: 0, y: 0 },
        "node-b": { x: 1, y: 1 },
      },
    });
    adapter.project(null, previous);
    const next = project([node("node-a"), node("node-c")], {
      positions: {
        "node-a": { x: 20, y: -30 },
        "node-c": { x: 40, y: 50 },
      },
    });

    adapter.project(previous, next);

    expect(actions).toEqual([]);
  });

  test("complete-set hides ports and edges while advanced reuses the same topology", () => {
    const adapter = mount();
    const edge: TypedEdge = {
      id: "edge-a-b",
      kind: "prompt",
      sourceNodeId: "node-a",
      sourcePort: "prompt",
      targetNodeId: "node-b",
      targetPort: "prompt",
      skuId: null,
    };
    const state = project(
      [node("node-a", "prompt"), node("node-b", "model_generation")],
      {
        positions: {
          "node-a": { x: 0.1, y: 0.2 },
          "node-b": { x: 0.8, y: 0.2 },
        },
        edges: [edge],
      },
    );
    adapter.project(null, state);
    const canvas = fabricHarness.FakeCanvas.instances[0];
    if (canvas === undefined) throw new Error("expected fake Fabric canvas");
    const topology = canvas.objects.filter((object) => {
      const role = metadata(object)?.role;
      return role === "edge" || role === "port";
    });
    expect(topology.length).toBeGreaterThan(0);
    expect(topology.every((object) => object.visible === false)).toBe(true);

    adapter.setMode("advanced");

    expect(
      topology.every(
        (object) =>
          canvas.objects.includes(object) && object.visible === true,
      ),
    ).toBe(true);

    adapter.setMode("complete-set");
    expect(topology.every((object) => object.visible === false)).toBe(true);
  });

  test("projects every authoritative line independently with frame anchors and fixed z order", () => {
    const state = projectWithPendingImage("product-a", "render-a");
    const belowNode = node("below-node", "text_layer");
    belowNode.textSnapshotId = "below-text";
    const aboveNode = node("above-node", "text_layer");
    aboveNode.textSnapshotId = "above-text";
    state.semanticState.nodes.push(belowNode, aboveNode);
    const common = {
      fontAssetId: null,
      fontFamily: "Noto Sans CJK SC" as const,
      fontVersion: "sha256:2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b" as const,
      boxWidth: 200,
      fontSize: 20,
      color: "#112233",
      letterSpacing: 2,
      lineHeight: 1.2,
      align: "center" as const,
      baseline: "middle" as const,
    };
    state.layoutState.textSnapshots.push(
      {
        ...common,
        id: "below-text",
        nodeId: belowNode.id,
        content: "below one\nbelow two",
        lines: [
          { text: "below one", x: 20, y: 30, width: 80 },
          { text: "below two", x: 40, y: 60, width: 0 },
        ],
        zBand: "below-product",
        sortOrder: 2,
      },
      {
        ...common,
        id: "above-text",
        nodeId: aboveNode.id,
        content: "above",
        lines: [{ text: "above", x: 60, y: 90, width: 100 }],
        zBand: "above-product",
        sortOrder: 1,
      },
    );

    const overlay = createPresentationPlan(state).descriptors.filter(
      (descriptor) => descriptor.role === "product" || descriptor.role === "text",
    );
    expect(overlay.map((descriptor) => descriptor.key)).toEqual([
      "text:below-text:line:0",
      "text:below-text:line:1",
      "product:product-a",
      "text:above-text:line:0",
    ]);
    expect(overlay[0]?.properties).toMatchObject({
      text: "below one",
      left: 60,
      top: 20,
      lineFrameWidth: 80,
      originX: "center",
      originY: "top",
      fontFamily: "Noto Sans CJK SC",
      charSpacing: 100,
    });
    expect(overlay[1]?.properties).toMatchObject({
      text: "below two",
      left: 140,
      lineFrameWidth: 200,
      top: 50,
    });
    expect(overlay[0]?.properties).not.toHaveProperty("textBaseline");
  });

  test("updates an explicit FabricText line in place when its snapshot changes", () => {
    const adapter = mount();
    const previous = project([node("text-node", "text_layer")], {
      positions: { "text-node": { x: 0.2, y: 0.3 } },
    });
    previous.layoutState.textSnapshots.push({
      id: "text-snapshot-a",
      nodeId: "text-node",
      content: "Before",
      fontAssetId: null,
      fontFamily: "Noto Sans CJK SC",
      fontVersion: "sha256:2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b",
      boxWidth: 240,
      lines: [{ text: "Before", x: 0, y: 0, width: 120 }],
      fontSize: 32,
      color: "#111111",
      letterSpacing: 0,
      lineHeight: 1.2,
      align: "left",
      baseline: "alphabetic",
      zBand: "above-product",
      sortOrder: 0,
    });
    adapter.project(null, previous);
    const canvas = fabricHarness.FakeCanvas.instances[0];
    const textbox =
      canvas === undefined
        ? undefined
        : presentationObject(canvas, "text:text-snapshot-a:line:0");
    if (canvas === undefined || textbox === undefined) {
      throw new Error("expected projected Textbox");
    }
    expect(textbox.text).toBe("Before");

    const next = structuredClone(previous);
    const snapshot = next.layoutState.textSnapshots[0];
    if (snapshot === undefined) throw new Error("expected text snapshot");
    snapshot.content = "After";
    snapshot.lines = [{ text: "After", x: 0, y: 0, width: 100 }];

    adapter.project(previous, next);

    expect(presentationObject(canvas, "text:text-snapshot-a:line:0")).toBe(textbox);
    expect(textbox.text).toBe("After");
  });

  test("pan and zoom ignore canvas dimensions but enforce inclusive numeric safety", () => {
    const limits = {
      minPan: -100,
      maxPan: 100,
      minZoom: 0.25,
      maxZoom: 4,
    };
    const atBoundary = panViewport(
      { x: 0, y: 0, zoom: 1 },
      { x: 100, y: -100 },
      limits,
    );
    expect(atBoundary).toEqual({ x: 100, y: -100, zoom: 1 });
    expect(
      panViewport(atBoundary, { x: 1, y: -1 }, limits),
    ).toEqual({ x: 100, y: -100, zoom: 1 });
    expect(zoomViewport(atBoundary, 4, limits).zoom).toBe(4);
    expect(zoomViewport(atBoundary, 5, limits).zoom).toBe(4);
    expect(DEFAULT_VIEWPORT_SAFETY.maxPan).toBeGreaterThan(10_000);
    expect(() =>
      panViewport(atBoundary, { x: Number.NaN, y: 0 }, limits),
    ).toThrow(/finite/i);
    expect(() => zoomViewport(atBoundary, Number.POSITIVE_INFINITY, limits)).toThrow(
      /finite/i,
    );
  });

  test("Fabric gestures use numeric viewport safety without canvas-size clamping", () => {
    const dispatch = vi.fn();
    const adapter = mount(dispatch);
    adapter.project(null, createEmptyProjectState());
    const canvas = fabricHarness.FakeCanvas.instances[0];
    if (canvas === undefined) throw new Error("expected fake Fabric canvas");

    canvas.emit("mouse:down", {
      e: { altKey: true, button: 0, clientX: 0, clientY: 0 },
    });
    canvas.emit("mouse:move", {
      e: { altKey: true, button: 0, clientX: 20_000, clientY: -30_000 },
    });
    canvas.emit("mouse:up", {
      e: { altKey: true, button: 0, clientX: 20_000, clientY: -30_000 },
    });
    expect(canvas.viewportTransform).toEqual([
      1,
      0,
      0,
      1,
      20_000,
      -30_000,
    ]);
    expect(dispatch).toHaveBeenLastCalledWith({
      type: "viewport/set",
      viewport: { x: 20_000, y: -30_000, zoom: 1 },
    });

    const preventDefault = vi.fn();
    canvas.emit("mouse:wheel", {
      e: { deltaY: -10_000, preventDefault },
    });
    expect(canvas.viewportTransform[0]).toBe(DEFAULT_VIEWPORT_SAFETY.maxZoom);
    expect(dispatch).toHaveBeenLastCalledWith({
      type: "viewport/set",
      viewport: {
        x: 20_000,
        y: -30_000,
        zoom: DEFAULT_VIEWPORT_SAFETY.maxZoom,
      },
    });
    expect(preventDefault).toHaveBeenCalledOnce();
    expect(() =>
      canvas.emit("mouse:wheel", {
        e: { deltaY: Number.POSITIVE_INFINITY, preventDefault: vi.fn() },
      }),
    ).toThrow(/finite/i);
  });

  test("focusBoard centers the board's mapped domain object without size clamping", () => {
    const adapter = mount();
    const output = node("output-node", "main_output", "complete-set");
    const state = project([output], {
      positions: { "output-node": { x: 1_200, y: -900 } },
    });
    state.semanticState.outputBoards.push({
      id: "board-a",
      outputNodeId: "output-node",
      outputType: "main",
      skuId: null,
      sortOrder: 0,
      selectedResultAssetId: null,
    });
    state.layoutState.viewport = { x: 99, y: 99, zoom: 2 };
    adapter.project(null, state);
    const canvas = fabricHarness.FakeCanvas.instances[0];
    if (canvas === undefined) throw new Error("expected fake Fabric canvas");

    adapter.focusBoard("board-a");

    expect(canvas.viewportTransform).toEqual([2, 0, 0, 2, -2_000, 2_100]);
    expect(() => adapter.focusBoard("missing-board")).toThrow(/unknown output board/i);
  });

  test("product images load the matching preview content endpoint", () => {
    const adapter = mount();
    adapter.project(null, projectWithPendingImage("layer-a", "render-a"));

    expect(fabricHarness.imageLoads).toHaveLength(1);
    expect(fabricHarness.imageLoads[0]?.url).toBe(
      "/api/canvas/assets/render-a/content?variant=preview",
    );
    adapter.dispose();
  });

  test("projects only the selected result background preview beneath the editable product", () => {
    const adapter = mount();
    adapter.project(null, projectWithPendingImage("layer-a", "render-a"));
    if (adapter.setResultBackgroundPreview === undefined) {
      throw new Error("result background preview projection is unavailable");
    }

    adapter.setResultBackgroundPreview("background-preview-a");

    expect(fabricHarness.imageLoads.map((load) => load.url)).toEqual([
      "/api/canvas/assets/render-a/content?variant=preview",
      "/api/canvas/assets/background-preview-a/content?variant=preview",
    ]);
    expect(fabricHarness.imageLoads.map((load) => load.url).join(" ")).not.toContain("composed");
  });

  test("system product and auto-cutout nodes are never Fabric-selectable", () => {
    const adapter = mount();
    const state = projectWithPendingImage("main-product", "render-a");
    state.semanticState.nodes = [
      { ...node("main-product-source", "product_source"), assetId: "source-main-product" },
      { ...node("main-product-cutout", "auto_cutout"), assetId: "render-a" },
    ];
    state.semanticState.edges = [{
      id: "main-product-source-cutout", kind: "product_asset",
      sourceNodeId: "main-product-source", sourcePort: "product",
      targetNodeId: "main-product-cutout", targetPort: "reference", skuId: null,
    }];
    state.layoutState.nodePositions = {
      "main-product-source": { x: 120, y: 160 },
      "main-product-cutout": { x: 320, y: 160 },
    };
    state.semanticState.mode = "advanced";

    adapter.project(null, state);
    const canvas = fabricHarness.FakeCanvas.instances[0];
    if (canvas === undefined) throw new Error("expected fake Fabric canvas");

    for (const key of ["node:main-product-source", "node:main-product-cutout"]) {
      expect(presentationObject(canvas, key)).toMatchObject({
        selectable: false,
        evented: false,
      });
    }
  });

  test("object:removed resolves locked nodes by registry identity and preserves authoritative order", async () => {
    const actions: ProjectAction[] = [];
    const adapter = mount((action) => actions.push(action));
    const state = projectWithPendingImage("main-product", "render-a");
    state.semanticState.nodes = [
      { ...node("main-product-source", "product_source"), assetId: "source-main-product" },
      { ...node("main-product-cutout", "auto_cutout"), assetId: "render-a" },
      node("ordinary", "prompt"),
    ];
    state.semanticState.edges = [{
      id: "main-product-source-cutout", kind: "product_asset",
      sourceNodeId: "main-product-source", sourcePort: "product",
      targetNodeId: "main-product-cutout", targetPort: "reference", skuId: null,
    }];
    state.layoutState.nodePositions = {
      "main-product-source": { x: 120, y: 160 },
      "main-product-cutout": { x: 320, y: 160 },
      ordinary: { x: 520, y: 160 },
    };
    state.semanticState.mode = "advanced";
    adapter.project(null, state);
    const canvas = fabricHarness.FakeCanvas.instances[0];
    const productLoad = fabricHarness.imageLoads[0];
    if (canvas === undefined || productLoad === undefined) {
      throw new Error("expected fake Fabric canvas and pending product");
    }

    const orderedKeys = (): string[] => canvas.objects.map((object) => {
      const key = metadata(object)?.key;
      if (key === undefined) throw new Error("expected restored presentation metadata");
      return key;
    });
    const beforeKeys = orderedKeys();
    expect(beforeKeys).toEqual([
      "node:main-product-source",
      "node:main-product-cutout",
      "node:ordinary",
      "edge:main-product-source-cutout",
      "port:main-product-source-cutout:source",
      "port:main-product-source-cutout:target",
    ]);

    const systemProduct = presentationObject(canvas, "node:main-product-source");
    const systemCutout = presentationObject(canvas, "node:main-product-cutout");
    const ordinary = presentationObject(canvas, "node:ordinary");
    if (systemProduct === undefined || systemCutout === undefined || ordinary === undefined) {
      throw new Error("expected all projected nodes");
    }

    delete systemProduct.__canvasPresentation;
    canvas.remove(systemProduct);
    expect(canvas.objects).toContain(systemProduct);
    expect(orderedKeys()).toEqual(beforeKeys);

    systemCutout.__canvasPresentation = {
      key: "node:ordinary",
      role: "node",
      domainId: "ordinary",
      node: node("ordinary", "prompt"),
    };
    canvas.remove(systemCutout);
    expect(canvas.objects).toContain(systemCutout);
    expect(orderedKeys()).toEqual(beforeKeys);

    ordinary.__canvasPresentation = {
      key: "node:ordinary",
      role: "node",
      domainId: "ordinary",
      node: node("ordinary", "auto_cutout", "complete-set"),
    };
    canvas.remove(ordinary);
    expect(canvas.objects).not.toContain(ordinary);
    expect(orderedKeys()).toEqual(beforeKeys.filter((key) => key !== "node:ordinary"));

    const product = new fabricHarness.FakeFabricImage();
    productLoad.resolve(product);
    await Promise.resolve();
    await Promise.resolve();

    expect(orderedKeys()).toEqual([
      "node:main-product-source",
      "node:main-product-cutout",
      "edge:main-product-source-cutout",
      "port:main-product-source-cutout:source",
      "port:main-product-source-cutout:target",
      "product:main-product",
    ]);
    expect(new Set(canvas.objects).size).toBe(canvas.objects.length);
    expect(actions).toEqual([]);
  });

  test("locked product rejects direct transform, crop, skew, flip, filter, color, and deletion", async () => {
    const actions: ProjectAction[] = [];
    const adapter = mount((action) => actions.push(action));
    const state = projectWithPendingImage("layer-a", "render-a");
    state.layoutState.productLayers[0].locked = true;
    adapter.project(null, state);
    const canvas = fabricHarness.FakeCanvas.instances[0];
    const load = fabricHarness.imageLoads[0];
    if (canvas === undefined || load === undefined) throw new Error("expected product load");
    const image = new fabricHarness.FakeFabricImage();
    load.resolve(image);
    await Promise.resolve();
    await Promise.resolve();

    Object.assign(image, {
      left: 999,
      top: 999,
      scaleX: 0.2,
      scaleY: 1.7,
      cropX: 10,
      cropY: 20,
      skewX: 12,
      skewY: 8,
      flipX: true,
      flipY: true,
      filters: [{ unsafe: true }],
      opacity: 0.3,
      globalCompositeOperation: "multiply",
    });
    canvas.emit("object:modified", { target: image });

    expect(image).toMatchObject({
      left: 0.5,
      top: 0.25,
      scaleX: 0.75,
      scaleY: 0.75,
      angle: 12,
      cropX: 0,
      cropY: 0,
      skewX: 0,
      skewY: 0,
      flipX: false,
      flipY: false,
      filters: [],
      opacity: 1,
      globalCompositeOperation: "source-over",
    });
    canvas.remove(image);
    expect(canvas.objects).toContain(image);
    expect(actions).toEqual([]);
  });

  test("switching projects cancels loads, removes listeners, disposes, and rejects late images", async () => {
    const adapter = mount();
    const oldProject = projectWithPendingImage("old-layer", "old-render");
    adapter.project(null, oldProject);
    const oldCanvas = fabricHarness.FakeCanvas.instances[0];
    const oldLoad = fabricHarness.imageLoads[0];
    if (oldCanvas === undefined || oldLoad === undefined) {
      throw new Error("expected old canvas and pending image");
    }
    expect(oldCanvas.listenerCount()).toBeGreaterThan(0);
    expect(oldLoad.signal?.aborted).toBe(false);

    const nextProject = projectWithPendingImage("new-layer", "new-render");
    adapter.project(null, nextProject);

    const newCanvas = fabricHarness.FakeCanvas.instances[1];
    const newLoad = fabricHarness.imageLoads[1];
    if (newCanvas === undefined || newLoad === undefined) {
      throw new Error("expected remounted canvas and pending image");
    }
    expect(oldLoad.signal?.aborted).toBe(true);
    expect(oldCanvas.listenerCount()).toBe(0);
    expect(oldCanvas.disposeCalls).toBe(1);
    expect(newCanvas.listenerCount()).toBeGreaterThan(0);

    oldLoad.resolve(new fabricHarness.FakeFabricImage());
    await Promise.resolve();
    await Promise.resolve();
    expect(presentationObject(newCanvas, "product:old-layer")).toBeUndefined();

    adapter.dispose();
    adapter.dispose();
    expect(newLoad.signal?.aborted).toBe(true);
    expect(newCanvas.listenerCount()).toBe(0);
    expect(newCanvas.disposeCalls).toBe(1);

    newLoad.resolve(new fabricHarness.FakeFabricImage());
    await Promise.resolve();
    await Promise.resolve();
    expect(presentationObject(newCanvas, "product:new-layer")).toBeUndefined();
  });

  test("superseding a pending product fingerprint releases the late image and adds the latest once", async () => {
    const adapter = mount();
    const previous = projectWithPendingImage("layer-a", "render-old");
    adapter.project(null, previous);
    const next = projectWithPendingImage("layer-a", "render-new");
    const nextLayer = next.layoutState.productLayers[0];
    if (nextLayer === undefined) throw new Error("expected next product layer");
    nextLayer.sourceAssetId = "source-new";

    adapter.project(previous, next);
    adapter.project(next, next);

    const canvas = fabricHarness.FakeCanvas.instances[0];
    const oldLoad = fabricHarness.imageLoads[0];
    const newLoad = fabricHarness.imageLoads[1];
    if (canvas === undefined || oldLoad === undefined || newLoad === undefined) {
      throw new Error("expected superseded and current image loads");
    }
    expect(fabricHarness.imageLoads).toHaveLength(2);
    expect(oldLoad.signal?.aborted).toBe(true);

    const staleImage = new fabricHarness.FakeFabricImage();
    oldLoad.resolve(staleImage);
    await Promise.resolve();
    await Promise.resolve();
    expect(presentationObject(canvas, "product:layer-a")).toBeUndefined();
    expect(staleImage.disposeCalls).toBe(1);

    adapter.setMode("complete-set");
    const latestImage = new fabricHarness.FakeFabricImage();
    newLoad.resolve(latestImage);
    await Promise.resolve();
    await Promise.resolve();
    expect(presentationObject(canvas, "product:layer-a")).toBe(latestImage);
    expect(canvas.addBatches.flat().filter((object) => object === latestImage)).toHaveLength(1);
    expect(latestImage.visible).toBe(true);
  });

  test("a resolved product image is removed and disposed before its fingerprint reload", async () => {
    const adapter = mount();
    const previous = projectWithPendingImage("layer-a", "render-old");
    adapter.project(null, previous);
    const canvas = fabricHarness.FakeCanvas.instances[0];
    const oldLoad = fabricHarness.imageLoads[0];
    if (canvas === undefined || oldLoad === undefined) {
      throw new Error("expected initial image load");
    }
    const oldImage = new fabricHarness.FakeFabricImage();
    oldLoad.resolve(oldImage);
    await Promise.resolve();
    await Promise.resolve();
    expect(presentationObject(canvas, "product:layer-a")).toBe(oldImage);

    const next = projectWithPendingImage("layer-a", "render-new");
    const nextLayer = next.layoutState.productLayers[0];
    if (nextLayer === undefined) throw new Error("expected next product layer");
    nextLayer.sourceAssetId = "source-new";
    next.layoutState.objectTransforms["layer-a"] = {
      x: 0.4,
      y: 0.8,
      scale: 0.5,
      rotation: 90,
    };
    const nextGroup = next.semanticState.compositionGroups[0];
    if (nextGroup === undefined) throw new Error("expected composition group");
    nextGroup.layout = {
      ...structuredClone(nextGroup.layout),
      slot: { ...nextGroup.layout.slot, x: 0, width: 0.8 },
      anchor: { ...nextGroup.layout.anchor, x: 0.5 },
      baseline: 0.8,
      relativeProductFraction: 0.5,
      rotation: 90,
    };
    nextGroup.layoutHash = compositionLayoutHash(nextGroup.layout);

    adapter.project(previous, next);

    expect(canvas.objects).not.toContain(oldImage);
    expect(canvas.removeBatches.flat()).toContain(oldImage);
    expect(oldImage.disposeCalls).toBe(1);
    expect(fabricHarness.imageLoads).toHaveLength(2);
    const newLoad = fabricHarness.imageLoads[1];
    if (newLoad === undefined) throw new Error("expected refreshed image load");
    const newImage = new fabricHarness.FakeFabricImage();
    newLoad.resolve(newImage);
    await Promise.resolve();
    await Promise.resolve();
    expect(presentationObject(canvas, "product:layer-a")).toBe(newImage);
    expect(newImage.left).toBe(0.4);
    expect(newImage.top).toBe(0.8);
  });

  test("cancelPendingLoads aborts current image work without disposing the canvas", () => {
    const adapter = mount();
    adapter.project(null, projectWithPendingImage("layer-a", "render-a"));
    const canvas = fabricHarness.FakeCanvas.instances[0];
    const load = fabricHarness.imageLoads[0];
    if (canvas === undefined || load === undefined) {
      throw new Error("expected pending image");
    }

    adapter.cancelPendingLoads();

    expect(load.signal?.aborted).toBe(true);
    expect(canvas.disposeCalls).toBe(0);
  });

  test("validates domain state before object creation", () => {
    const adapter = mount();
    const invalid = createEmptyProjectState();
    invalid.layoutState.viewport.x = Number.NaN;
    const canvas = fabricHarness.FakeCanvas.instances[0];
    if (canvas === undefined) throw new Error("expected fake Fabric canvas");

    expect(() => adapter.project(null, invalid)).toThrow(/finite/i);
    expect(canvas.objects).toEqual([]);
  });

  test("main optionally mounts and wires an adapter without storing Fabric state", () => {
    document.body.innerHTML = '<div id="canvas-app"></div>';
    const store = createProjectStore();
    const element = document.createElement("canvas");
    let wiredDispatch: Dispatch | undefined;
    const adapter: CanvasAdapter = {
      mount: vi.fn((_element, dispatch) => {
        wiredDispatch = dispatch;
      }),
      project: vi.fn(),
      setMode: vi.fn(),
      focusBoard: vi.fn(),
      cancelPendingLoads: vi.fn(),
      dispose: vi.fn(),
    };

    const mounted = mountCanvas(store, { adapter, element });

    expect(mounted).toBe(store);
    expect(document.querySelector("#canvas-app")?.contains(element)).toBe(true);
    expect(adapter.mount).toHaveBeenCalledWith(element, expect.any(Function));
    expect(adapter.project).toHaveBeenCalledWith(
      null,
      store.getState().project,
    );
    expect(adapter.setMode).toHaveBeenCalledWith("complete-set");
    if (wiredDispatch === undefined) throw new Error("expected adapter dispatch");

    wiredDispatch({ type: "mode/set", mode: "advanced" });

    expect(store.getState().project.semanticState.mode).toBe("advanced");
    expect(adapter.project).toHaveBeenCalledTimes(2);
    expect(JSON.stringify(store.getState())).not.toContain("FakeCanvas");
  });

  test("main rejects a second mount before mutating the existing canvas DOM", () => {
    document.body.innerHTML = '<div id="canvas-app"></div>';
    const root = document.querySelector<HTMLElement>("#canvas-app");
    if (root === null) throw new Error("expected canvas root");
    const firstElement = document.createElement("canvas");
    const firstAdapter: CanvasAdapter = {
      mount: vi.fn(),
      project: vi.fn(),
      setMode: vi.fn(),
      focusBoard: vi.fn(),
      cancelPendingLoads: vi.fn(),
      dispose: vi.fn(),
    };
    mountCanvas(createProjectStore(), {
      adapter: firstAdapter,
      element: firstElement,
    });
    const observer = new MutationObserver(() => {});
    observer.observe(root, { childList: true });
    const secondElement = document.createElement("canvas");
    const secondAdapter: CanvasAdapter = {
      mount: vi.fn(),
      project: vi.fn(),
      setMode: vi.fn(),
      focusBoard: vi.fn(),
      cancelPendingLoads: vi.fn(),
      dispose: vi.fn(),
    };

    expect(() =>
      mountCanvas(createProjectStore(), {
        adapter: secondAdapter,
        element: secondElement,
      }),
    ).toThrow(/already mounted/i);

    expect(root.firstElementChild).toBe(firstElement);
    expect(observer.takeRecords()).toEqual([]);
    expect(secondAdapter.mount).not.toHaveBeenCalled();
    expect(firstAdapter.dispose).not.toHaveBeenCalled();
    observer.disconnect();
  });

  test("domain, state, and main modules never import Fabric", () => {
    const sources = [
      domainTypesSource,
      domainValidationSource,
      projectStoreSource,
      mainSource,
    ];

    for (const source of sources) {
      expect(source).not.toMatch(/from\s+["']fabric["']/);
      expect(source).not.toMatch(/import\s*\(["']fabric["']\)/);
    }
  });
});
