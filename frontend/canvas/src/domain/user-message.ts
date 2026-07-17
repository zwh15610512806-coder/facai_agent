const MESSAGE_MAP: ReadonlyArray<readonly [RegExp, string]> = [
  [/network|fetch|connection|offline/i, "网络连接失败，请检查网络后重试"],
  [/timeout|timed out/i, "请求超时，请稍后重试"],
  [/credential|api[ -]?key|secret/i, "尚未配置服务器端模型凭据"],
  [/unauthori[sz]ed|forbidden/i, "请求被服务拒绝，请刷新页面后重试"],
  [/not found|404/i, "请求的资源不存在，请刷新后重试"],
  [/conflict|revision/i, "项目版本有冲突，请刷新后重试"],
  [/storage|capacity|disk|space/i, "存储空间不足，请清理空间后重试"],
  [/private network|loopback|localhost|ssrf/i, "当前地址不符合网络安全限制，请检查 Base URL"],
];

export function canvasUserMessage(message: unknown, fallback = "操作失败，请稍后重试"): string {
  const value = typeof message === "string" ? message.trim() : "";
  if (value === "") return fallback;
  if (/\p{Script=Han}/u.test(value)) return value;
  for (const [pattern, translated] of MESSAGE_MAP) {
    if (pattern.test(value)) return translated;
  }
  return fallback;
}
