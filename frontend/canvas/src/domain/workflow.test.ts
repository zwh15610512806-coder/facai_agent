import { describe, expect, test } from "vitest";

import {
  canOpenInspectorTab,
  defaultInspectorTab,
  deriveCanvasWorkflowStage,
  type CanvasWorkflowSnapshot,
} from "./workflow";

const snapshot = (
  patch: Partial<CanvasWorkflowSnapshot> = {},
): CanvasWorkflowSnapshot => ({
  hasProject: true,
  hasSource: true,
  processing: false,
  generating: false,
  hasResults: false,
  hasSelectedResult: false,
  exportRequested: false,
  ...patch,
});

describe("Canvas workflow", () => {
  test.each([
    [snapshot({ hasProject: false, hasSource: false }), "project"],
    [snapshot({ hasSource: false }), "source"],
    [snapshot({ processing: true }), "processing"],
    [snapshot(), "configure"],
    [snapshot({ generating: true }), "generating"],
    [snapshot({ hasResults: true }), "results"],
    [snapshot({ hasResults: true, hasSelectedResult: true, exportRequested: true }), "export"],
  ] as const)("derives %s as %s", (input, expected) => {
    expect(deriveCanvasWorkflowStage(input)).toBe(expected);
    expect(defaultInspectorTab(expected)).toMatch(/source|generate|results|export/);
  });

  test("keeps result and export tabs hidden until their real prerequisites exist", () => {
    expect(canOpenInspectorTab("source", snapshot({ hasSource: false }))).toBe(true);
    expect(canOpenInspectorTab("generate", snapshot({ hasSource: false }))).toBe(false);
    expect(canOpenInspectorTab("results", snapshot())).toBe(false);
    expect(canOpenInspectorTab("results", snapshot({ generating: true }))).toBe(true);
    expect(canOpenInspectorTab("export", snapshot({ hasResults: true }))).toBe(false);
    expect(canOpenInspectorTab("export", snapshot({ hasResults: true, hasSelectedResult: true }))).toBe(true);
  });
});
