# Taobao Connector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在淘宝应用获批后交付 TOP OAuth/签名客户端，轮询同步店铺、商品/SKU/库存、订单、退款、物流和获批账务数据；未完成真实联调前保持“待配置/待联调”。

**Architecture:** `TaobaoConnector` 只访问淘宝固定 OAuth 与 TOP 网关，使用严格安全字段列表，绝不请求收件人 PII。首次订单按平台允许窗口回溯，后续使用修改时间增量接口并重叠十分钟；TOP 分页/乱序由统一 cursor 和 platform timestamp 幂等处理。v1 不实现 TMC。

**Tech Stack:** Taobao Open Platform/TOP、httpx、official OAuth and request signing、PostgreSQL sync core、`unittest` MockTransport。

## Global Constraints

- 取得淘宝应用、回调审批和实际 scope 前可以完成公共文档契约与离线客户端，但连接不能显示 `active`。
- 只请求经营所需安全字段。任何包含 receiver/name/mobile/address/ID-card 的 fields 参数都应使测试失败。
- TOP gateway 固定为 `https://eco.taobao.com/router/rest`；OAuth host 固定为官方域名。用户不能配置 Base URL。
- TMC consumer、长连接、重连和消息一致性明确排除 v1；`/integrations/events/taobao` 不注册处理器。
- 首次订单窗口受官方近三个月等限制时，capability report 显示实际 earliest date，不承诺更早历史。

---

### Task 1: Verify Taobao Operations, Safe Fields And App Scopes

**Files:**
- Modify: `integrations/provider_contracts/taobao.json`
- Modify: `docs/integrations/provider-contracts/taobao.md`
- Create: `tests/fixtures/integrations/taobao/trades_sold/source.json`
- Test: `tests/test_taobao_operation_catalog.py`

- [ ] **Step 1: Write failing catalog and safe-field tests**

Require exact operation keys for OAuth exchange/refresh (if supported for the app), shop, products, inventory products, SKUs, initial/incremental orders, order detail, refunds, refund detail, logistics and trade amount. Every `fields` list must pass a denylist check for PII field names.

- [ ] **Step 2: Record public official operations**

Use current first-party documentation:

- OAuth endpoints and flow: <https://developer.alibaba.com/docs/doc.htm?articleId=102635&docType=1&treeId=1>.
- `taobao.shop.seller.get`, safe shop identity: <https://developer.alibaba.com/docs/api.htm?apiId=42908>.
- `taobao.items.onsale.get` and `taobao.items.inventory.get`, modified-window pagination, `num_iid`: <https://developer.alibaba.com/docs/api.htm?apiId=18> and <https://developer.alibaba.com/docs/api.htm?apiId=162>.
- `taobao.item.skus.get`, `num_iids`, `sku_id`: <https://developer.alibaba.com/docs/api.htm?apiId=30>.
- `taobao.trades.sold.get`, initial sold trades, `tid`: <https://developer.alibaba.com/docs/api.htm?apiId=46>.
- `taobao.trades.sold.increment.get`, modified incremental trades: <https://developer.alibaba.com/docs/api.htm?apiId=128>.
- `taobao.trade.fullinfo.get`, safe trade detail: <https://developer.alibaba.com/docs/api.htm?apiId=54>.
- `taobao.refunds.receive.get`, refund list: <https://developer.alibaba.com/docs/api.htm?apiId=52>.
- `taobao.logistics.orders.detail.get`, safe logistics fields: <https://developer.alibaba.com/docs/api.htm?apiId=234>.
- `taobao.trade.amount.get`, trade accounting: <https://developer.alibaba.com/docs/api.htm?apiId=10481>.

Also verify `taobao.refund.get` in current official docs/control panel before coding its exact fields.

- [ ] **Step 3: Confirm approved-app details**

Capture the exact TOP sign method/canonicalization, token response/refresh behavior, approved scopes, QPS, per-operation window/page limits, response list paths, error codes and safe field availability. Store sanitized request/page/auth/rate fixtures with source hashes.

- [ ] **Step 4: Run and commit evidence**

Run: `python -m unittest tests.test_provider_contract_evidence tests.test_taobao_operation_catalog -v`

Commit: `git add integrations/provider_contracts/taobao.json docs/integrations/provider-contracts/taobao.md tests/fixtures/integrations/taobao tests/test_taobao_operation_catalog.py && git commit -m "docs: verify Taobao application operations"`

---

### Task 2: Implement TOP OAuth, Session Refresh And Signing

**Files:**
- Create: `integrations/connectors/taobao.py`
- Modify: `integrations/connectors/registry.py`
- Test: `tests/test_taobao_connector.py`

- [ ] **Step 1: Write failing official signing vectors**

Using sanitized console examples, assert exact signature for fixed params. Input order must not matter; changing method, timestamp, session or business param must change signature. Secret/session/signature must never enter URL logs, repr or error summaries beyond protocol-required transport fields.

OAuth tests cover authorize query, code exchange, app-specific refresh/renewal behavior, aware expiry, invalid grant and state/callback integration.

- [ ] **Step 2: Run and verify red**

Run: `python -m unittest tests.test_taobao_connector -v`

Expected: connector absent.

- [ ] **Step 3: Implement verified TOP canonicalization**

Build system params (`method`, app key, timestamp, format, version, sign method and session when required) and business params exactly from catalog. Implement only the approved sign method; do not silently fall back between MD5/HMAC variants. Request only fixed official gateway and reject redirects.

- [ ] **Step 4: Implement OAuth/session mapping and errors**

Map OAuth result into `TokenBundle`, treating the TOP session as the access credential and using platform expiry/refresh semantics. Translate TOP error/sub-error/request IDs into shared typed exceptions with safe summaries.

- [ ] **Step 5: Register conditionally, test and commit**

Registry exposes Taobao connector code even without credentials, but provider readiness remains `setup_required` until app config and approved catalog exist.

Run: `python -m unittest tests.test_taobao_connector tests.test_integration_connector_contract tests.test_integration_oauth -v`

Commit: `git add integrations/connectors/taobao.py integrations/connectors/registry.py tests/test_taobao_connector.py tests/fixtures/integrations/taobao && git commit -m "feat: add Taobao TOP client"`

---

### Task 3: Discover The Shop And Probe Resource Permissions

**Files:**
- Modify: `integrations/connectors/taobao.py`
- Test: `tests/test_taobao_connector.py`

- [ ] **Step 1: Write failing identity/capability cases**

Test one shop identity, missing item scope, missing refund scope, expired session, documented history boundary and optional trade-amount permission denied. Assert partial resource permissions do not masquerade as full connection success.

- [ ] **Step 2: Implement discovery and probe**

Call `taobao.shop.seller.get` with only `sid,title,pic_path`; map one shop connection. Probe each resource with its approved safe fields and smallest page; return documented/app-approved/live stages, missing scopes, earliest date and limits.

- [ ] **Step 3: Run and commit**

Run: `python -m unittest tests.test_taobao_connector tests.test_integration_management_api -v`

Commit: `git add integrations/connectors/taobao.py tests/test_taobao_connector.py && git commit -m "feat: probe Taobao shop capabilities"`

---

### Task 4: Normalize Products, SKUs And Inventory

**Files:**
- Modify: `integrations/connectors/taobao.py`
- Create: `tests/fixtures/integrations/taobao/items/normalized.golden.json`
- Test: `tests/test_taobao_products.py`

- [ ] **Step 1: Write failing product pagination/mapping tests**

Fixtures cover on-sale and inventory lists, overlapping `num_iid`, two pages, updated item, SKU list, stock/quantity, off-shelf state and a numeric ID above JavaScript safe range. Assert duplicate lists merge by connection/product ID and newest platform timestamp.

- [ ] **Step 2: Run and verify red**

Run: `python -m unittest tests.test_taobao_products -v`

Expected: product fetch/mapping absent.

- [ ] **Step 3: Implement explicit safe field lists and pagination**

Hard-code reviewed safe fields from catalog. Use `start_modified/end_modified/page_no/page_size` within verified limits, map `num_iid` and `sku_id` as strings, normalize product status, and emit inventory snapshots without requesting seller/buyer address data.

- [ ] **Step 4: Run and commit**

Run: `python -m unittest tests.test_taobao_products tests.test_taobao_connector tests.test_integration_writer -v`

Commit: `git add integrations/connectors/taobao.py tests/fixtures/integrations/taobao tests/test_taobao_products.py && git commit -m "feat: sync Taobao catalog and inventory"`

---

### Task 5: Normalize Orders, Refunds, Logistics And Accounting

**Files:**
- Modify: `integrations/connectors/taobao.py`
- Create: `tests/fixtures/integrations/taobao/trades/normalized.golden.json`
- Test: `tests/test_taobao_orders.py`

- [ ] **Step 1: Write failing initial/incremental/refund tests**

Cover initial sold list, incremental modified list, full safe detail, parent `tid`, item `oid`, refunds, one refund detail, logistics safe fields and trade amount. Include PII in the mocked platform response but assert normalized/archive inputs omit it. Test page `has_next`, duplicate trades across overlap and late older updates.

- [ ] **Step 2: Run and verify red**

Run: `python -m unittest tests.test_taobao_orders -v`

Expected: order/refund fetch missing.

- [ ] **Step 3: Implement initial and incremental order strategies**

Initial backfill uses `taobao.trades.sold.get` only within capability earliest date. Recurring sync uses `taobao.trades.sold.increment.get`, splits each modified window to at most the verified one-day limit and overlaps prior watermark by ten minutes. Page using `page_no/page_size/use_has_next` and let conditional upsert resolve duplicates.

- [ ] **Step 4: Implement detail, refunds, safe logistics and accounting**

Request only catalog-approved safe fields. Map all IDs as strings and amounts with Decimal. Logistics fields are limited to `tid,order_code,status,type,company_name,created,modified,sub_tids,is_split`; never request receiver fields. Trade amount maps to settlement/accounting records only when scope is approved.

- [ ] **Step 5: Run and commit**

Run: `python -m unittest tests.test_taobao_orders tests.test_taobao_connector tests.test_integration_runner tests.test_integration_redaction -v`

Commit: `git add integrations/connectors/taobao.py tests/fixtures/integrations/taobao tests/test_taobao_orders.py && git commit -m "feat: sync Taobao orders and aftersales"`

---

### Task 6: Prove Polling Consistency Without TMC

**Files:**
- Test: `tests/test_taobao_polling.py`
- Modify: `integrations/connectors/taobao.py`

- [ ] **Step 1: Write failure-recovery scenarios**

Simulate a trade modified at a page boundary, duplicated in the next ten-minute overlap, a refund arriving after the order, page two timeout/retry and a session refresh during the window. Assert one final row, newest timestamp wins and cursor advances only after committed pages.

- [ ] **Step 2: Run and verify red**

Run: `python -m unittest tests.test_taobao_polling -v`

- [ ] **Step 3: Close pagination/watermark gaps**

Persist cursor with operation key, page number and fixed window; never recompute window mid-run. Use response `has_next/total_results` exactly as cataloged. After window completion, advance watermark to the fixed exclusive end, not the newest row alone.

- [ ] **Step 4: Assert no message consumer exists**

Source tests assert no TMC dependency/module/process and no Taobao HTTP event handler. `/integrations/events/taobao` returns unavailable/404 under the public boundary.

- [ ] **Step 5: Run and commit**

Run: `python -m unittest tests.test_taobao_polling tests.test_taobao_orders tests.test_integration_runner -v`

Commit: `git add integrations/connectors/taobao.py tests/test_taobao_polling.py && git commit -m "test: harden Taobao polling consistency"`

---

### Task 7: Keep Pending Or Complete Taobao Live Acceptance

**Files:**
- Create: `docs/runbooks/taobao-live-acceptance.md`
- Update: `docs/integrations/provider-contracts/taobao.md`

- [ ] **Step 1: Pass the complete offline contract suite**

Run:

```powershell
python -m unittest tests.test_taobao_operation_catalog tests.test_taobao_connector tests.test_taobao_products tests.test_taobao_orders tests.test_taobao_polling -v
```

- [ ] **Step 2: If credentials/scopes are unavailable, verify honest pending state**

UI/API must show `setup_required` or `permission_limited`, list the exact missing app/scope/live gates, schedule no unverified resource and never show “已接入”. Record this result and stop without claiming live completion.

- [ ] **Step 3: When approved, perform OAuth, refresh, backfill and incremental sync**

Authorize one法采淘宝店，probe scopes, complete platform-allowed backfill, restart worker mid-window, and run one scheduled plus manual sync.

- [ ] **Step 4: Reconcile against official export**

Sample 20 orders/refunds; IDs/status/amounts match to cent. Compare aggregate order count, paid and refunded totals for the same finalized window.

- [ ] **Step 5: Mark live only after all gates**

Set stage `reconciled` and connection `active` only after real OAuth, refresh, backfill, incremental and reconciliation pass.

Commit: `git add docs/runbooks/taobao-live-acceptance.md docs/integrations/provider-contracts/taobao.md && git commit -m "docs: record Taobao integration acceptance"`
