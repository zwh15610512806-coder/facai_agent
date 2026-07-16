export type CanvasWorkflowStage =
  | "project"
  | "source"
  | "processing"
  | "configure"
  | "generating"
  | "results"
  | "export";

export type CanvasInspectorTab = "source" | "generate" | "results" | "export";

export interface CanvasWorkflowSnapshot {
  hasProject: boolean;
  hasSource: boolean;
  processing: boolean;
  generating: boolean;
  hasResults: boolean;
  hasSelectedResult: boolean;
  exportRequested: boolean;
}

export function deriveCanvasWorkflowStage(
  snapshot: CanvasWorkflowSnapshot,
): CanvasWorkflowStage {
  if (!snapshot.hasProject) return "project";
  if (!snapshot.hasSource) return "source";
  if (snapshot.processing) return "processing";
  if (snapshot.generating) return "generating";
  if (snapshot.exportRequested && snapshot.hasSelectedResult) return "export";
  if (snapshot.hasResults) return "results";
  return "configure";
}

export function defaultInspectorTab(stage: CanvasWorkflowStage): CanvasInspectorTab {
  switch (stage) {
    case "project":
    case "source":
    case "processing":
      return "source";
    case "configure":
      return "generate";
    case "generating":
    case "results":
      return "results";
    case "export":
      return "export";
  }
}

export function canOpenInspectorTab(
  tab: CanvasInspectorTab,
  snapshot: CanvasWorkflowSnapshot,
): boolean {
  switch (tab) {
    case "source":
      return snapshot.hasProject;
    case "generate":
      return snapshot.hasProject && snapshot.hasSource && !snapshot.processing;
    case "results":
      return snapshot.hasProject && (snapshot.generating || snapshot.hasResults);
    case "export":
      return snapshot.hasProject && snapshot.hasSelectedResult;
  }
}
