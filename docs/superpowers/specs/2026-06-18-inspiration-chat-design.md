# 灵感 AI 对话页设计

## Context

用户要在顶部导航「检索」右侧新增一个独立「灵感」功能板块，用来和 AI 进行通用聊天对话。项目当前是 FastAPI + Jinja2 + 静态 CSS/JS 的本地 Agent 应用，已有「产品」页的三栏聊天工作台和产品 RAG 对话样式可复用。

## Goal

新增 `/app/inspiration` 独立页面，让用户可以进入一个类似 ChatGPT 的轻量聊天界面，围绕短视频脚本、运营灵感、产品表达、活动文案和日常创意问题直接与 AI 对话。

成功标准：

- 顶部导航在「检索」右侧显示「灵感」，当前页高亮。
- `/app/inspiration` 能正常渲染独立聊天页面。
- 页面首屏就是可用聊天体验，不是营销落地页。
- 用户输入问题后能调用后端接口并追加 AI 回复。
- DeepSeek 不可用或接口失败时，页面给出清楚的反馈。
- 移动端导航、会话侧栏、聊天输入框不挤压、不溢出。

## Recommended Approach

实现完整可用聊天页。

原因：

- 这最符合「主要就是用来和 AI 聊天对话」的目标。
- 现有 `services.ai_service.ai_service.chat` 已封装 DeepSeek 调用和离线回退，后端不需要引入新供应商。
- 现有 `products.html` 已有聊天气泡、输入框、空状态和消息渲染模式，可以在视觉上继承，不必重造一套风格。

非目标：

- 本次不做持久化会话历史。
- 本次不做流式输出。
- 本次不做文件上传或产品资料 RAG 检索。
- 本次不接入外部 ChatGPT 官方站点或新的模型供应商。

## UX Design

导航：

- 所有主模板导航末尾从「检索」扩展为「检索」「灵感」。
- 「灵感」页面自身高亮。

页面布局：

- 桌面端使用两栏：左侧窄栏放新对话按钮、常用提示词和定位说明；右侧为主聊天区。
- 主聊天区顶部显示简短标题和当前模型状态。
- 中间是消息列表，空状态展示 4 个常用提示词按钮。
- 底部是固定 composer：多行输入框 + 发送按钮 + 清空按钮。
- 参考 ChatGPT 的信息层级：页面克制、对话居中、输入框是核心视觉焦点。
- 视觉必须沿用法采现有 tokens：`--facai`、`--surface`、`--bg`、`--border`、`--font-ui`、`--font-display`。

交互：

- 点击提示词会填入输入框并聚焦，用户可直接发送或继续编辑。
- Enter 发送，Shift+Enter 换行。
- 发送中禁用发送按钮，追加「正在思考」状态。
- 成功后追加 assistant 回复。
- 失败时将错误以 assistant 消息展示，并保留用户输入上下文。
- 清空按钮会清空当前页面消息并恢复欢迎状态。
- assistant 消息支持复制，复制后用现有 toast 提示。

## API Design

新增路由模块 `routers/inspiration.py`。

Endpoint:

`POST /api/inspiration/chat`

Request:

```json
{
  "message": "帮我想 5 个新品短视频开头",
  "history": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

Response:

```json
{
  "answer": "可以，下面是 5 个方向...",
  "mode": "ai",
  "model": "deepseek-chat"
}
```

Behavior:

- `message` 必填，去空白后不能为空。
- `history` 最多取最近 12 条，且只接受 `user` / `assistant` role。
- system prompt 将 AI 定位为「法采新媒体运营灵感助手」，可回答通用创意问题，但优先服务烘焙短视频运营场景。
- 调用 `ai_service.chat(..., allow_fallback=False)`。
- 如果 AI 不可用或返回空内容，返回本地兜底回复，说明当前 AI 服务不可用，并给出可继续手写的问题拆解建议。

## Files

- `main.py`: include inspiration router and add `/app/inspiration` page route.
- `routers/inspiration.py`: define chat request/response models and API endpoint.
- `templates/inspiration.html`: new independent chat UI.
- Existing templates: update nav links to include 「灵感」.
- `tests/test_inspiration_page.py`: page, nav, JS behavior structure tests.
- `tests/test_inspiration_api.py`: API validation, AI success, fallback behavior tests.
- `tests/test_frontend_common_js.py`: include `inspiration.html` in common JS coverage.

## Testing

Test-first plan:

- Page test fails until `templates/inspiration.html` exists and includes the expected shell, prompt buttons, composer, common JS, and `/api/inspiration/chat` call.
- Route test fails until `/app/inspiration` is registered.
- API test fails until `/api/inspiration/chat` validates input and returns AI or fallback answers.
- Nav test fails until all main templates include the new 「灵感」 link.

Verification commands:

```bash
python -m unittest tests.test_inspiration_page tests.test_inspiration_api -v
python -m unittest discover -s tests -v
```

## Risks

- Existing templates contain some mojibake text from earlier encoding issues. New files should be saved as UTF-8 and touched templates should preserve their current encoding behavior.
- The product page already uses a chat UI; avoid naming collisions by scoping new CSS with `.inspiration-*`.
- DeepSeek API may be unconfigured locally. Tests should monkeypatch `ai_service.chat` and `ai_service.client` rather than relying on network or real credentials.
