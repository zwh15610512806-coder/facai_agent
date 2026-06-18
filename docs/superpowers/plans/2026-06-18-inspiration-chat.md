# Inspiration Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a standalone `/app/inspiration` AI chat page with a matching `/api/inspiration/chat` endpoint and a new 「灵感」 nav item immediately after 「检索」.

**Architecture:** Implement a focused FastAPI router for general inspiration chat, backed by the existing `services.ai_service.ai_service`. Add one self-contained Jinja template with scoped `.inspiration-*` CSS and page-local JavaScript, while reusing shared `style.css`, `common.js`, Lucide icons, and existing navigation patterns.

**Tech Stack:** FastAPI, Pydantic, Jinja2 templates, vanilla JavaScript, unittest/TestClient.

---

## File Structure

- Create `routers/inspiration.py`
  - Owns `POST /api/inspiration/chat`.
  - Sanitizes short chat history and handles AI unavailable fallback.
- Modify `main.py`
  - Includes the inspiration API router at `/api/inspiration`.
  - Adds `GET /app/inspiration`.
- Create `templates/inspiration.html`
  - Owns the standalone ChatGPT-style page, scoped CSS, prompt chips, composer, message rendering, copy, clear, and send behavior.
- Modify `templates/index.html`, `templates/rewrite.html`, `templates/products.html`, `templates/import.html`, `templates/templates.html`, `templates/history.html`, `templates/search.html`
  - Adds the 「灵感」 nav link after 「检索」.
- Modify `tests/test_frontend_common_js.py`
  - Requires `inspiration.html` to load `common.js`.
- Create `tests/test_inspiration_api.py`
  - Covers validation, successful AI response, fallback response, and history trimming.
- Create `tests/test_inspiration_page.py`
  - Covers route rendering, template structure, JS hooks, common JS, responsive CSS, and nav coverage.

---

### Task 1: Inspiration Chat API

**Files:**
- Create: `tests/test_inspiration_api.py`
- Create: `routers/inspiration.py`

- [ ] **Step 1: Write the failing API tests**

Create `tests/test_inspiration_api.py`:

```python
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient


class InspirationApiTests(unittest.TestCase):
    def setUp(self):
        from routers import inspiration

        self.inspiration = inspiration
        self.original_client = inspiration.ai_service.client
        self.original_chat = inspiration.ai_service.chat
        self.original_model = inspiration.ai_service.model

        app = FastAPI()
        app.include_router(inspiration.router, prefix="/api/inspiration")
        self.client = TestClient(app)

    def tearDown(self):
        self.inspiration.ai_service.client = self.original_client
        self.inspiration.ai_service.chat = self.original_chat
        self.inspiration.ai_service.model = self.original_model

    def test_chat_requires_non_empty_message(self):
        response = self.client.post("/api/inspiration/chat", json={"message": "   "})

        self.assertEqual(response.status_code, 422)

    def test_chat_returns_ai_answer_when_service_responds(self):
        self.inspiration.ai_service.client = object()
        self.inspiration.ai_service.model = "deepseek-chat"

        async def fake_chat(messages, temperature=0.7, allow_fallback=False):
            self.assertFalse(allow_fallback)
            self.assertEqual(messages[0]["role"], "system")
            self.assertIn("法采新媒体运营灵感助手", messages[0]["content"])
            self.assertEqual(messages[-1], {"role": "user", "content": "帮我想 3 个新品短视频开头"})
            return "这里是 3 个开头。"

        self.inspiration.ai_service.chat = fake_chat

        response = self.client.post(
            "/api/inspiration/chat",
            json={"message": "帮我想 3 个新品短视频开头"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["answer"], "这里是 3 个开头。")
        self.assertEqual(data["mode"], "ai")
        self.assertEqual(data["model"], "deepseek-chat")

    def test_chat_returns_local_fallback_when_ai_unavailable(self):
        self.inspiration.ai_service.client = None

        response = self.client.post(
            "/api/inspiration/chat",
            json={"message": "今天拍什么内容？"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["mode"], "fallback")
        self.assertIn("AI 服务暂时不可用", data["answer"])
        self.assertIn("今天拍什么内容？", data["answer"])

    def test_chat_sends_only_recent_valid_history(self):
        self.inspiration.ai_service.client = object()
        captured = {}

        async def fake_chat(messages, temperature=0.7, allow_fallback=False):
            captured["messages"] = messages
            return "已结合上下文回答。"

        self.inspiration.ai_service.chat = fake_chat
        history = []
        for index in range(20):
            role = "user" if index % 2 == 0 else "assistant"
            history.append({"role": role, "content": f"历史 {index}"})
        history.append({"role": "system", "content": "should be ignored"})
        history.append({"role": "user", "content": ""})

        response = self.client.post(
            "/api/inspiration/chat",
            json={"message": "继续"},
        )

        self.assertEqual(response.status_code, 200)
        roles = [item["role"] for item in captured["messages"]]
        contents = [item["content"] for item in captured["messages"]]
        self.assertEqual(roles[0], "system")
        self.assertEqual(roles[-1], "user")
        self.assertEqual(contents[-1], "继续")
        self.assertNotIn("should be ignored", contents)
        self.assertLessEqual(len(captured["messages"]), 14)
        self.assertIn("历史 8", contents)
        self.assertIn("历史 19", contents)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the API tests to verify RED**

Run:

```bash
python -m unittest tests.test_inspiration_api -v
```

Expected: FAIL with `ImportError` or `ModuleNotFoundError` for `routers.inspiration`.

- [ ] **Step 3: Implement the minimal API router**

Create `routers/inspiration.py`:

```python
"""General inspiration chat API."""
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from services.ai_service import ai_service


router = APIRouter()


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(default="", max_length=4000)


class InspirationChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=40)

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("请输入聊天内容")
        return value


class InspirationChatResponse(BaseModel):
    answer: str
    mode: Literal["ai", "fallback"]
    model: str


SYSTEM_PROMPT = """你是法采新媒体运营灵感助手。
你擅长短视频脚本创意、烘焙产品卖点表达、直播与抖音运营、活动文案、拍摄选题和内容复盘。
回答要直接、可执行、适合本地运营团队拿去改写使用。
如果用户问题和法采业务无关，也可以正常协助，但优先把建议落回内容创作和运营执行。
"""


def _recent_history(history: list[ChatTurn]) -> list[dict[str, str]]:
    cleaned = []
    for item in history:
        content = (item.content or "").strip()
        if content:
            cleaned.append({"role": item.role, "content": content})
    return cleaned[-12:]


def _fallback_answer(message: str) -> str:
    return (
        "AI 服务暂时不可用，但可以先这样拆解你的问题：\n\n"
        f"你刚才问的是：{message}\n\n"
        "1. 先明确目标：要做选题、脚本、标题、活动文案，还是拍摄方向。\n"
        "2. 再补充对象：产品名、使用场景、价格活动、希望强调的卖点。\n"
        "3. 最后给出约束：平台、时长、语气、是否需要镜头说明。\n\n"
        "等 AI 服务恢复后，我可以继续把它整理成完整方案。"
    )


@router.post("/chat", response_model=InspirationChatResponse)
async def chat_with_inspiration(data: InspirationChatRequest):
    message = data.message.strip()
    model = ai_service.get_model_name()
    if not ai_service.is_available:
        return InspirationChatResponse(answer=_fallback_answer(message), mode="fallback", model=model)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(_recent_history(data.history))
    messages.append({"role": "user", "content": message})
    answer = (await ai_service.chat(messages, temperature=0.7, allow_fallback=False)).strip()
    if not answer:
        return InspirationChatResponse(answer=_fallback_answer(message), mode="fallback", model=model)
    return InspirationChatResponse(answer=answer, mode="ai", model=model)
```

- [ ] **Step 4: Run the API tests to verify GREEN**

Run:

```bash
python -m unittest tests.test_inspiration_api -v
```

Expected: PASS, 4 tests.

- [ ] **Step 5: Commit the API task**

Run:

```bash
git add routers/inspiration.py tests/test_inspiration_api.py
git commit -m "feat: add inspiration chat api"
```

---

### Task 2: Inspiration Page Route And UI

**Files:**
- Create: `tests/test_inspiration_page.py`
- Create: `templates/inspiration.html`
- Modify: `main.py`
- Modify: `tests/test_frontend_common_js.py`

- [ ] **Step 1: Write the failing page tests**

Create `tests/test_inspiration_page.py`:

```python
import re
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from main import app


ROOT = Path(__file__).resolve().parents[1]


class InspirationPageTests(unittest.TestCase):
    def test_inspiration_route_renders_page(self):
        response = TestClient(app).get("/app/inspiration")

        self.assertEqual(response.status_code, 200)
        self.assertIn("灵感", response.text)
        self.assertIn("inspiration-shell", response.text)

    def test_inspiration_template_has_chat_experience(self):
        page = (ROOT / "templates" / "inspiration.html").read_text(encoding="utf-8-sig")

        self.assertIn('class="inspiration-shell"', page)
        self.assertIn('id="inspirationThread"', page)
        self.assertIn('id="inspirationInput"', page)
        self.assertIn('id="inspirationSend"', page)
        self.assertIn('id="clearChatBtn"', page)
        self.assertIn("sendInspirationChat", page)
        self.assertIn("appendMessage", page)
        self.assertIn("copyAssistantMessage", page)
        self.assertIn("submitOnEnter", page)
        self.assertIn("fetch('/api/inspiration/chat'", page)
        self.assertIn("/static/js/common.js", page)

    def test_inspiration_template_has_prompt_chips_and_responsive_css(self):
        page = (ROOT / "templates" / "inspiration.html").read_text(encoding="utf-8-sig")

        self.assertGreaterEqual(page.count("prompt-chip"), 4)
        self.assertIn("@media (max-width: 900px)", page)
        self.assertIn(".inspiration-shell{grid-template-columns:1fr", page)
        self.assertIn("@media (max-width: 640px)", page)
        self.assertIn(".inspiration-page{height:auto", page)

    def test_common_js_test_includes_inspiration_page(self):
        test_file = (ROOT / "tests" / "test_frontend_common_js.py").read_text(encoding="utf-8-sig")

        self.assertIn('"inspiration.html"', test_file)
```

- [ ] **Step 2: Run the page tests to verify RED**

Run:

```bash
python -m unittest tests.test_inspiration_page -v
```

Expected: FAIL because `/app/inspiration` and `templates/inspiration.html` do not exist.

- [ ] **Step 3: Wire the route in `main.py`**

Modify `main.py` imports:

```python
from routers import products, templates as tpl_routes, scripts, import_data, reference_scripts, inspiration
```

Add router include after the reference router:

```python
app.include_router(inspiration.router, prefix="/api/inspiration", tags=["inspiration"])
```

Add page route after `/app/search`:

```python
@app.get("/app/inspiration")
def inspiration_page(request: Request): return templates.TemplateResponse(request, "inspiration.html", {"request": request})
```

- [ ] **Step 4: Create the chat page template**

Create `templates/inspiration.html` with this structure:

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>灵感 · 法采新媒体运营 Agent</title>
<link rel="stylesheet" href="/static/css/style.css?v=mobile-20260613">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Source+Serif+4:wght@600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<script src="https://unpkg.com/lucide@latest/dist/umd/lucide.min.js"></script>
<script src="/static/js/common.js?v=20260618"></script>
<style>
body{overflow:hidden}
.inspiration-page{max-width:min(1440px,calc(100vw - 32px));height:calc(100dvh - 68px);margin:0 auto;padding:16px;display:flex;flex-direction:column}
.inspiration-shell{flex:1;min-height:0;display:grid;grid-template-columns:280px minmax(0,1fr);gap:14px}
.inspiration-panel{min-width:0;min-height:0;background:var(--surface);border:1px solid var(--border);border-radius:var(--r);box-shadow:var(--s-2);display:flex;flex-direction:column;overflow:hidden}
.inspiration-side{padding:14px;gap:12px}
.inspiration-new{width:100%;height:40px}
.inspiration-side-title{font-family:var(--font-ui);font-size:13px;font-weight:900;color:var(--text);margin:8px 0 4px}
.prompt-list{display:grid;gap:8px}
.prompt-chip{border:1px solid var(--border);background:var(--surface);border-radius:var(--r-sm);padding:9px 10px;text-align:left;font-family:var(--font-ui);font-size:13px;font-weight:700;line-height:1.5;color:var(--text-2);cursor:pointer}
.prompt-chip:hover{border-color:var(--facai);color:var(--facai);background:var(--facai-ghost)}
.inspiration-note{margin-top:auto;padding:12px;border:1px solid var(--border-soft);border-radius:var(--r-sm);background:var(--surface-darker);font-size:12px;line-height:1.65;color:var(--text-2)}
.inspiration-main{background:linear-gradient(180deg,#fff 0%,#fff 62%,#fbfaf8 100%)}
.inspiration-hd{flex:0 0 auto;padding:14px 18px;border-bottom:1px solid var(--border-soft);display:flex;align-items:center;justify-content:space-between;gap:12px}
.inspiration-title{font-family:var(--font-display);font-size:1.25rem;margin:0}
.model-pill{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--facai-subtle);background:var(--facai-ghost);color:var(--facai);border-radius:var(--r-pill);padding:4px 10px;font-size:12px;font-weight:800}
.inspiration-thread{flex:1;min-height:0;overflow:auto;padding:22px 18px 14px;display:flex;flex-direction:column;gap:14px}
.inspiration-empty{max-width:680px;margin:auto;text-align:center;color:var(--text-2);display:grid;gap:14px}
.inspiration-empty-icon{width:46px;height:46px;border-radius:var(--r);margin:0 auto;background:var(--facai-soft);color:var(--facai);display:flex;align-items:center;justify-content:center}
.inspiration-empty-icon svg,.inspiration-empty-icon i{width:21px;height:21px}
.inspiration-empty h1{font-size:1.7rem;margin:0}
.inspiration-empty-prompts{display:flex;flex-wrap:wrap;gap:8px;justify-content:center}
.chat-message{display:flex;gap:10px;align-items:flex-start;max-width:100%}
.chat-message.user{justify-content:flex-end}
.chat-avatar{width:30px;height:30px;border-radius:var(--r-pill);display:inline-flex;align-items:center;justify-content:center;flex:0 0 auto;background:var(--facai-soft);color:var(--facai)}
.chat-avatar svg,.chat-avatar i{width:15px;height:15px}
.chat-bubble{max-width:min(780px,84%);border:1px solid var(--border-soft);border-radius:14px;background:var(--surface);padding:11px 13px;font-size:14px;line-height:1.78;color:var(--text);box-shadow:var(--s-1);white-space:pre-wrap;overflow-wrap:anywhere}
.chat-message.user .chat-bubble{background:var(--facai);border-color:var(--facai);color:#fff;box-shadow:var(--s-brand)}
.message-tools{margin-top:8px;display:flex;gap:6px}
.message-tool{border:1px solid var(--border);border-radius:var(--r-sm);background:var(--surface);height:28px;padding:0 9px;font-size:12px;font-weight:800;color:var(--text-2);cursor:pointer}
.message-tool:hover{border-color:var(--facai);color:var(--facai);background:var(--facai-ghost)}
.thinking{color:var(--text-3)}
.inspiration-composer{flex:0 0 auto;border-top:1px solid var(--border-soft);padding:12px;background:rgba(255,255,255,.96)}
.composer-form{display:flex;gap:8px;align-items:flex-end}
.inspiration-input{flex:1;min-height:44px;max-height:132px;resize:none;border:1.5px solid var(--border);border-radius:var(--r);padding:10px 12px;font:inherit;font-size:14px;line-height:1.55;background:var(--surface)}
.inspiration-input:focus{outline:none;border-color:var(--facai);box-shadow:0 0 0 3px var(--facai-subtle)}
.icon-button{width:44px;height:44px;border-radius:var(--r);border:1px solid var(--border);background:var(--surface);color:var(--text-2);display:inline-flex;align-items:center;justify-content:center;cursor:pointer;flex:0 0 auto}
.icon-button:hover{border-color:var(--facai);color:var(--facai);background:var(--facai-ghost)}
.send-button{border:0;background:var(--facai);color:#fff}
.send-button:disabled{background:var(--border);cursor:not-allowed}
.icon-button svg,.icon-button i{width:16px;height:16px}
@media (max-width: 900px){
  body{overflow:auto}
  .inspiration-page{height:auto;max-width:100%;padding:12px}
  .inspiration-shell{grid-template-columns:1fr}
  .inspiration-side{min-height:0}
  .prompt-list{grid-template-columns:repeat(2,minmax(0,1fr))}
  .inspiration-main{min-height:calc(100dvh - 220px)}
}
@media (max-width: 640px){
  .inspiration-page{height:auto;padding:10px}
  .inspiration-hd{align-items:flex-start;flex-direction:column}
  .prompt-list{grid-template-columns:1fr}
  .inspiration-thread{padding:16px 12px 10px}
  .chat-bubble{max-width:92%}
  .composer-form{gap:6px}
  .icon-button{width:40px;height:40px}
}
</style>
</head>
<body>
<nav class="nav">
<div class="nav-inner">
<a href="/app" class="nav-brand"><span class="nav-brand-mark"><img src="/static/images/facai-logo.png" alt="法采"></span><span>法采新媒体运营 Agent</span></a>
<div class="nav-links">
<a href="/app" class="nav-link">生成</a><a href="/app/rewrite" class="nav-link">改写</a><a href="/app/products" class="nav-link">产品</a><a href="/app/import" class="nav-link">导入</a><a href="/app/templates" class="nav-link">模板库</a><a href="/app/history" class="nav-link">历史</a><a href="/app/search" class="nav-link">检索</a><a href="/app/inspiration" class="nav-link on">灵感</a>
</div></div></nav>
<main class="inspiration-page">
<section class="inspiration-shell" aria-label="灵感 AI 对话工作台">
  <aside class="inspiration-panel inspiration-side">
    <button class="btn btn-pri inspiration-new" type="button" onclick="clearChat()"><i data-lucide="plus"></i>新对话</button>
    <div>
      <div class="inspiration-side-title">常用提示</div>
      <div class="prompt-list">
        <button class="prompt-chip" type="button" onclick="usePrompt('帮我想 5 个烘焙新品短视频开头')">新品短视频开头</button>
        <button class="prompt-chip" type="button" onclick="usePrompt('把这个卖点改成更适合抖音口播的表达')">卖点口播改写</button>
        <button class="prompt-chip" type="button" onclick="usePrompt('给我一组直播间促单话术')">直播促单话术</button>
        <button class="prompt-chip" type="button" onclick="usePrompt('根据这个活动设计 3 个内容选题')">活动内容选题</button>
      </div>
    </div>
    <div class="inspiration-note">适合头脑风暴、脚本方向、标题、口播、拍摄思路和活动表达。产品资料精确问答仍建议去「产品」页。</div>
  </aside>
  <section class="inspiration-panel inspiration-main">
    <div class="inspiration-hd">
      <div><h1 class="inspiration-title">灵感</h1><div class="text-2" style="font-size:13px">和 AI 聊创意、脚本、选题与运营表达</div></div>
      <span id="modelPill" class="model-pill"><i data-lucide="sparkles"></i><span>AI 对话</span></span>
    </div>
    <div id="inspirationThread" class="inspiration-thread"></div>
    <div class="inspiration-composer">
      <form class="composer-form" onsubmit="sendInspirationChat(event)">
        <button id="clearChatBtn" class="icon-button" type="button" onclick="clearChat()" aria-label="清空对话" title="清空对话"><i data-lucide="trash-2"></i></button>
        <textarea id="inspirationInput" class="inspiration-input" rows="1" placeholder="问点什么，例如：帮我想一个奶冻粉的短视频脚本方向..." onkeydown="submitOnEnter(event)"></textarea>
        <button id="inspirationSend" class="icon-button send-button" type="submit" aria-label="发送"><i data-lucide="send-horizontal"></i></button>
      </form>
    </div>
  </section>
</section>
</main>
<script>
const ui=window.FacaiUI||{};
const escHtml=ui.escHtml||function(v){return String(v==null?'':v).replace(/[&<>"']/g,function(ch){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch];});};
const toast=ui.toast||function(message){alert(message);};
const copyText=ui.copyText||function(text){return navigator.clipboard.writeText(text);};
let chatHistory=[];
function renderIcons(){if(window.lucide)window.lucide.createIcons();}
function renderWelcome(){
 const thread=document.getElementById('inspirationThread');
 thread.innerHTML='<div class="inspiration-empty"><div class="inspiration-empty-icon"><i data-lucide="sparkles"></i></div><h1>今天想聊点什么？</h1><p>可以直接问选题、脚本、标题、活动文案或拍摄方向。</p><div class="inspiration-empty-prompts"><button class="prompt-chip" type="button" onclick="usePrompt(\\'帮我想 5 个烘焙新品短视频开头\\')">新品开头</button><button class="prompt-chip" type="button" onclick="usePrompt(\\'给我 3 个低成本拍摄选题\\')">低成本选题</button><button class="prompt-chip" type="button" onclick="usePrompt(\\'把卖点改成更口语的直播话术\\')">直播话术</button><button class="prompt-chip" type="button" onclick="usePrompt(\\'帮我做一版活动促单文案\\')">促单文案</button></div></div>';
 renderIcons();
}
function appendMessage(role,content,options){
 const thread=document.getElementById('inspirationThread');
 if(thread.querySelector('.inspiration-empty'))thread.innerHTML='';
 const msg=document.createElement('div');
 msg.className='chat-message '+(role==='user'?'user':'assistant');
 const safe=escHtml(content);
 const tools=role==='assistant'&&!options?.thinking?'<div class="message-tools"><button class="message-tool" type="button" onclick="copyAssistantMessage(this)">复制</button></div>':'';
 msg.innerHTML=(role==='user'?'':'<span class="chat-avatar"><i data-lucide="bot"></i></span>')+'<div class="chat-bubble '+(options?.thinking?'thinking':'')+'">'+safe+tools+'</div>'+(role==='user'?'<span class="chat-avatar"><i data-lucide="user"></i></span>':'');
 thread.appendChild(msg);
 thread.scrollTop=thread.scrollHeight;
 renderIcons();
 return msg;
}
function copyAssistantMessage(button){
 const bubble=button.closest('.chat-bubble');
 const text=bubble?bubble.childNodes[0].textContent:'';
 copyText(text).then(function(){toast('已成功复制到剪贴板','success');}).catch(function(){toast('复制失败，请手动选中文案复制','error');});
}
function usePrompt(text){
 const input=document.getElementById('inspirationInput');
 input.value=text;
 input.focus();
}
function submitOnEnter(event){
 if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();document.getElementById('inspirationSend').click();}
}
function setBusy(isBusy){
 document.getElementById('inspirationSend').disabled=isBusy;
 document.getElementById('inspirationInput').disabled=isBusy;
}
async function sendInspirationChat(event){
 event.preventDefault();
 const input=document.getElementById('inspirationInput');
 const message=input.value.trim();
 if(!message)return;
 input.value='';
 appendMessage('user',message);
 const loading=appendMessage('assistant','正在思考...', {thinking:true});
 setBusy(true);
 try{
  const response=await fetch('/api/inspiration/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:message,history:chatHistory})});
  const data=await response.json();
  loading.remove();
  if(!response.ok)throw new Error(data.detail||data.message||'发送失败');
  chatHistory.push({role:'user',content:message},{role:'assistant',content:data.answer||''});
  chatHistory=chatHistory.slice(-12);
  document.querySelector('#modelPill span').textContent=data.mode==='fallback'?'离线提示':(data.model||'AI 对话');
  appendMessage('assistant',data.answer||'没有收到回复');
 }catch(error){
  loading.remove();
  appendMessage('assistant','发送失败：'+(error&&error.message?error.message:'网络错误'));
 }finally{
  setBusy(false);
  input.focus();
 }
}
function clearChat(){
 chatHistory=[];
 document.getElementById('inspirationInput').value='';
 document.querySelector('#modelPill span').textContent='AI 对话';
 renderWelcome();
}
renderWelcome();
document.addEventListener('DOMContentLoaded',renderIcons);
</script>
</body>
</html>
```

- [ ] **Step 5: Extend common JS coverage**

Modify `tests/test_frontend_common_js.py` loop:

```python
for name in ["templates.html", "history.html", "import.html", "products.html", "search.html", "inspiration.html"]:
```

- [ ] **Step 6: Run page tests to verify GREEN**

Run:

```bash
python -m unittest tests.test_inspiration_page tests.test_frontend_common_js -v
```

Expected: PASS for the new inspiration tests and common JS coverage.

- [ ] **Step 7: Commit the page task**

Run:

```bash
git add main.py templates/inspiration.html tests/test_inspiration_page.py tests/test_frontend_common_js.py
git commit -m "feat: add inspiration chat page"
```

---

### Task 3: Navigation Entry Across Existing Pages

**Files:**
- Modify: `templates/index.html`
- Modify: `templates/rewrite.html`
- Modify: `templates/products.html`
- Modify: `templates/import.html`
- Modify: `templates/templates.html`
- Modify: `templates/history.html`
- Modify: `templates/search.html`
- Modify: `tests/test_inspiration_page.py`

- [ ] **Step 1: Add the failing nav coverage test**

Append to `tests/test_inspiration_page.py`:

```python

class InspirationNavigationTests(unittest.TestCase):
    def test_all_main_templates_link_to_inspiration_after_search(self):
        pages = [
            "index.html",
            "rewrite.html",
            "products.html",
            "import.html",
            "templates.html",
            "history.html",
            "search.html",
            "inspiration.html",
        ]
        for name in pages:
            page = (ROOT / "templates" / name).read_text(encoding="utf-8-sig")
            self.assertIn('href="/app/inspiration"', page, name)
            self.assertRegex(
                page,
                re.compile(r'href="/app/search"[^>]*>.*?</a>\s*<a href="/app/inspiration"', re.S),
                name,
            )

    def test_inspiration_nav_is_active_only_on_inspiration_page(self):
        page = (ROOT / "templates" / "inspiration.html").read_text(encoding="utf-8-sig")

        self.assertIn('<a href="/app/inspiration" class="nav-link on">灵感</a>', page)
```

- [ ] **Step 2: Run nav tests to verify RED**

Run:

```bash
python -m unittest tests.test_inspiration_page.InspirationNavigationTests -v
```

Expected: FAIL because existing templates do not yet link to `/app/inspiration`.

- [ ] **Step 3: Add the nav link to each existing template**

In every existing nav, change the final search link from:

```html
<a href="/app/search" class="nav-link">检索</a>
```

to:

```html
<a href="/app/search" class="nav-link">检索</a><a href="/app/inspiration" class="nav-link">灵感</a>
```

For `templates/search.html`, change:

```html
<a href="/app/search" class="nav-link on">检索</a>
```

to:

```html
<a href="/app/search" class="nav-link on">检索</a><a href="/app/inspiration" class="nav-link">灵感</a>
```

Do not change the active `on` class of any existing page except `templates/inspiration.html`.

- [ ] **Step 4: Run nav tests to verify GREEN**

Run:

```bash
python -m unittest tests.test_inspiration_page.InspirationNavigationTests -v
```

Expected: PASS.

- [ ] **Step 5: Commit the nav task**

Run:

```bash
git add templates/index.html templates/rewrite.html templates/products.html templates/import.html templates/templates.html templates/history.html templates/search.html tests/test_inspiration_page.py
git commit -m "feat: add inspiration navigation entry"
```

---

### Task 4: Final Verification And Local Preview

**Files:**
- No new files unless a verification fix is required.

- [ ] **Step 1: Run focused tests**

Run:

```bash
python -m unittest tests.test_inspiration_api tests.test_inspiration_page tests.test_frontend_common_js -v
```

Expected: PASS.

- [ ] **Step 2: Run the full test suite**

Run:

```bash
python -m unittest discover -s tests -v
```

Expected: PASS. If unrelated pre-existing failures appear, capture the exact failing test names and error messages before changing anything.

- [ ] **Step 3: Start the local server**

Run:

```bash
python main.py
```

Expected: FastAPI starts on `http://localhost:8001/app`.

- [ ] **Step 4: Open and inspect the page**

Open:

```text
http://localhost:8001/app/inspiration
```

Check:

- 「灵感」 nav item is visible immediately after 「检索」.
- Left prompt column and main chat panel render on desktop.
- Mobile width stacks side column above chat panel.
- Prompt chips populate the input.
- Enter sends; Shift+Enter inserts a newline.
- Sending shows a temporary thinking message.
- Reply is appended as an assistant bubble.
- Copy and clear controls work.

- [ ] **Step 5: Commit any verification fixes**

Only if fixes were needed:

```bash
git add <fixed files>
git commit -m "fix: polish inspiration chat verification"
```

---

## Self-Review

- Spec coverage: API, route, independent page, ChatGPT-like layout, nav after search, AI fallback, prompt chips, copy, clear, mobile responsive behavior, and tests are each covered by a task.
- Placeholder scan: no TBD/TODO/fill-in steps remain.
- Type consistency: API request uses `message` and `history`; response uses `answer`, `mode`, `model`; page JavaScript sends the same request and reads the same response fields.
