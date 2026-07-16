import type {
  CanvasViewport,
  NormalizedPoint,
} from "../domain/types";

export interface ViewportSafetyLimits {
  minPan: number;
  maxPan: number;
  minZoom: number;
  maxZoom: number;
}

export const DEFAULT_VIEWPORT_SAFETY: Readonly<ViewportSafetyLimits> =
  Object.freeze({
    minPan: -1_000_000,
    maxPan: 1_000_000,
    minZoom: 0.01,
    maxZoom: 1_000,
  });

function finite(value: number, label: string): number {
  if (!Number.isFinite(value)) {
    throw new Error(`${label} must be finite`);
  }
  return value;
}

function validateLimits(limits: ViewportSafetyLimits): ViewportSafetyLimits {
  const parsed = {
    minPan: finite(limits.minPan, "minPan"),
    maxPan: finite(limits.maxPan, "maxPan"),
    minZoom: finite(limits.minZoom, "minZoom"),
    maxZoom: finite(limits.maxZoom, "maxZoom"),
  };
  if (parsed.minPan > parsed.maxPan) {
    throw new Error("minPan must not exceed maxPan");
  }
  if (parsed.minZoom <= 0 || parsed.minZoom > parsed.maxZoom) {
    throw new Error("zoom safety limits must be positive and ordered");
  }
  return parsed;
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}

function validateViewport(viewport: CanvasViewport): CanvasViewport {
  return {
    x: finite(viewport.x, "viewport.x"),
    y: finite(viewport.y, "viewport.y"),
    zoom: finite(viewport.zoom, "viewport.zoom"),
  };
}

export function panViewport(
  viewport: CanvasViewport,
  delta: NormalizedPoint,
  limits: ViewportSafetyLimits = DEFAULT_VIEWPORT_SAFETY,
): CanvasViewport {
  const current = validateViewport(viewport);
  const safety = validateLimits(limits);
  const deltaX = finite(delta.x, "pan.x");
  const deltaY = finite(delta.y, "pan.y");
  return {
    x: clamp(current.x + deltaX, safety.minPan, safety.maxPan),
    y: clamp(current.y + deltaY, safety.minPan, safety.maxPan),
    zoom: clamp(current.zoom, safety.minZoom, safety.maxZoom),
  };
}

export function zoomViewport(
  viewport: CanvasViewport,
  zoom: number,
  limits: ViewportSafetyLimits = DEFAULT_VIEWPORT_SAFETY,
): CanvasViewport {
  const current = validateViewport(viewport);
  const safety = validateLimits(limits);
  return {
    x: clamp(current.x, safety.minPan, safety.maxPan),
    y: clamp(current.y, safety.minPan, safety.maxPan),
    zoom: clamp(finite(zoom, "zoom"), safety.minZoom, safety.maxZoom),
  };
}
