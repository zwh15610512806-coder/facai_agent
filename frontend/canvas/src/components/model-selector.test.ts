import { expect, test, vi } from "vitest";

import type { ModelProfile } from "../domain/providers";
import { createModelSelector } from "./model-selector";

const unavailable: ModelProfile = {
  id: "disabled-model", providerId: "p", modelId: "m", displayName: "Disabled", enabled: false,
  availability: "disabled", availabilityReason: "管理员已禁用", configVersion: 1,
  capabilities: { textToImage: true, imageToImage: false, maskEdit: false, allowedRatios: [], allowedSizes: [], minWidth: null, maxWidth: null, minHeight: null, maxHeight: null, maxQuantity: 1, maxReferenceImages: 0, referenceTransfer: "none", protocol: "sync", supportsCancel: false, supportsIdempotency: false, supportsIdempotencyLookup: false, concurrencyLimit: 1, priceMetadata: null },
  priceMetadata: null,
};

test("disabled profiles cannot be selected and selected capability conflicts are visible", () => {
  const field = createModelSelector({
    label: "主图模型", value: unavailable.id, models: [unavailable], disabled: false,
    requirements: { width: 1024, height: 1024, referenceCount: 1 }, onChange: vi.fn(),
  });
  const option = field.querySelector<HTMLOptionElement>(`option[value="${unavailable.id}"]`);
  expect(option?.disabled).toBe(true);
  expect(field.querySelector("[data-testid='canvas-model-capability-reason']")?.textContent).toContain("管理员已禁用");
});
