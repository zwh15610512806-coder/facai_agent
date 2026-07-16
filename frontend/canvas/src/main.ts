import "./styles.css";

import {
  createCanvasApi,
  type CanvasApi,
} from "./api/client";
import { createAssetsApi, type AssetsApi } from "./api/assets";
import { createCompositionsApi, type CompositionsApi } from "./api/compositions";
import { createGenerationsApi, type GenerationsApi } from "./api/generations";
import { createExportsApi, type ExportsApi } from "./api/exports";
import {
  openProjectEvents,
  type CanvasProjectEvent,
  type ProjectEventStream,
} from "./api/events";
import { createSkusApi, type SkusApi } from "./api/skus";
import { createProvidersApi, type ProvidersApi } from "./api/providers";
import type {
  CanvasAdapter,
  Dispatch,
} from "./canvas/canvas-adapter";
import { createCanvasAdapter } from "./canvas/canvas-adapter";
export { createCanvasAdapter } from "./canvas/canvas-adapter";
import { mountWorkspace } from "./components/workspace";
import { createAutosaveController } from "./controllers/autosave-controller";
import {
  createProjectController,
  type ProjectController,
} from "./controllers/project-controller";
import {
  createProjectStore,
  type ProjectStore,
} from "./state/project-store";
import { loadPinnedCanvasFont } from "./domain/text-layout";

const LOADING_SHELL =
  '<main class="canvas-shell" data-canvas-state="loading" aria-busy="true"><p>Loading Product Canvas...</p></main>';
const mountedRoots = new WeakSet<HTMLElement>();

export interface CanvasBootstrap {
  apiBase: string;
  projectId: string | null;
}

export interface CanvasApplication {
  ready: Promise<void>;
  store: ProjectStore;
  controller: ProjectController;
  dispose(): void;
}

export interface StartCanvasApplicationOptions {
  bootstrap: CanvasBootstrap;
  root?: HTMLElement;
  api?: CanvasApi;
  assetsApi?: AssetsApi;
  compositionsApi?: CompositionsApi;
  skusApi?: SkusApi;
  providersApi?: ProvidersApi;
  generationsApi?: GenerationsApi;
  exportsApi?: ExportsApi;
  adapter?: CanvasAdapter;
  openEvents?: (
    projectId: string,
    onEvent: (event: CanvasProjectEvent) => void,
  ) => ProjectEventStream;
  syncUrl?: (projectId: string | null) => void;
  loadFont?: () => Promise<void>;
}

export interface CanvasMountOptions {
  adapter: CanvasAdapter;
  element?: HTMLCanvasElement;
}

export function mountCanvas(
  store: ProjectStore = createProjectStore(),
  options?: CanvasMountOptions,
): ProjectStore {
  const root = document.querySelector<HTMLElement>("#canvas-app");
  if (root === null) {
    throw new Error('Product Canvas mount point "#canvas-app" was not found.');
  }
  if (mountedRoots.has(root)) {
    throw new Error("Product Canvas is already mounted in #canvas-app.");
  }

  if (options !== undefined) {
    const element = options.element ?? document.createElement("canvas");
    element.dataset.canvasSurface = "product-canvas";
    root.replaceChildren(element);
    const dispatch: Dispatch = (action) => {
      const previous = store.getState().project;
      const result = store.dispatch(action);
      if (result.applied) {
        options.adapter.project(previous, store.getState().project);
      }
    };
    options.adapter.mount(element, dispatch);
    const initialProject = store.getState().project;
    options.adapter.project(null, initialProject);
    options.adapter.setMode(initialProject.semanticState.mode);
    mountedRoots.add(root);
    return store;
  }

  root.innerHTML = LOADING_SHELL;
  mountedRoots.add(root);
  return store;
}

function defaultSyncUrl(projectId: string | null): void {
  const path =
    projectId === null
      ? "/app/canvas"
      : `/app/canvas/${encodeURIComponent(projectId)}`;
  if (window.location.pathname !== path) {
    window.history.replaceState(null, "", path);
  }
}

export function startCanvasApplication({
  bootstrap,
  root = document.querySelector<HTMLElement>("#canvas-app") ?? undefined,
  api = createCanvasApi({ apiBase: bootstrap.apiBase }),
  assetsApi = createAssetsApi({ apiBase: bootstrap.apiBase }),
  compositionsApi = createCompositionsApi({ apiBase: bootstrap.apiBase }),
  skusApi = createSkusApi({ apiBase: bootstrap.apiBase }),
  providersApi = createProvidersApi({ apiBase: bootstrap.apiBase }),
  generationsApi = createGenerationsApi({ apiBase: bootstrap.apiBase }),
  exportsApi = createExportsApi({ apiBase: bootstrap.apiBase }),
  adapter = createCanvasAdapter(),
  openEvents = (projectId, onEvent) =>
    openProjectEvents({
      apiBase: bootstrap.apiBase,
      projectId,
      onEvent,
    }),
  syncUrl = defaultSyncUrl,
  loadFont = loadPinnedCanvasFont,
}: StartCanvasApplicationOptions): CanvasApplication {
  if (root === undefined) {
    throw new Error('Product Canvas mount point "#canvas-app" was not found.');
  }
  if (mountedRoots.has(root)) {
    throw new Error("Product Canvas is already mounted in #canvas-app.");
  }
  mountedRoots.add(root);
  root.innerHTML = LOADING_SHELL;

  const store = createProjectStore();
  const eventSubscribers = new Set<(event: CanvasProjectEvent) => void>();
  const controller = createProjectController({
    api,
    store,
    adapter,
    createAutosave: (projectStore, save) =>
      createAutosaveController({ store: projectStore, save }),
    openEvents: (projectId, onEvent) =>
      openEvents(projectId, (event) => {
        onEvent(event);
        for (const subscriber of [...eventSubscribers]) {
          subscriber(event);
        }
      }),
  });
  let workspace: ReturnType<typeof mountWorkspace> | null = null;

  let disposed = false;
  let lastProjectId: string | null = null;
  const unsubscribeUrl = controller.subscribe((state) => {
    if (state.activeProjectId !== lastProjectId) {
      lastProjectId = state.activeProjectId;
      syncUrl(lastProjectId);
    }
  });
  const bootstrapAbort = new AbortController();
  const ready = (async () => {
    try {
      await loadFont();
      if (disposed) return;
      workspace = mountWorkspace({
        root,
        controller,
        store,
        adapter,
        assetsApi,
        compositionsApi,
        skusApi,
        providersApi,
        generationsApi,
        exportsApi,
        subscribeEvents: (listener) => {
          eventSubscribers.add(listener);
          return () => {
            eventSubscribers.delete(listener);
          };
        },
      });
      if (bootstrap.projectId !== null) {
        const loaded = await api.getProject(bootstrap.projectId, bootstrapAbort.signal);
        if (disposed) return;
        if (!loaded.ok) throw new Error(loaded.message);
        controller.initialize(loaded.value);
      }
      if (!disposed) {
        await controller.searchProjects("", false);
      }
    } catch (error) {
      if (!disposed) {
        const alert = document.createElement("p");
        alert.className = "canvas-fatal-error";
        alert.setAttribute("role", "alert");
        alert.textContent = error instanceof Error ? error.message : "画布加载失败";
        root.replaceChildren(alert);
      }
      throw error;
    }
  })();

  return {
    ready,
    store,
    controller,
    dispose: () => {
      if (disposed) {
        return;
      }
      disposed = true;
      bootstrapAbort.abort();
      unsubscribeUrl();
      if (workspace === null) {
        controller.dispose();
        adapter.dispose();
        root.replaceChildren();
      } else {
        workspace.dispose();
      }
      eventSubscribers.clear();
      mountedRoots.delete(root);
    },
  };
}

export function parseCanvasBootstrap(value: unknown): CanvasBootstrap {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error("Canvas bootstrap must be an object");
  }
  const record = value as Record<string, unknown>;
  if (
    Object.keys(record).sort().join(",") !== "apiBase,projectId" ||
    typeof record.apiBase !== "string" ||
    !record.apiBase.startsWith("/") ||
    (record.projectId !== null && typeof record.projectId !== "string")
  ) {
    throw new Error("Canvas bootstrap does not match the expected contract");
  }
  return { apiBase: record.apiBase, projectId: record.projectId };
}

function autoStartCanvasApplication(): void {
  const root = document.querySelector<HTMLElement>("#canvas-app");
  const bootstrapElement = document.querySelector<HTMLScriptElement>("#canvas-bootstrap");
  if (root === null || bootstrapElement === null) {
    return;
  }
  try {
    const bootstrap = parseCanvasBootstrap(
      JSON.parse(bootstrapElement.textContent ?? "null"),
    );
    const application = startCanvasApplication({ root, bootstrap });
    void application.ready.catch((error: unknown) => {
      application.dispose();
      const alert = document.createElement("p");
      alert.className = "canvas-fatal-error";
      alert.setAttribute("role", "alert");
      alert.textContent = error instanceof Error ? error.message : "画布加载失败";
      root.replaceChildren(alert);
    });
  } catch (error) {
    const alert = document.createElement("p");
    alert.className = "canvas-fatal-error";
    alert.setAttribute("role", "alert");
    alert.textContent = error instanceof Error ? error.message : "画布加载失败";
    root.replaceChildren(alert);
  }
}

autoStartCanvasApplication();
