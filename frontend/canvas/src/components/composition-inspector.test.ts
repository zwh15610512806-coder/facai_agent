import { expect, test, vi } from "vitest";

import vectorsFixture from "../../test/fixtures/composition-vectors.json";
import { createCompositionInspector } from "./composition-inspector";
import type { CompositionLayout } from "../domain/types";

test("composition inspector edits only shared fields and emits one group update", () => {
  const onUpdate = vi.fn();
  const inspector = createCompositionInspector({ onUpdate });
  inspector.update({
    groupId: "group-a",
    layout: structuredClone(vectorsFixture.vectors[0].layout) as CompositionLayout,
    disabled: false,
  });

  expect(inspector.element.textContent).toContain("共享构图");
  expect(inspector.element.textContent).not.toMatch(/背景|模型|光线|色彩|装饰/);
  const baseline = inspector.element.querySelector<HTMLInputElement>(
    '[data-field="baseline"]',
  );
  if (baseline === null) throw new Error("expected baseline input");
  baseline.value = "0.7";
  baseline.dispatchEvent(new Event("change", { bubbles: true }));

  expect(onUpdate).toHaveBeenCalledTimes(1);
  expect(onUpdate).toHaveBeenCalledWith(
    "group-a",
    expect.objectContaining({ baseline: 0.7, contain: true }),
  );
  inspector.dispose();
});
