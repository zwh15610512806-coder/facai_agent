import { expect, test, vi } from "vitest";

import { createProvidersApi } from "./providers";

test("provider catalog loads every backend capability without exposing a second model type", async () => {
  const fetcher = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const body = url.endsWith("/model-providers")
      ? [{
        id: "provider-1",
        name: "Seedream",
        enabled: true,
        availability: "available",
        availabilityReason: null,
        configVersion: 1,
      }]
      : [{
        id: "model-1",
        providerId: "provider-1",
        modelId: "seedream-5-pro",
        displayName: "Seedream 5.0 Pro",
        enabled: true,
        availability: "available",
        availabilityReason: null,
        configVersion: 4,
        capabilities: {
          text_to_image: true,
          image_to_image: true,
          mask_edit: false,
          allowed_ratios: ["1:1"],
          allowed_sizes: ["1024x1024"],
          min_width: 512,
          max_width: 2048,
          min_height: 512,
          max_height: 2048,
          max_quantity: 1,
          max_reference_images: 14,
          reference_transfer: "base64",
          protocol: "sync",
          supports_cancel: false,
          supports_idempotency: true,
          supports_idempotency_lookup: false,
          concurrency_limit: 2,
        },
        priceMetadata: { unit: "image", amount: 0.1 },
      }];
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  const api = createProvidersApi({ apiBase: "/api/canvas", fetcher });

  const catalog = await api.loadCatalog();

  expect(catalog).toEqual({
    ok: true,
    value: [{
      id: "model-1",
      providerId: "provider-1",
      modelId: "seedream-5-pro",
      displayName: "Seedream 5.0 Pro",
      enabled: true,
      availability: "available",
      availabilityReason: null,
      configVersion: 4,
      capabilities: expect.objectContaining({
        imageToImage: true,
        maxReferenceImages: 14,
        supportsIdempotency: true,
      }),
      priceMetadata: { unit: "image", amount: 0.1 },
    }],
  });
  expect(fetcher.mock.calls.map(([url]) => url)).toEqual([
    "/api/canvas/model-providers",
    "/api/canvas/model-providers/provider-1/models",
  ]);
});

test("provider management sends a write-only credential and does not accept it from a response", async () => {
  const secret = "never-render-this";
  const fetcher = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
    expect(JSON.parse(String(init?.body))).toMatchObject({ credential: { apiKey: secret } });
    return new Response(JSON.stringify({
      id: "provider-2", adapterType: "openai_images", name: "Vendor", baseUrl: "https://api.vendor.example",
      authType: "bearer", enabled: true, configVersion: 1, credentialConfigured: true, credentialHint: "stored securely",
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  });
  const api = createProvidersApi({ apiBase: "/api/canvas", fetcher });
  const result = await api.createProvider({
    adapterType: "openai_images", name: "Vendor", baseUrl: "https://api.vendor.example",
    authType: "bearer", credential: { apiKey: secret }, credentialHint: "stored securely",
  });
  expect(result).toEqual(expect.objectContaining({ ok: true }));
  if (result.ok) expect(JSON.stringify(result.value)).not.toContain(secret);
});
