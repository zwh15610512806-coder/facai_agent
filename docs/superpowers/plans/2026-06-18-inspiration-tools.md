# Inspiration Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add file attachments, thinking mode, research mode, and data-analysis mode to the Inspiration chat.

**Architecture:** Keep the existing `/api/inspiration/chat` endpoint compatible while adding optional `tool_mode` and `attachments` fields. Add a dedicated attachment extraction service for PDF, Word, text, CSV, and Excel, plus a web research service that returns bounded search-result context for research and data-analysis modes.

**Tech Stack:** FastAPI, Pydantic, OpenAI-compatible DeepSeek API, pdfminer.six, python-docx, pandas/openpyxl, httpx, BeautifulSoup, vanilla JS.

---

### Task 1: Attachment Extraction API

**Files:**
- Create: `services/inspiration_attachments.py`
- Modify: `routers/inspiration.py`
- Test: `tests/test_inspiration_api.py`

- [x] **Step 1: Write failing attachment endpoint tests**

Add tests that upload `.txt` and `.docx` files to `/api/inspiration/attachments`, assert extracted text is returned, and assert image uploads are rejected with 415.

- [x] **Step 2: Run tests to verify failure**

Run: `python -m unittest tests.test_inspiration_api -v`
Expected: failures because `/api/inspiration/attachments` does not exist.

- [x] **Step 3: Implement extraction service and endpoint**

Create `extract_attachment_text()` with support for `.txt`, `.md`, `.json`, `.csv`, `.pdf`, `.docx`, and `.xlsx`. Reject `.jpg`, `.jpeg`, `.png`, `.webp`, and unknown extensions.

- [x] **Step 4: Run attachment tests**

Run: `python -m unittest tests.test_inspiration_api -v`
Expected: attachment endpoint tests pass.

### Task 2: Model Routing And Thinking Output

**Files:**
- Modify: `config.py`
- Modify: `services/ai_service.py`
- Modify: `routers/inspiration.py`
- Test: `tests/test_inspiration_api.py`

- [x] **Step 1: Write failing model-route tests**

Add tests asserting normal chat uses `deepseek-v4-flash`, thinking mode uses `deepseek-v4-pro`, thinking mode enables reasoning parameters, and the response includes `reasoning`.

- [x] **Step 2: Run tests to verify failure**

Run: `python -m unittest tests.test_inspiration_api -v`
Expected: failures because model override and reasoning output are not implemented.

- [x] **Step 3: Implement model overrides**

Add config defaults for `DEEPSEEK_V4_FLASH_MODEL` and `DEEPSEEK_V4_PRO_MODEL`. Extend `AIService.chat()` with optional `model`, `thinking`, `reasoning_effort`, and `return_reasoning` parameters while preserving the existing string return by default.

- [x] **Step 4: Wire Inspiration tool modes**

Add `tool_mode` to the request. Use V4 Flash for chat, research, and analysis; use V4 Pro with thinking enabled for thinking mode.

- [x] **Step 5: Run model tests**

Run: `python -m unittest tests.test_inspiration_api -v`
Expected: model-route tests pass.

### Task 3: Research And Data Analysis Search Context

**Files:**
- Create: `services/web_research.py`
- Modify: `routers/inspiration.py`
- Test: `tests/test_inspiration_api.py`

- [x] **Step 1: Write failing research tests**

Patch `routers.inspiration.search_web` to return two sources. Assert research and analysis requests include the search context in the model prompt and return `sources`.

- [x] **Step 2: Run tests to verify failure**

Run: `python -m unittest tests.test_inspiration_api -v`
Expected: failures because search context is not wired.

- [x] **Step 3: Implement search service and prompt context**

Use DuckDuckGo HTML results through `httpx`, parse title, URL, and snippet, and never raise to the chat endpoint on search failures.

- [x] **Step 4: Run research tests**

Run: `python -m unittest tests.test_inspiration_api -v`
Expected: research tests pass.

### Task 4: Frontend Tool Bar

**Files:**
- Modify: `templates/inspiration.html`
- Test: `tests/test_inspiration_page.py`

- [x] **Step 1: Write failing frontend tests**

Assert the page has upload, thinking, research, and analysis controls; posts `tool_mode`; uploads files to `/api/inspiration/attachments`; renders reasoning and sources.

- [x] **Step 2: Run tests to verify failure**

Run: `python -m unittest tests.test_inspiration_page -v`
Expected: failures because the toolbar is not present.

- [x] **Step 3: Implement toolbar**

Add the composer toolbar above the text input, mode state, file upload flow, attachment chips, reasoning rendering, and source rendering.

- [x] **Step 4: Run frontend tests**

Run: `python -m unittest tests.test_inspiration_page -v`
Expected: frontend tests pass.

### Task 5: Final Verification

**Files:**
- All modified files

- [x] **Step 1: Run focused regression**

Run: `python -m unittest tests.test_inspiration_api tests.test_inspiration_page tests.test_frontend_common_js -v`
Expected: all focused tests pass.

- [x] **Step 2: Run full suite**

Run: `python -m unittest discover -s tests -v`
Expected: all tests pass.

- [x] **Step 3: Browser check**

Open `/app/inspiration`, verify the toolbar renders, mode toggles work, and the page has no horizontal overflow on desktop and mobile.
