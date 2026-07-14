# Doudian Connector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用法采抖店应用完成真实店铺 OAuth、商品/SKU/库存、订单、售后同步，并以官方验签事件快速入队、轮询重叠窗口最终对账。

**Architecture:** `DoudianConnector` 通过抖店固定官方网关和独立 Token 实现签名请求。核心读资源由轮询同步；事件回调先验证官方签名，在适配器边界删除 PII，以 `msg_id` 幂等写入 event inbox 并入队，worker 再处理。物流、结算和经营分析只有在应用控制台确认操作/scope 后启用。

**Tech Stack:** Doudian Open Platform official API、HMAC-SHA256、httpx MockTransport、FastAPI public event router、PostgreSQL sync core、`unittest`。

## Global Constraints

- 抖店 OAuth/Token 不能与千川复用。
- 当前公开第一方文档已确认 token、商品、订单、售后核心读取操作；消息签名、物流、结算下载和经营分析仍须在批准应用控制台逐项确认。
- 下单人、收件人姓名、电话、身份证和详细地址在 connector 收到响应后立即删除；fixtures 只能包含显眼的假 PII 哨兵，并断言其不会越过适配器。
- 事件只改善时效，不替代每 15 分钟订单/售后轮询；重复、迟到和乱序必须由 inbox 与 platform timestamp 幂等处理。
- 未获批资源显示 `permission_limited`，不能把整店误报为同步失败。

---

### Task 1: Verify The Doudian App Contract And Event Signature

**Files:**
- Modify: `integrations/provider_contracts/doudian.json`
- Modify: `docs/integrations/provider-contracts/doudian.md`
- Create: `tests/fixtures/integrations/doudian/order_search_list/source.json`
- Test: `tests/test_doudian_operation_catalog.py`

- [ ] **Step 1: Write failing catalog tests**

Core required keys:

```text
oauth_authorize
token_create
token_refresh
shop_identity
product_list_v2
product_detail
order_search_list
order_detail
aftersale_list
aftersale_detail
event_verify
event_ack
```

Optional keys `logistics`, `settlement`, `business_metrics` are capability-gated and absent until verified.

- [ ] **Step 2: Record public official contracts**

Use only current first-party documentation:

- `/token/create`, `method=token.create`, authorization code exchange and returned shop/token fields: <https://op.jinritemai.com/docs/guide-docs/9/22>.
- `/token/refresh`, `method=token.refresh`, refresh-token grant: <https://op.jinritemai.com/docs/api-docs/162/1601>.
- `/product/listV2`, update window, 1-based page, size at most 100, `product_id_str`: <https://op.jinritemai.com/docs/api-docs/14/633>.
- `/product/detail`, `product_id`, product key `product_id_str`, SKU key `spec_prices[].sku_id`, stock `stock_num`: <https://op.jinritemai.com/docs/api-docs/14/56>.
- `/order/searchList`, update window, `order_by=update_time`, 0-based page, size at most 100, `shop_order_id`/`sku_order_id`: <https://op.jinritemai.com/docs/api-docs/15/1342>.
- `/order/orderDetail`, detail enrichment: <https://op.jinritemai.com/docs/guide-docs/205>.
- `/afterSale/List`, update window, ascending update order, 0-based page, size at most 100, `has_more`, `aftersale_id`: <https://op.jinritemai.com/docs/api-docs/17/1295>.

Capture `/afterSale/Detail` and any changed parameter paths from the approved application console before implementation.

- [ ] **Step 3: Capture signing and message evidence**

From official app console, record the exact HMAC-SHA256 canonical-string algorithm, included/excluded fields, timestamp tolerance, body canonicalization, signature encoding and error codes. Record event callback challenge/verification, header/body signature fields, `msg_id`, the safe shop/authorization subject field, whether `msg_id` is provider-global or subject-scoped, event type, ack body and retry policy. Sanitize all samples. Without evidence for both subject routing and ID scope, event ingestion remains disabled while polling continues.

- [ ] **Step 4: Run evidence tests and commit**

Run: `python -m unittest tests.test_provider_contract_evidence tests.test_doudian_operation_catalog -v`

Commit: `git add integrations/provider_contracts/doudian.json docs/integrations/provider-contracts/doudian.md tests/fixtures/integrations/doudian tests/test_doudian_operation_catalog.py && git commit -m "docs: verify Doudian application operations"`

---

### Task 2: Implement Doudian OAuth, Refresh And HMAC-SHA256 Requests

**Files:**
- Create: `integrations/connectors/doudian.py`
- Modify: `integrations/connectors/registry.py`
- Test: `tests/test_doudian_connector.py`

- [ ] **Step 1: Write failing signature and OAuth tests**

Use official sanitized examples as golden vectors. One-character changes in method, timestamp, business params or secret must change the signature; parameter order in input must not. Assert signature/App Secret/Token never appears in safe logs or errors.

OAuth tests cover URL, code exchange, refresh, returned `shop_id/shop_name`, aware expiries and error translation. Request tests cover official gateway only, success, auth/permission/rate/5xx, malformed response and request ID.

- [ ] **Step 2: Run and verify red**

Run: `python -m unittest tests.test_doudian_connector -v`

Expected: connector absent.

- [ ] **Step 3: Implement the verified canonical signer**

Implement `sign_request()` exactly from the catalog golden vector; take App Secret as a `SecretStr`/non-repr parameter, canonicalize only documented fields and return the documented encoding. Do not create a “fallback” signing mode.

- [ ] **Step 4: Implement OAuth and request helper**

Use fixed `https://openapi-fxg.jinritemai.com` gateway and catalog token/authorize hosts. Build common fields and business `param_json` exactly as documented. Map token results into `TokenBundle(subject_external_id=shop_id)` and shop into one `AccountIdentity(connection_type="shop")`.

- [ ] **Step 5: Register, test and commit**

Run: `python -m unittest tests.test_doudian_connector tests.test_integration_connector_contract tests.test_integration_oauth -v`

Commit: `git add integrations/connectors/doudian.py integrations/connectors/registry.py tests/test_doudian_connector.py tests/fixtures/integrations/doudian && git commit -m "feat: add Doudian OAuth and signed client"`

---

### Task 3: Probe Store Capabilities And Earliest Windows

**Files:**
- Modify: `integrations/connectors/doudian.py`
- Test: `tests/test_doudian_connector.py`

- [ ] **Step 1: Add failing capability cases**

Test a fully approved shop, missing售后 scope, expired authorization, 90-day order limit, optional settlement permission denied and an app missing verified event signature contract.

- [ ] **Step 2: Implement probe behavior**

Probe shop identity plus low-cost first page/permission checks. Capability report includes each resource stage, missing scope/official-contract reason, actual earliest date and page/window limits. A permission-limited optional resource does not disable orders/products.

- [ ] **Step 3: Run and commit**

Run: `python -m unittest tests.test_doudian_connector tests.test_integration_management_api -v`

Commit: `git add integrations/connectors/doudian.py tests/test_doudian_connector.py && git commit -m "feat: probe Doudian store capabilities"`

---

### Task 4: Normalize Products, SKUs, Inventory, Orders And Aftersales

**Files:**
- Modify: `integrations/connectors/doudian.py`
- Create: `tests/fixtures/integrations/doudian/order_search_list/normalized.golden.json`
- Test: `tests/test_doudian_normalization.py`

- [ ] **Step 1: Write golden mapping and pagination tests**

Cover two pages for product list, detail-derived SKU/inventory, order list/detail, order items, aftersale list/detail. Include numeric IDs larger than JavaScript safe integer and assert they remain strings. Include fake receiver PII and prove it is absent from normalized records, archive-input records and error objects.

- [ ] **Step 2: Run and verify red**

Run: `python -m unittest tests.test_doudian_normalization -v`

Expected: fetch/mapping absent.

- [ ] **Step 3: Implement product and SKU fetches**

`product_list_v2` uses verified update window, page starting at 1 and size 100. Each product list record yields a product; detail fetch yields explicit SKU records and an inventory snapshot whose `captured_at` is the runner's fixed logical snapshot time. Bound detail fan-out with the runner's resource concurrency and rate hints.

- [ ] **Step 4: Implement order and aftersale fetches**

Order/aftersale pages start at 0 and use ascending update time so watermark progression is stable. Fetch detail only when list payload lacks approved safe business fields. Map parent order/item/refund IDs and Decimal amounts explicitly. HMAC buyer external ID before leaving connector; delete all prohibited receiver fields before building `NormalizedRecord`.

- [ ] **Step 5: Run tests and commit**

Run: `python -m unittest tests.test_doudian_normalization tests.test_doudian_connector tests.test_integration_runner tests.test_integration_redaction -v`

Commit: `git add integrations/connectors/doudian.py tests/fixtures/integrations/doudian tests/test_doudian_normalization.py && git commit -m "feat: sync Doudian commerce data"`

---

### Task 5: Verify, Deduplicate And Queue Doudian Events

**Files:**
- Modify: `integrations/connectors/doudian.py`
- Modify: `routers/integrations.py`
- Modify: `integrations/sync/runner.py`
- Test: `tests/test_doudian_events.py`
- Test: `tests/test_integration_public_boundary.py`

- [ ] **Step 1: Write failing signature, replay and latency tests**

Official golden fixtures cover valid signature, changed body/header, stale timestamp, unknown event, global/subject-scoped duplicate `msg_id`, two enabled shops, unknown subject, forced ambiguous-subject corruption, out-of-order update, fake PII and handler failure. Assert invalid events never enter DB/queue; duplicate valid events ack successfully but enqueue once; each valid known subject routes to exactly its own connection; callback does no platform fetch or business upsert.

- [ ] **Step 2: Run and verify red**

Run: `python -m unittest tests.test_doudian_events tests.test_integration_public_boundary -v`

Expected: provider event handler unregistered/503.

- [ ] **Step 3: Implement exact official verification and safe event value**

`verify_event(headers, body)` follows the verified catalog algorithm and constant-time compares signatures. Parse with bounded body size, require external `msg_id` and the cataloged safe shop/authorization subject ID, map only allowlisted event type/entity ID/update time, redact before storage, and return the shared `VerifiedEvent` with the cataloged `EventIdScope`. Unknown signed event types may be acknowledged and safely recorded as unsupported, but never interpreted generically.

- [ ] **Step 4: Add public event route dispatch**

`GET|POST /integrations/events/doudian` is available only on callback host fence. After verification, resolve the subject transactionally to exactly one enabled Doudian connection using the cataloged subject semantics. Zero matches inserts an `unroutable_subject` inbox row with nullable connection, raises an operator alert, returns the official success ack to avoid a retry storm, and enqueues nothing. More than one match is an invariant breach: roll back, audit `ambiguous_event_subject`, return the official retryable failure response and enqueue nothing. A unique match inserts `CommerceEventInbox` using the shared scope-aware dedupe key, enqueues one `process_event` job containing only inbox/connection IDs, commits, then returns the exact ack. Use a short DB timeout and no outbound request.

- [ ] **Step 5: Process events as sync hints**

Worker maps supported events to a narrow order/refund/product sync checkpoint around the event watermark. Upsert timestamp rules prevent older events from overwriting poll results. The normal overlapping poll schedule remains unchanged.

- [ ] **Step 6: Run tests and commit**

Run: `python -m unittest tests.test_doudian_events tests.test_doudian_normalization tests.test_integration_public_boundary tests.test_integration_runner -v`

Commit: `git add integrations/connectors/doudian.py routers/integrations.py integrations/sync/runner.py tests/test_doudian_events.py tests/test_integration_public_boundary.py && git commit -m "feat: ingest verified Doudian events"`

---

### Task 6: Add Only Approved Logistics, Settlement And Business Metrics

**Files:**
- Modify: `integrations/provider_contracts/doudian.json`
- Modify: `integrations/connectors/doudian.py`
- Modify: `docs/integrations/provider-contracts/doudian.md`
- Test: `tests/test_doudian_optional_resources.py`

- [ ] **Step 1: Confirm optional operations in the approved console**

Record exact methods, safe field lists, time windows, async download behavior, result format and scopes. `/order/downloadToShop` must not be implemented from an incomplete public excerpt.

- [ ] **Step 2: Write fixtures and failing mappings**

For each actually approved resource, add official-format sanitized fixture and golden normalized shipment/settlement/daily metric. Prove downloads stay on official hosts, have bounded size, and contain no receiver PII after parsing.

- [ ] **Step 3: Implement capability-gated fetches**

Add one explicit mapper per verified operation. If the app lacks scope, probe reports limitation and scheduler omits it. Do not make optional failure block core order/product sync.

- [ ] **Step 4: Run and commit**

Run: `python -m unittest tests.test_doudian_optional_resources tests.test_doudian_connector tests.test_doudian_normalization -v`

Commit: `git add integrations/provider_contracts/doudian.json integrations/connectors/doudian.py docs/integrations/provider-contracts/doudian.md tests/fixtures/integrations/doudian tests/test_doudian_optional_resources.py && git commit -m "feat: sync approved Doudian optional resources"`

If no optional scope is approved, commit only the evidence/status showing `permission_limited`; do not add dead methods.

---

### Task 7: Complete Doudian Live Acceptance

**Files:**
- Create: `docs/runbooks/doudian-live-acceptance.md`
- Update: `docs/integrations/provider-contracts/doudian.md`

- [ ] **Step 1: Run complete offline connector tests**

Run:

```powershell
python -m unittest tests.test_doudian_operation_catalog tests.test_doudian_connector tests.test_doudian_normalization tests.test_doudian_events tests.test_doudian_optional_resources -v
```

- [ ] **Step 2: Complete real OAuth and refresh**

Authorize at least one法采抖店, verify shop ID/name/scope/expiry, force one locked refresh and confirm no credential disclosure.

- [ ] **Step 3: Backfill and resume**

Backfill from capability earliest date (public order API may limit history), kill worker between pages, confirm cursor resumes, then run one scheduled and one manual sync.

- [ ] **Step 4: Verify event plus polling reconciliation**

Trigger one safe test event if the platform console supports it, confirm ack/inbox/job/idempotency, then confirm the next poll yields the same final business state.

- [ ] **Step 5: Reconcile platform export**

Randomly sample 20 orders in one window. Order ID, normalized/raw status and amounts must match to the cent; compare aggregate count/paid/refund totals. Record only safe IDs and amounts.

- [ ] **Step 6: Mark live and commit evidence**

Only after OAuth, refresh, backfill, incremental and reconciliation pass can the connection be `active` and capability stage `reconciled`.

Commit: `git add docs/runbooks/doudian-live-acceptance.md docs/integrations/provider-contracts/doudian.md && git commit -m "docs: verify Doudian live integration"`
