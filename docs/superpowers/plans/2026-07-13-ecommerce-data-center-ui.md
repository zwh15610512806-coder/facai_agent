# Ecommerce Data Center UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把现有右下角两个悬浮入口合并为一个“工具”菜单，并交付受管理员保护的 API 接入中心登录、七页签经营数据中心、筛选、商品人工关联和后台导出。

**Architecture:** `static/js/common.js` 是桌面/移动工具入口的唯一数据源；Jinja 页面不再硬编码 FAB。接入中心使用独立 CSS/JS，数据汇总/筛选全部由服务端返回安全 DTO，浏览器只渲染和分页。长区间导出进入 worker，生成 24 小时有效的 CSV/XLSX。

**Tech Stack:** FastAPI/Jinja2、vanilla JavaScript、Lucide local asset、SQLAlchemy/PostgreSQL、openpyxl/CSV、Playwright、`unittest` source/API tests。

## Global Constraints

- 右下角最终只有一个 `.facai-tools-launcher`，不是在现有两个 FAB 旁增加第三个按钮。
- 普通业务页工具菜单显示三项；`/app/import`、`/app/ai-config`、`/app/api-connections` 各自过滤当前项后显示两项。
- 移动端隐藏悬浮 launcher，用同一数组把工具项注入顶部 `.nav-links`。
- 登录页是明确公开例外且不加载共享工具菜单；主页面/API 继续要求 integration administrator session。
- UI/API/导出不显示买家姓名、手机号、身份证、详细地址、Secret、Token 或 ciphertext。
- 实际店铺成交、广告归因成交和广告消耗是不同指标，不在前端合并。
- 列表默认 50、最大 200；交互查询日期最多 366 天，更长范围只能后台导出。

---

### Task 1: Replace Hard-Coded FABs With One Shared Tools Disclosure

**Files:**
- Modify: `static/js/common.js`
- Modify: `static/css/style.css`
- Modify: `static/css/inspiration.css`
- Modify: `static/css/creators.css`
- Modify: `templates/index.html`
- Modify: `templates/rewrite.html`
- Modify: `templates/products.html`
- Modify: `templates/creators.html`
- Modify: `templates/import.html`
- Modify: `templates/templates.html`
- Modify: `templates/history.html`
- Modify: `templates/search.html`
- Modify: `templates/inspiration.html`
- Modify: `templates/ai_config.html`
- Test: `tests/test_frontend_common_js.py`
- Test: `tests/test_mobile_responsive_layout.py`
- Test: `tests/test_inspiration_page.py`
- Test: `tests/test_ai_config.py`
- Test: `tests/test_index_hero.py`
- Test: `tests/test_templates_page.py`
- Test: `tests/test_inspiration_stream.py`
- Test: `tests/test_creators_page.py`
- Test: `tests/test_product_detail_modal.py`
- Test: `e2e/app.spec.js`

- [ ] **Step 1: Rewrite source tests to describe the new single source**

Tests assert all ten templates load `/static/js/common.js?v=tools-20260713`, none contains `data-import-fab` or `ai-config-fab`, and common JS declares exactly:

```javascript
var TOOL_LINKS = [
  {label: '数据导入', href: '/app/import', icon: 'upload'},
  {label: 'AI配置', href: '/app/ai-config', icon: 'settings'},
  {label: 'API接入', href: '/app/api-connections', icon: 'plug-zap'}
];
```

Add DOM/source assertions for one toggle with `aria-expanded/aria-controls`, a labelled nav, Escape/focus restoration, outside click, current-page filtering and mobile links.

- [ ] **Step 2: Run and verify red**

Run:

```powershell
python -m unittest tests.test_frontend_common_js tests.test_mobile_responsive_layout tests.test_inspiration_page tests.test_ai_config tests.test_index_hero tests.test_templates_page tests.test_inspiration_stream tests.test_creators_page tests.test_product_detail_modal -v
```

Expected: old dual-FAB contracts fail.

- [ ] **Step 3: Implement shared desktop disclosure and mobile links**

`initToolNavigation()` uses the single `TOOL_LINKS` array. Desktop injection creates:

```html
<div class="facai-tools-launcher">
  <button id="facaiToolsToggle" type="button" aria-expanded="false" aria-controls="facaiToolsMenu">
    <i data-lucide="wrench"></i><span>工具</span>
  </button>
  <nav id="facaiToolsMenu" aria-label="工具入口" hidden></nav>
</div>
```

Use DOM APIs/textContent, not raw platform content HTML. Toggle handles click/Enter/Space through native button behavior; Escape closes and restores focus; outside click closes without stealing clicked-target focus; open state toggles `body.facai-tools-open`; Lucide rerenders after injection. Export `FacaiUI.toolLinks` as a frozen copy and `FacaiUI.initToolNavigation` for tests.

Current page matching is prefix-aware but exact by tool route, so `/app/api-connections/login` also filters API接入.

- [ ] **Step 4: Replace CSS and template markup**

Delete old `.ai-config-fab/.data-import-fab` rules and hard-coded anchors. Add launcher/menu hover, shadow, z-index and `:focus-visible`. At `max-width: 768px`, hide launcher and show `.nav-mobile-utility`; desktop hides mobile utilities.

Load common JS in the previously missing `index.html` and `rewrite.html`. Use one cache key in all templates/tests.

Keep `/app` inspiration composer clear of the launcher with a shared `--facai-tools-reserve` around 128px; restore normal padding when launcher is hidden. Remove only the dead 184px mobile FAB rule. Remove stale creator FAB selectors.

- [ ] **Step 5: Resolve the generate-page scroll-top collision**

On desktop place `.scroll-top-btn` above the launcher (target `bottom: 90px; right: 28px` after rendered measurement). Add:

```css
body.facai-tools-open .scroll-top-btn {
  visibility: hidden;
  pointer-events: none;
}
```

Preserve the existing mobile safe-area position.

- [ ] **Step 6: Run source tests and Playwright interactions**

Add E2E assertions: one launcher per desktop page; normal page three links; each tool page two; ARIA false→true; Tab/Shift+Tab; Escape focus restore; outside click; mobile 390px launcher hidden and three utility links on normal page; generate scroll button above launcher and hidden while menu open.

Run:

```powershell
python -m unittest tests.test_frontend_common_js tests.test_mobile_responsive_layout tests.test_inspiration_page tests.test_ai_config tests.test_index_hero tests.test_templates_page tests.test_inspiration_stream tests.test_creators_page tests.test_product_detail_modal -v
npm.cmd run test:e2e -- --grep "tools|mobile AI work|scroll top"
```

- [ ] **Step 7: Commit the right-bottom change**

Stage only the files listed in this task:

```powershell
git add static/js/common.js static/css/style.css static/css/inspiration.css static/css/creators.css templates/index.html templates/rewrite.html templates/products.html templates/creators.html templates/import.html templates/templates.html templates/history.html templates/search.html templates/inspiration.html templates/ai_config.html tests/test_frontend_common_js.py tests/test_mobile_responsive_layout.py tests/test_inspiration_page.py tests/test_ai_config.py tests/test_index_hero.py tests/test_templates_page.py tests/test_inspiration_stream.py tests/test_creators_page.py tests/test_product_detail_modal.py e2e/app.spec.js
git diff --cached --check
git commit -m "feat: replace floating shortcuts with shared tools menu"
```

Review `git diff --cached --name-only` before committing so unrelated templates/tests are not staged.

---

### Task 2: Add The Administrator Login And Protected Page Shell

**Files:**
- Create: `templates/api_connections_login.html`
- Create: `templates/api_connections.html`
- Create: `static/css/api-connections.css`
- Create: `static/js/api-connections-login.js`
- Create: `static/js/api-connections.js`
- Modify: `main.py`
- Modify: `scripts/e2e_server.py`
- Create: `tests/test_integration_pages.py`

- [ ] **Step 1: Write failing page/session redirect tests**

Assert:

- GET login is public 200 and never loads common tools JS;
- GET main page without session returns 303 to `/app/api-connections/login?next=%2Fapp%2Fapi-connections`;
- API unauthenticated still returns JSON 401, never redirect;
- a valid cookie returns main page 200;
- password/session config missing disables login with “安全配置未完成”;
- other credential config missing after login shows a read-only banner but does not block logout/data already stored;
- `next` only accepts `/app/api-connections` path prefix, never external URLs.

- [ ] **Step 2: Run and verify red**

Run: `python -m unittest tests.test_integration_pages -v`

Expected: page/templates absent.

- [ ] **Step 3: Add page routes without circular imports**

Keep Jinja page routes in `main.py`, matching existing project convention. Use `integration_admin_session_or_none(request)` to decide redirect or render; do not use the JSON-401 dependency directly on the page. Login context contains readiness booleans/error codes only, never configured values.

- [ ] **Step 4: Build accessible login**

Password uses `autocomplete="current-password"`; errors use `role="alert"`; lock countdown uses `aria-live="polite"`. JS posts strict JSON to `/api/integrations/session`, follows only server-validated local `next`, displays 429 retry seconds and never logs/retains the password after submit. Provide a simple `/app` return link.

- [ ] **Step 5: Seed safe E2E-only settings**

In `scripts/e2e_server.py`, generate/set a fixed test scrypt hash, test session/master keys, `FACAI_INTEGRATIONS_INTERNAL_BASE_URL=http://127.0.0.1:{actual_e2e_port}`, `FACAI_INTEGRATIONS_PUBLIC_BASE_URL=https://callbacks.test.invalid`, and a temporary absolute archive directory before importing `main`. Assert the origins differ and page requests use the exact loopback origin; keep worker disabled. Values must be clearly test-only and isolated from business data.

- [ ] **Step 6: Run tests and commit**

Run: `python -m unittest tests.test_integration_pages tests.test_integration_auth tests.test_security_hardening -v`

Commit: `git add templates/api_connections_login.html templates/api_connections.html static/css/api-connections.css static/js/api-connections-login.js static/js/api-connections.js main.py scripts/e2e_server.py tests/test_integration_pages.py && git commit -m "feat: add integration administrator pages"`

---

### Task 3: Expose Safe Reporting And Product-Link APIs

**Files:**
- Create: `integrations/reporting.py`
- Modify: `integrations/schemas.py`
- Modify: `routers/integrations.py`
- Test: `tests/test_integration_data_api.py`

- [ ] **Step 1: Write failing query-contract tests**

Test strict enums/unknown fields/date errors, default 50/max 200 pagination, stable ordering (`business_time DESC, id DESC`), provider/connection/date/status/search filters, 366-day limit, Decimal-as-string JSON, Asia/Shanghai display boundaries, product-link lifecycle and response-wide PII/credential denylist. Overview fixtures must cover paid/shipped/completed vs pending/closed orders, completed vs pending refunds, zero-order AOV, CNY/non-CNY rows, order-ledger/provider-daily source selection, and multiple ad entity levels without double counting.

All list responses use the existing repository shape:

```json
{"items":[],"total":0,"page":1,"per_page":50,"total_pages":1}
```

- [ ] **Step 2: Run and verify red**

Run: `python -m unittest tests.test_integration_data_api -v`

Expected: reporting endpoints absent.

- [ ] **Step 3: Define filters and safe DTOs**

Common query fields: `provider`, `connection_id`, `date_from`, `date_to`, `page`, `per_page`. Orders add normalized `status/search`; products add `status/search/link_status`; refunds add `status/search`; ad entities add `entity_type/search`; ad metrics add `granularity`; runs add `status/source/resource_type`.

Search operates only on safe external IDs/product titles/SKU names, never buyer fields. Money/ratios serialize as fixed Decimal strings; timestamps serialize as UTC ISO and provide display date grouping from Asia/Shanghai.

- [ ] **Step 4: Implement server-side overview**

`GET /api/integrations/data/overview` defaults to 30 days and returns summary plus daily series. Separate keys:

```json
{
  "actual_sales":"0.00",
  "order_count":0,
  "refund_amount":"0.00",
  "average_order_value":"0.00",
  "ad_spend":"0.00",
  "ad_attributed_sales":"0.00",
  "daily":[]
}
```

KPI definitions and sources are fixed:

- At capability reconciliation, each connection records one `overview_commerce_source`: `order_ledger` when orders/refunds are reconciled, otherwise `provider_daily` only when that resource is reconciled. The API never combines the two sources for one connection/day; mixed multi-connection responses aggregate each connection once and return a source breakdown.
- For `order_ledger`, `actual_sales` is gross `paid_amount` for distinct orders with normalized status `paid|shipped|completed`, bucketed by non-null `paid_at` in Asia/Shanghai; pending/closed and missing-paid-time rows are excluded and counted in a data-quality warning. `order_count` is the count of those distinct orders. Refunds do not reduce this value.
- `refund_amount` is the sum of distinct refunds with normalized status `completed`, bucketed by non-null `completed_at`. `average_order_value = actual_sales / order_count`, quantized to two decimals with zero when the denominator is zero.
- For `provider_daily`, use that connection/day's single `commerce_daily_metrics` row at `granularity="day"` for all four commerce values. Do not supplement it from order/refund rows.
- `ad_spend` and `ad_attributed_sales` come only from one non-overlapping reconciled ad aggregation level recorded in capability metadata, preferring `entity_type="account"`; never sum account/campaign/creative/material levels together.
- Overview totals include CNY rows only. Return counts/currencies excluded from aggregation rather than converting or silently mixing them.

Never add ad-attributed sales to actual shop sales. The daily series uses the same source/status/time rules as summary totals; tests assert the sum of daily values equals the summary across DST-free Asia/Shanghai boundaries and pagination does not affect aggregates.

- [ ] **Step 5: Implement list, ad-entity and product-link endpoints**

Add orders/products/refunds/ad-entities/ad-metrics endpoints plus:

```text
PUT    /api/integrations/data/products/{commerce_product_id}/link
DELETE /api/integrations/data/products/{commerce_product_id}/link
```

Link PUT accepts strict `product_id`; confirms both rows exist; upserts link and audits administrator session digest. DELETE removes only the link.

- [ ] **Step 6: Run tests and commit**

Run: `python -m unittest tests.test_integration_data_api tests.test_integration_management_api -v`

Commit: `git add integrations/reporting.py integrations/schemas.py routers/integrations.py tests/test_integration_data_api.py && git commit -m "feat: expose integration reporting APIs"`

---

### Task 4: Generate Audited CSV And Excel Exports In The Worker

**Files:**
- Create: `integrations/exports.py`
- Modify: `integrations/sync/worker.py`
- Modify: `integrations/schemas.py`
- Modify: `routers/integrations.py`
- Test: `tests/test_integration_exports.py`

- [ ] **Step 1: Write failing job/API/download tests**

Cover 202 create, strict resource/format/filter body, status polling, worker result, CSV BOM, XLSX cells, filter parity with UI, long date range allowed only here, no PII, path traversal resistance, failed job, 24-hour expiry/410, cleanup and audit. Include platform-controlled strings beginning with `=`, `+`, `-`, `@`, tab/CR/LF and leading whitespace before those characters; prove neither CSV nor XLSX contains an executable formula. Prove unauthenticated status/download returns 401, while a newly authenticated administrator session can retrieve an export created under an earlier session; the public job ID is a server-generated UUID and never a sequential database ID.

- [ ] **Step 2: Run and verify red**

Run: `if (-not $env:FACAI_TEST_DATABASE_URL) { throw 'FACAI_TEST_DATABASE_URL is required' }; python -m unittest tests.test_integration_exports -v`

Expected: export model/service/routes absent.

- [ ] **Step 3: Use the sync-core export-job persistence**

Use the `IntegrationExportJob` table created by sync-core revision 0002. Confirm it has requester session digest, resource, sanitized filters JSON, format, status, relative path, row count, error code/summary, created/started/completed/expires timestamps and named indexes for requester/status/expiry. This is a single-company, single-role administration surface: requester digest is audit metadata only, not an ACL. Any currently valid integration-admin session may poll/download any known export UUID; no unauthenticated request may do so. Do not add a parallel export table or runtime DDL.

- [ ] **Step 4: Implement safe generation**

`POST /api/integrations/exports` creates model + deduped worker job and returns 202. Worker reuses reporting query builders, streams rows to `archive_dir/exports/${job_uuid}.csv.tmp` or `${job_uuid}.xlsx.tmp`, then atomically renames. CSV is UTF-8 with BOM; XLSX uses write-only openpyxl. Use explicit safe columns per resource and string IDs.

Implement one `escape_spreadsheet_text(value: str) -> str` seam used by both formats. If `value.lstrip()` begins with `=`, `+`, `-` or `@`, or the original begins with tab/CR/LF, prefix a literal ASCII apostrophe and write it as text; never sanitize numeric `Decimal`/integer cells through this function. For XLSX, create explicit text cells (`data_type="s"`) for all platform-controlled strings and assert with openpyxl that no exported cell has `data_type="f"`. Preserve external IDs—including leading zeros—as text. Unit fixtures cover formula payloads in names, titles, raw statuses, tracking numbers and metadata-derived labels.

- [ ] **Step 5: Implement status and download**

`GET /exports/{id}` returns status/row count/expiry and a download URL only when ready. `GET /exports/{id}/download` resolves containment, requires a current `require_integration_admin` session, returns `Cache-Control: no-store`, and returns 410 after expiry. Both routes write the current session digest and export creator digest to allowlisted audit fields without exposing either value in the response. Daily worker cleanup deletes files then marks expired; failures remain retryable.

- [ ] **Step 6: Run tests and commit**

Run:

```powershell
if (-not $env:FACAI_TEST_DATABASE_URL) { throw 'FACAI_TEST_DATABASE_URL is required' }
python -m unittest tests.test_integration_exports tests.test_integration_data_api tests.test_integration_worker tests.test_alembic_postgres -v
```

Commit: `git add integrations/exports.py integrations/sync/worker.py integrations/schemas.py routers/integrations.py tests/test_integration_exports.py && git commit -m "feat: export integration data asynchronously"`

---

### Task 5: Build The Seven-Tab Integration Center

**Files:**
- Modify: `templates/api_connections.html`
- Modify: `static/css/api-connections.css`
- Modify: `static/js/api-connections.js`
- Modify: `tests/frontend_source.py`
- Modify: `tests/test_integration_pages.py`
- Create: `e2e/api-connections.spec.js`

- [ ] **Step 1: Write failing DOM and E2E contracts**

Require seven real tabs and panels, keyboard/ARIA behavior, security banner, platform cards, safe tables, filters/pagination, product link, purge dialog, export polling, 401 redirect and mobile layout. Add `api_connections.html` to `_PAGE_ASSETS` with its CSS/JS.

- [ ] **Step 2: Run and verify red**

Run: `python -m unittest tests.test_integration_pages -v`

Expected: shell lacks seven tabs/actions.

- [ ] **Step 3: Implement accessible tab state**

Tabs are `connections`, `overview`, `orders`, `products`, `refunds`, `ads`, `sync-runs`. Use `role=tablist`, buttons with `role=tab/aria-selected/aria-controls`, and panels with `role=tabpanel/tabindex=0/hidden`. Left/Right/Home/End move/select, and state syncs to validated `?tab=`. On narrow screens, tablist scrolls horizontally; it does not enter global nav.

- [ ] **Step 4: Implement connection management UI**

Render app config/connection cards using `textContent` or `FacaiUI.escHtml`. Show configured/masked Secret only, scope, expiry, capability, last sync and status. Provide save, authorize, sync, reauthorize, disable and authorization revoke. Purge uses native `<dialog>` with password plus exact display-name confirmation; dangerous submit remains disabled until exact match.

All async actions disable/busy their button. A 401 redirects to login; errors go through `FacaiUI.getApiErrorMessage`.

- [ ] **Step 5: Implement data tabs and filters**

Use one filter bar pattern. Provider change reloads connection options; filter change resets page 1; page sizes are 50/100/200. Request only active tab and abort stale fetches. Panels expose `aria-busy`; loading/empty/error use `role=status`/`aria-live`.

Orders contain no buyer PII. Overview labels “实际成交”“广告归因成交”“广告消耗” separately. Ads panel fetches both entities and metrics. Products provide explicit link/unlink dialog to existing Product search.

- [ ] **Step 6: Implement export lifecycle**

Build export body from current tab and filters, poll status every two seconds until ready/failed, stop timers on tab change/unload, then show backend download URL. Expired download prompts recreation.

- [ ] **Step 7: Add Playwright route-mocked flows**

Test real login/logout UI; seven-tab keyboard/ARIA; correct filter/page query; no PII text; overview metric separation; app Secret mask; purge double confirmation; 401 redirect; export 202→ready→download; 390px no horizontal page overflow.

- [ ] **Step 8: Run UI tests and commit**

Run:

```powershell
python -m unittest tests.test_integration_pages tests.test_integration_data_api tests.test_integration_exports -v
npm.cmd run test:e2e -- --grep "API connections"
```

Commit: `git add templates/api_connections.html static/css/api-connections.css static/js/api-connections.js tests/frontend_source.py tests/test_integration_pages.py e2e/api-connections.spec.js && git commit -m "feat: add seven-tab integration data center"`

---

### Task 6: Frontend And Reporting Verification Gate

**Files:**
- Verify files in this plan.

- [ ] **Step 1: Run all focused Python tests**

Run:

```powershell
python -m unittest tests.test_frontend_common_js tests.test_mobile_responsive_layout tests.test_integration_pages tests.test_integration_data_api tests.test_integration_exports -v
```

- [ ] **Step 2: Run complete E2E**

Run: `npm.cmd run test:e2e`

Expected: desktop/mobile existing flows and API connection flows pass.

- [ ] **Step 3: Run full project gates**

Run:

```powershell
python -m compileall -q .
python -m unittest discover -s tests -v
git diff --check
```

- [ ] **Step 4: Perform rendered browser inspection**

At desktop and 390px mobile, inspect `/app`, `/app/generate`, `/app/import`, `/app/ai-config`, login and all seven tabs. Verify right-bottom single launcher, scroll-top separation, keyboard focus, no horizontal overflow, masks/PII safety and all empty/loading/error states.
