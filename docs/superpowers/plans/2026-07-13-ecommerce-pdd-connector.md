# Pinduoduo Connector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在拼多多应用获批并取得第一方控制台操作目录后，实现官方 OAuth/签名客户端和店铺经营数据轮询；在此之前交付可测试的安全客户端骨架并诚实保持“待配置/待联调”。

**Architecture:** `PddConnector` 固定访问拼多多官方 OAuth 与 `gw-api.pinduoduo.com` 网关。签名算法由第一方官方文档 golden vector 锁定，具体商品、订单、售后、物流、账务 method 必须从批准应用控制台取得后显式实现。v1 不实现拼多多 WebSocket 消息 consumer。

**Tech Stack:** Pinduoduo Open Platform、official MD5 request signing、httpx、PostgreSQL sync core、`unittest` MockTransport。

## Global Constraints

- 第一方站点的具体 API 目录依赖登录/JavaScript；未从批准应用控制台核实 method、参数、分页和主键前，禁止使用第三方 SDK/博客中的常见方法名。
- 控制台门槛未完成时，`probe_capabilities()` 返回 `official_contract_not_verified`，连接保持 `setup_required`，worker 不安排拼多多资源。
- 网关固定为 `https://gw-api.pinduoduo.com/api/router`；用户不能配置 Base URL。
- 不请求或保存买家姓名、电话、身份证和详细地址。响应含 PII 时适配器立即删除。
- WebSocket 消息能力不进入 v1；不创建 consumer、重连逻辑或 HTTP webhook 伪实现。

---

### Task 1: Capture The Approved Pinduoduo Operation Catalog

**Files:**
- Modify: `integrations/provider_contracts/pdd.json`
- Modify: `docs/integrations/provider-contracts/pdd.md`
- Create: `tests/fixtures/integrations/pdd/catalog_capture/source.json`
- Test: `tests/test_pdd_operation_catalog.py`

- [ ] **Step 1: Write a hard-gate catalog test**

Require logical keys, but never pre-populate unknown method strings:

```text
oauth_authorize
oauth_exchange
oauth_refresh_or_renewal
shop_identity
product_list
product_detail
sku_inventory
order_initial
order_incremental
order_detail
refund_incremental
refund_detail
logistics
finance_or_settlement
```

Each present operation must include exact TOP-style `type`/method, request parameters, page/cursor fields, list path, external key, safe fields, scopes, QPS, errors and first-party source. Missing keys are allowed only with catalog `verification_required` and capability reason.

- [ ] **Step 2: Record the verified general gateway and signature contract**

Record official gateway `https://gw-api.pinduoduo.com/api/router` and the documented signature rule: concatenate client secret, ASCII-key-sorted parameter name/value pairs, and client secret; MD5 and uppercase the hexadecimal result. Verify exact encoding/exclusions with the official application document: <https://open.yangkeduo.com/application/document/browse?idStr=8EC06C399636041E>.

Record OAuth from the official application document: <https://open.yangkeduo.com/application/document/browse?idStr=BD3A776A4D41D5F5>.

- [ ] **Step 3: Export every resource operation from the approved app console**

For each logical key, capture exact method, parameter types, timestamp/token placement, maximum page/window, response path, external IDs, error codes, QPS and approved scope. Save sanitized official request/page/rate/auth fixtures and source SHA-256. Explicitly record when the app lacks a resource.

- [ ] **Step 4: Run evidence tests and commit**

Run: `python -m unittest tests.test_provider_contract_evidence tests.test_pdd_operation_catalog -v`

Commit: `git add integrations/provider_contracts/pdd.json docs/integrations/provider-contracts/pdd.md tests/fixtures/integrations/pdd tests/test_pdd_operation_catalog.py && git commit -m "docs: verify Pinduoduo application operations"`

If approved console access is unavailable, stop provider implementation here. The remaining tasks are executable only after this evidence exists.

---

### Task 2: Implement Pinduoduo OAuth And Official Request Signing

**Files:**
- Create: `integrations/connectors/pdd.py`
- Modify: `integrations/connectors/registry.py`
- Test: `tests/test_pdd_connector.py`

- [ ] **Step 1: Write failing official signature vectors**

Use sanitized first-party examples. Assert stable uppercase MD5 for unordered inputs, correct UTF-8 handling and changes when secret/method/timestamp/param changes. Assert App Secret/access token/signature never appears in repr/log/error. Reject nested values unless the operation catalog defines their exact serialization.

OAuth tests cover authorize/exchange/renewal as documented for the approved app, state/callback integration, aware expiry and auth errors.

- [ ] **Step 2: Run and verify red**

Run: `python -m unittest tests.test_pdd_connector -v`

Expected: connector absent or blocked by missing approved catalog.

- [ ] **Step 3: Implement the signer exactly**

Convert only documented scalar parameters to their official string representation, sort keys by ASCII, concatenate with both client-secret boundaries, MD5 UTF-8 bytes and uppercase. Never log the canonical input. Put the resulting sign and common params in the official transport fields.

- [ ] **Step 4: Implement OAuth and fixed-host API calls**

Use only hosts committed in the approved catalog. Map OAuth result into `TokenBundle` with platform expiry/renewal behavior. Translate official `error_response` codes/request IDs into shared typed exceptions.

- [ ] **Step 5: Register conditionally and commit**

The registry can instantiate the connector only when app config exists; without a complete approved catalog, it exposes pending capability and refuses `fetch_page` with typed `OfficialContractNotVerified`.

Run: `python -m unittest tests.test_pdd_connector tests.test_integration_connector_contract tests.test_integration_oauth -v`

Commit: `git add integrations/connectors/pdd.py integrations/connectors/registry.py tests/test_pdd_connector.py tests/fixtures/integrations/pdd && git commit -m "feat: add Pinduoduo signed API client"`

---

### Task 3: Discover The Shop And Probe Actual Permissions

**Files:**
- Modify: `integrations/connectors/pdd.py`
- Test: `tests/test_pdd_connector.py`

- [ ] **Step 1: Write failing discovery/capability tests**

Fixture cases: approved shop identity, missing product scope, missing refund scope, expired token, catalog-incomplete resource and platform earliest window. Assert no theoretical resource is marked live without a successful probe.

- [ ] **Step 2: Implement discovery and capability probe**

Use only cataloged shop operation and map one shop `AccountIdentity`. Probe each approved resource with the smallest safe request. Report stages `docs_verified`, `oauth_verified`, `backfill_verified`, `incremental_verified`, `reconciled` separately; missing catalog uses `official_contract_not_verified`, missing scope uses `scope_not_granted`.

- [ ] **Step 3: Run and commit**

Run: `python -m unittest tests.test_pdd_connector tests.test_integration_management_api -v`

Commit: `git add integrations/connectors/pdd.py tests/test_pdd_connector.py && git commit -m "feat: probe Pinduoduo shop capabilities"`

---

### Task 4: Normalize Only Catalog-Verified Commerce Resources

**Files:**
- Modify: `integrations/connectors/pdd.py`
- Create: `tests/fixtures/integrations/pdd/catalog_verified/normalized.golden.json`
- Test: `tests/test_pdd_normalization.py`

- [ ] **Step 1: Write golden tests after each operation is verified**

At minimum cover the actually approved product/SKU/inventory, order initial/incremental/detail, refund/detail, logistics and finance resources. Include two pages, duplicate overlap, large numeric IDs, late updates and fake PII. Assert IDs remain strings, money is Decimal, status preserves raw+normalized, timestamps are aware and no PII survives.

- [ ] **Step 2: Run and verify red**

Run: `python -m unittest tests.test_pdd_normalization -v`

Expected: mappings absent. If catalog remains incomplete, the expected test is an explicit typed refusal—not a skipped/green fake connector.

- [ ] **Step 3: Implement one explicit mapper per approved operation**

Hard-code catalog-approved method constants and safe request fields. Build strict normalized records field-by-field; do not persist raw response dictionaries. Derive buyer digest before returning orders and remove names/phones/addresses even if the API included them.

- [ ] **Step 4: Implement exact catalog pagination/windows**

Persist only verified page/cursor values. Initial and incremental orders/refunds use separate operation keys when the platform provides both. Recurring windows overlap by the catalog-safe margin; writer timestamps make duplicates harmless.

- [ ] **Step 5: Run and commit**

Run: `python -m unittest tests.test_pdd_normalization tests.test_pdd_connector tests.test_integration_runner tests.test_integration_redaction -v`

Commit: `git add integrations/connectors/pdd.py tests/fixtures/integrations/pdd tests/test_pdd_normalization.py && git commit -m "feat: sync approved Pinduoduo commerce data"`

---

### Task 5: Prove Polling Consistency And The Absence Of A Fake Webhook

**Files:**
- Modify: `integrations/connectors/pdd.py`
- Test: `tests/test_pdd_polling.py`
- Test: `tests/test_integration_public_boundary.py`

- [ ] **Step 1: Write retry/overlap/late-update scenarios**

Simulate duplicate pages, a record moving between pages, a late refund, page timeout, rate limit and token renewal. Assert one final row, newest platform update wins and cursor resumes from the last committed page.

- [ ] **Step 2: Run and verify red**

Run: `python -m unittest tests.test_pdd_polling -v`

- [ ] **Step 3: Fix cursor and watermark rules per catalog**

Freeze the logical window for the run, persist operation/page/cursor, and advance watermark only after full-window completion. Use scheduler overlap and conditional upsert, never in-memory “seen IDs” as long-term dedupe.

- [ ] **Step 4: Assert v1 has no message consumer**

Source tests assert there is no PDD WebSocket dependency/process and no PDD HTTP event verifier. `/integrations/events/pdd` returns unavailable/404; it must never accept an unsigned body.

- [ ] **Step 5: Run and commit**

Run: `python -m unittest tests.test_pdd_polling tests.test_pdd_normalization tests.test_integration_public_boundary tests.test_integration_runner -v`

Commit: `git add integrations/connectors/pdd.py tests/test_pdd_polling.py tests/test_integration_public_boundary.py && git commit -m "test: harden Pinduoduo polling consistency"`

---

### Task 6: Keep Pending Or Complete Pinduoduo Live Acceptance

**Files:**
- Create: `docs/runbooks/pdd-live-acceptance.md`
- Update: `docs/integrations/provider-contracts/pdd.md`

- [ ] **Step 1: Run all offline/evidence tests**

Run:

```powershell
python -m unittest tests.test_pdd_operation_catalog tests.test_pdd_connector tests.test_pdd_normalization tests.test_pdd_polling -v
```

- [ ] **Step 2: If app approval is unavailable, verify pending state**

UI/API lists exact missing catalog/app/scope/live gates, schedules nothing, and never displays “已接入”. Record pending evidence and do not mark this provider plan complete beyond the safe skeleton/evidence tasks.

- [ ] **Step 3: Once approved, perform OAuth and renewal**

Authorize one法采拼多多店, probe actual scopes/earliest windows, verify Token renewal if supported and credential non-disclosure.

- [ ] **Step 4: Backfill, resume and increment**

Complete platform-allowed history, restart worker between pages, run scheduled and manual windows, and confirm duplicate overlap is idempotent.

- [ ] **Step 5: Reconcile against official export**

Sample 20 orders/refunds; IDs, raw/normalized status and amounts match to the cent. Compare aggregate paid/refunded totals for a finalized window.

- [ ] **Step 6: Mark live only after all gates**

Only real OAuth, renewal, backfill, incremental and reconciliation permit `active`/`reconciled`.

Commit: `git add docs/runbooks/pdd-live-acceptance.md docs/integrations/provider-contracts/pdd.md && git commit -m "docs: record Pinduoduo integration acceptance"`
