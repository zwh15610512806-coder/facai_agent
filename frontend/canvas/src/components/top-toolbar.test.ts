import { describe, expect, it, vi } from "vitest";

import { createProjectStore } from "../state/project-store";
import { createTopToolbar } from "./top-toolbar";

describe("TopToolbar", () => {
  it("opens the interactive export surface only for an editable project", () => {
    const onExport = vi.fn();
    const toolbar = createTopToolbar(
      createProjectStore(),
      vi.fn(),
      vi.fn(),
      vi.fn(),
      onExport,
    );
    const button = toolbar.element.querySelector<HTMLButtonElement>("[data-testid='canvas-toolbar-export']")!;
    expect(button.disabled).toBe(true);
    toolbar.setEditable(true);
    expect(button.disabled).toBe(false);
    button.click();
    expect(onExport).toHaveBeenCalledOnce();
  });
});
