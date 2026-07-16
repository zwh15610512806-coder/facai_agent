import { expect, test, vi } from "vitest";

import { createProviderEditor } from "./provider-editor";

test("provider credentials are write-only, clear on success, and survive an immediate unlock retry in component memory", async () => {
  const createProvider = vi.fn()
    .mockResolvedValueOnce({ ok: false, kind: "unauthorized", message: "locked" })
    .mockResolvedValueOnce({ ok: true, value: { id: "p" } });
  let retry = (): void => { throw new Error("retry was not registered"); };
  let retryRegistered = false;
  const editor = createProviderEditor({
    api: { createProvider }, onSaved: vi.fn(), onUnconfigured: vi.fn(), onUnauthorized: (again) => { retry = again; retryRegistered = true; },
  });
  document.body.append(editor.element);
  const input = (label: string) => editor.element.querySelector<HTMLInputElement>(`input[aria-label="${label}"]`)!;
  input("提供方名称").value = "Vendor";
  input("服务地址").value = "https://api.vendor.example";
  input("API 密钥").value = "never-render-this";
  editor.element.querySelector<HTMLFormElement>("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  await vi.waitFor(() => expect(retryRegistered).toBe(true));
  expect(editor.element.textContent).not.toContain("never-render-this");
  retry();
  await vi.waitFor(() => expect(createProvider).toHaveBeenCalledTimes(2));
  expect(input("API 密钥").value).toBe("");
  document.body.replaceChildren();
});
