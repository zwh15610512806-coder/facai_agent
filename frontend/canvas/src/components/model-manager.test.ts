import { expect, test, vi } from "vitest";

import { createModelManager } from "./model-manager";

test("a provider with zero models remains selectable for its first profile and paid probe needs confirmation", async () => {
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  const probeProvider = vi.fn().mockResolvedValue({ ok: true, value: { status: "configuration_ready", paidProbeRequired: false } });
  const manager = createModelManager({
    catalogApi: { loadCatalog: vi.fn().mockResolvedValue({ ok: true, value: [] }) },
    managementApi: {
      loadProviders: vi.fn().mockResolvedValue({ ok: true, value: [{ id: "provider-empty", name: "Empty Vendor", enabled: true, availability: "available", availabilityReason: null, configVersion: 1 }] }),
      createProvider: vi.fn(), createModelProfile: vi.fn(), probeProvider,
    },
    onUnauthorized: vi.fn(), onUnconfigured: vi.fn(), onCatalog: vi.fn(),
  });
  document.body.append(manager.element);
  await vi.waitFor(() => expect(manager.element.querySelector<HTMLSelectElement>("select[aria-label='模型所属提供方']")?.options.length).toBe(2));
  expect(manager.element.querySelector<HTMLSelectElement>("select[aria-label='模型所属提供方']")?.options[1]?.value).toBe("provider-empty");
  const probe = [...manager.element.querySelectorAll("button")].find((button) => button.textContent === "检测连接")!;
  probe.click();
  expect(probeProvider).not.toHaveBeenCalled();
  confirm.mockReturnValue(true);
  probe.click();
  await vi.waitFor(() => expect(probeProvider).toHaveBeenCalledWith("provider-empty", true));
  confirm.mockRestore();
  document.body.replaceChildren();
});
