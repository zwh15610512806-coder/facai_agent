export interface GenerationStatusView {
  element: HTMLElement;
  update(message: string, tone?: "idle" | "working" | "success" | "error"): void;
}

export function createGenerationStatus(): GenerationStatusView {
  const element = document.createElement("p");
  element.className = "canvas-generation-status";
  element.dataset.testid = "canvas-generation-status";
  element.setAttribute("role", "status");
  return {
    element,
    update: (message, tone = "idle") => {
      element.dataset.tone = tone;
      element.textContent = message;
    },
  };
}
