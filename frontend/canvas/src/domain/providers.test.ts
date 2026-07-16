import { expect, test } from "vitest";

import {
  modelCapabilityConflicts,
  PROVIDER_ADAPTER_CHOICES,
  type ModelProfile,
} from "./providers";

const model: ModelProfile = {
  id: "model-1", providerId: "provider-1", modelId: "vendor-image", displayName: "Vendor Image",
  enabled: true, availability: "available", availabilityReason: null, configVersion: 1,
  capabilities: {
    textToImage: true, imageToImage: false, maskEdit: false, allowedRatios: ["1:1"], allowedSizes: ["1024x1024"],
    minWidth: 512, maxWidth: 1024, minHeight: 512, maxHeight: 1024, maxQuantity: 1,
    maxReferenceImages: 0, referenceTransfer: "none", protocol: "sync", supportsCancel: false,
    supportsIdempotency: true, supportsIdempotencyLookup: false, concurrencyLimit: 1, priceMetadata: null,
  },
  priceMetadata: null,
};

test("only Seedream, OpenAI-compatible and declarative HTTP are selectable adapter families", () => {
  expect(PROVIDER_ADAPTER_CHOICES.map((choice) => choice.type)).toEqual([
    "seedream", "openai_images", "declarative_http",
  ]);
  expect(PROVIDER_ADAPTER_CHOICES.some((choice) => /comfy|local/i.test(choice.label))).toBe(false);
});

test("capability conflicts explain references, masks, dimensions and quantity without mutating selection", () => {
  const selected = structuredClone(model);
  expect(modelCapabilityConflicts(selected, {
    width: 1536, height: 1024, quantity: 2, referenceCount: 1, requiresMask: true,
  })).toEqual(expect.arrayContaining([
    "单次最多支持 1 张", "不支持当前产品参考图", "不支持蒙版编辑", "不支持当前尺寸或比例",
  ]));
  expect(selected.id).toBe("model-1");
});

test("a disabled model remains a conflict and never becomes an implicit replacement", () => {
  const disabled = { ...model, enabled: false, availability: "disabled" as const, availabilityReason: "管理员已禁用" };
  expect(modelCapabilityConflicts(disabled, { width: 1024, height: 1024 })).toEqual(["管理员已禁用"]);
  expect(disabled.id).toBe("model-1");
});
