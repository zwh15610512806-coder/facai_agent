import { expect, test } from "vitest";

import { canvasUserMessage } from "./user-message";

test("keeps Chinese safe messages and replaces raw English service errors", () => {
  expect(canvasUserMessage("项目版本有冲突")).toBe("项目版本有冲突");
  expect(canvasUserMessage("Network unavailable")).toBe("网络连接失败，请检查网络后重试");
  expect(canvasUserMessage("A server-side credential is required")).toBe("尚未配置服务器端模型凭据");
  expect(canvasUserMessage("insufficient storage capacity")).toBe("存储空间不足，请清理空间后重试");
  expect(canvasUserMessage("Internal server error", "生成失败，请重试")).toBe("生成失败，请重试");
});
