# Qianchuan Connector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用法采已获批的巨量千川应用完成真实 OAuth、多广告账户发现、能力探测、投放数据回溯/增量同步，并让现有千川 Excel 素材绑定和高成交逻辑兼容消费 API 日报。

**Architecture:** `QianchuanConnector` 只调用在第一方文档或已批准应用控制台中核实的操作；`Access-Token`、OAuth 和分页由 connector 处理，统一 runner/worker 负责持久化。API 素材写入规范广告实体/日报表，兼容服务将旧 Excel 行与新 API 行投影为同一表现视图，不把 API 数据塞入旧 Float 表。

**Tech Stack:** Ocean Engine/Qianchuan official API、httpx、FastAPI OAuth callback、SQLAlchemy/PostgreSQL、existing Qianchuan Excel parser/binding routes、`unittest` MockTransport。

## Global Constraints

- 本计划依赖 foundation 与 sync-core 完成。
- 公开页面目前只确认 `GET /open_api/v1.0/qianchuan/advertiser/type/get/` 和 `GET /open_api/v3.0/report/custom/get/`；OAuth、账户、余额/流水、计划、创意、素材、商品/直播报表的精确操作必须先从当前应用控制台核实。
- 未进入 `integrations/provider_contracts/qianchuan.json` 且状态为 `approved_app_verified` 的操作不得写进 connector 常量。
- 千川与抖店使用不同授权和 Token 生命周期；不能复用抖店 Token 或假设相同 expiry。
- 保留 `/api/templates/qianchuan/import` 与所有 Excel/重匹配能力。
- 真实 Token、控制台截图中的 Secret、账户敏感信息不得进入 git；证据文件只保存脱敏字段和 SHA-256。

---

### Task 1: Complete The Approved-App Qianchuan Operation Catalog

**Files:**
- Modify: `integrations/provider_contracts/qianchuan.json`
- Modify: `docs/integrations/provider-contracts/qianchuan.md`
- Create: `tests/fixtures/integrations/qianchuan/advertiser_type/source.json`
- Test: `tests/test_qianchuan_operation_catalog.py`

- [ ] **Step 1: Write the catalog completeness test**

Require these internal operation keys before live connector status can become configured:

```text
oauth_authorize
oauth_exchange
oauth_refresh
authorization_subject
advertiser_discovery
advertiser_type
ad_account_info
ad_balance
ad_finance_transactions
ad_entities_campaign
ad_entities_creative
ad_entities_material
ad_report_daily
ad_report_material_daily
ad_report_live_daily
ad_report_product_daily
```

The test allows missing operations only while catalog status is `verification_required`; in that state capability probe must report each missing operation and the connector cannot be `active`.

- [ ] **Step 2: Record the two publicly verified operations**

Catalog these exact first-party operations:

- `GET https://api.oceanengine.com/open_api/v1.0/qianchuan/advertiser/type/get/`, request includes `advertiser_ids`, external key `advertiser_id`; official visual debugger: <https://open.oceanengine.com/tools/visual_debug.html?docId=1754620816918532>.
- `GET https://api.oceanengine.com/open_api/v3.0/report/custom/get/`, request includes `advertiser_id`, dimensions, metrics, filters, start/end and ordering; official visual debugger: <https://open.oceanengine.com/tools/visual_debug.html?docId=1741387668314126>.

Do not fill pagination fields/metric names until verified in the approved application.

- [ ] **Step 3: Capture the remaining operations from the approved application console**

For each key, use the official visual debugger/control panel to record HTTP method, exact path, `Access-Token` placement, request parameter names/types, pagination request/response fields, maximum page/window, response list path, external ID, request ID/error shape, scope and QPS. Save sanitized official sample request/page/error fixtures and their source SHA-256.

Acceptance: another engineer can replay each sanitized fixture contract without platform credentials, and the catalog status is `approved_app_verified` only after all operations required by the actual approved scopes are recorded.

- [ ] **Step 4: Run the evidence tests and commit**

Run: `python -m unittest tests.test_provider_contract_evidence tests.test_qianchuan_operation_catalog -v`

Commit: `git add integrations/provider_contracts/qianchuan.json docs/integrations/provider-contracts/qianchuan.md tests/fixtures/integrations/qianchuan tests/test_qianchuan_operation_catalog.py && git commit -m "docs: verify Qianchuan application operations"`

Stop here if the approved application console is unavailable. That is an external credential/permission gate, not authorization to invent method names.

---

### Task 2: Implement Qianchuan OAuth, Token Refresh And Request Translation

**Files:**
- Create: `integrations/connectors/qianchuan.py`
- Modify: `integrations/connectors/registry.py`
- Create: `tests/fixtures/integrations/qianchuan/oauth_exchange/page-1.json`
- Create: `tests/fixtures/integrations/qianchuan/oauth_refresh/page-1.json`
- Test: `tests/test_qianchuan_connector.py`

- [ ] **Step 1: Write failing OAuth/signature/header tests**

Using `httpx.MockTransport`, assert authorization URL query fields exactly match catalog, exchange/refresh use exact official methods, redirects use the configured callback, API requests send `Access-Token` only to official hosts, and the token never appears in URL/log/repr/error. Platform response expiry always wins over local defaults.

Test typed translation of success, platform auth error, permission error, rate limit, 5xx, malformed JSON, missing request ID and a two-page cursor.

- [ ] **Step 2: Run and verify red**

Run: `python -m unittest tests.test_qianchuan_connector -v`

Expected: connector absent.

- [ ] **Step 3: Implement catalog-backed constants and OAuth**

Hard-code only committed verified hosts/paths in `qianchuan.py`; load the catalog in tests to prove they agree, not at runtime to accept arbitrary operator edits. Build authorization URLs with `urllib.parse.urlencode`. Exchange/refresh map the exact official response into `TokenBundle` with aware UTC expiries and `repr=False` tokens.

- [ ] **Step 4: Implement a bounded API request helper**

Use `OfficialApiClient` with only catalog official hosts. Inject `Access-Token`, JSON/query fields and request ID parsing. Translate platform numeric/string error codes into the shared typed exceptions; sanitized errors include operation key, platform code and request ID only.

- [ ] **Step 5: Register and test**

Register `Provider.QIANCHUAN` only when app config and catalog are present. Run:

`python -m unittest tests.test_qianchuan_connector tests.test_integration_connector_contract tests.test_integration_oauth -v`

Commit: `git add integrations/connectors/qianchuan.py integrations/connectors/registry.py tests/fixtures/integrations/qianchuan tests/test_qianchuan_connector.py && git commit -m "feat: add Qianchuan OAuth client"`

---

### Task 3: Discover Advertisers And Probe Actual Capabilities

**Files:**
- Modify: `integrations/connectors/qianchuan.py`
- Test: `tests/test_qianchuan_connector.py`

- [ ] **Step 1: Add failing account/capability tests**

Fixture cases: one authorization discovers multiple advertisers; duplicate advertiser returned twice; advertiser type/account info enrichment; partial scope; earliest report date; permission-denied operation; one account inaccessible while siblings remain usable.

Assert each `IntegrationConnection` references one authorization and no connection row contains tokens.

- [ ] **Step 2: Run and verify red**

Run: `python -m unittest tests.test_qianchuan_connector.QianchuanAccountDiscoveryTests -v`

Expected: discovery/capability assertions fail.

- [ ] **Step 3: Implement discovery and probe**

Map each advertiser to `AccountIdentity(connection_type="ad_account", external_id, display_name, metadata)` and dedupe by external ID. Capability probe calls only lightweight verified operations, distinguishes missing catalog, missing scope, permission response and live success, and records earliest allowed date/QPS without treating theoretical platform support as granted.

- [ ] **Step 4: Run tests and commit**

Run: `python -m unittest tests.test_qianchuan_connector tests.test_integration_oauth tests.test_integration_management_api -v`

Commit: `git add integrations/connectors/qianchuan.py tests/test_qianchuan_connector.py && git commit -m "feat: discover Qianchuan advertiser accounts"`

---

### Task 4: Normalize Qianchuan Entities, Finance And Daily Reports

**Files:**
- Modify: `integrations/connectors/qianchuan.py`
- Create: `tests/fixtures/integrations/qianchuan/ad_report_material_daily/normalized.golden.json`
- Test: `tests/test_qianchuan_normalization.py`

- [ ] **Step 1: Write one golden mapping test per verified resource**

Cover ad account, campaign/plan, creative, material, daily/material/live/product report, balance snapshot and finance transaction when those scopes exist. Assert IDs remain strings, RMB amounts use `Decimal`, ratios use six-decimal precision, stat dates use Asia/Shanghai calendar dates, platform update timestamps are aware UTC, and every raw PII/credential key is absent.

- [ ] **Step 2: Run and verify red**

Run: `python -m unittest tests.test_qianchuan_normalization -v`

Expected: resource mapping/fetch pagination missing.

- [ ] **Step 3: Implement explicit operation-to-resource mappings**

Do not build a generic “copy response JSON” mapper. For each catalog operation, explicitly construct `NormalizedRecord` payload keys accepted by the strict schemas. Material daily rows use `entity_type="material"`, a string `external_entity_id` such as `7618149103516336169`, `stat_date`, and `granularity="day"`; balance and finance use their dedicated tables.

- [ ] **Step 4: Implement catalog pagination and windows**

Serialize cursor as compact JSON containing only verified page/cursor fields. Respect catalog maximum range and have scheduler split larger requests. Populate `request_id`, `rate_limit_hint` and watermark from verified response fields.

- [ ] **Step 5: Run tests and commit**

Run: `python -m unittest tests.test_qianchuan_normalization tests.test_qianchuan_connector tests.test_integration_runner -v`

Commit: `git add integrations/connectors/qianchuan.py tests/fixtures/integrations/qianchuan tests/test_qianchuan_normalization.py && git commit -m "feat: sync Qianchuan advertising data"`

---

### Task 5: Unify API And Excel Material Performance Without Breaking Bindings

**Files:**
- Create: `services/qianchuan_performance.py`
- Modify: `models.py`
- Modify: `database.py`
- Modify: `integrations/migration.py`
- Modify: `routers/templates.py`
- Create: `alembic/versions/20260713_0003_qianchuan_binding_keys.py`
- Test: `tests/test_qianchuan_api_compat.py`
- Test: `tests/test_qianchuan_performance.py`
- Test: `tests/test_sqlite_to_postgres_migration.py`

- [ ] **Step 1: Write failing compatibility and collision tests**

Prove:

- old Excel-only payloads, imports, auto-match, workbook rematch and high-conversion updates are unchanged;
- API material daily rows project to the same metric names as `QianchuanParsedRow`;
- Excel `material_id="123"` and API material `123` under two connections remain three distinct keys;
- legacy bind requests with only `material_id` work when the Excel candidate is unique and return 409 when ambiguous;
- API bind requests require/return `material_key` and do not silently rebind existing scripts;
- summaries dedupe by source/key/stat date/granularity and never add Excel/API duplicates blindly;
- current high-conversion threshold behavior is preserved exactly.

- [ ] **Step 2: Run and verify red**

Run: `python -m unittest tests.test_qianchuan_api_compat tests.test_qianchuan_performance -v`

Expected: API rows unavailable and binding key collision tests fail.

- [ ] **Step 3: Migrate binding identity safely**

Add non-null `material_key` to `QianchuanScriptBinding`. Against a disposable database already at revision 0002, run:

```powershell
if (-not $env:FACAI_TEST_DATABASE_URL) { throw 'FACAI_TEST_DATABASE_URL must reference the disposable PostgreSQL test database' }
python scripts/assert_disposable_postgres.py --env FACAI_TEST_DATABASE_URL --ack-env FACAI_DESTRUCTIVE_TEST_DATABASE_ACK
$env:FACAI_MIGRATION_DATABASE_URL = $env:FACAI_TEST_DATABASE_URL
alembic revision --autogenerate --rev-id 20260713_0003 -m "qianchuan binding keys"
```

Before generation, assert the disposable target reports revision 0002. Never let this task fall back to `DATABASE_URL`; the command must read the explicitly assigned `FACAI_MIGRATION_DATABASE_URL`. Set `revision = "20260713_0003"` and `down_revision = "20260713_0002"` explicitly, then review the generated operations. PostgreSQL revision 0003 adds the column nullable, backfills `excel:` + `material_id`, makes it non-null, replaces `(script_id, material_id)` uniqueness with `(script_id, material_key)`, and indexes source key. Its downgrade restores the old unique constraint only after asserting no row set would collide when reduced to `material_id`; otherwise it fails with an operator-facing error instead of losing distinctions. Add the equivalent SQLite compatibility column/backfill/index repair for rollback mode.

Key format is fixed:

```text
excel:{material_id}
api:{connection_id}:{external_material_id}
```

Keep `material_id` and `material_name` for display/backward response compatibility.

Register the sole historical copier adapter for `qianchuan_script_bindings.material_key`: when the frozen SQLite source lacks the column, require a non-empty `material_id` and synthesize exactly `excel:{material_id}`. A fixture built with the pre-0003 binding schema must migrate at Alembic head, report the synthesized count, preserve all binding IDs/relationships, and leave the source hash/bytes unchanged. If a source already contains `material_key`, copy and validate it without synthesis; any other missing legacy column still fails closed.

- [ ] **Step 4: Extract a unified read/projection service**

Move material-to-dict, summary, binding lookup and high-conversion calculation seams out of `routers/templates.py` into `services/qianchuan_performance.py`. Define a `QianchuanPerformanceView` dataclass with source, material key/ID/name, connection, stat date, amount field, Decimal money and common metrics. Legacy rows and normalized API rows each have explicit projectors.

- [ ] **Step 5: Update endpoints compatibly**

Existing response keys remain; add `source`, `material_key`, `connection_id`, and `stat_date`. Bind endpoint accepts optional `material_key`; material-ID-only lookup is allowed only for one unambiguous legacy candidate. Manual/fuzzy match remains review-first, and API sync never triggers forced bulk rebinding.

- [ ] **Step 6: Run regressions and migration round-trip tests**

Run:

```powershell
python -m unittest tests.test_qianchuan_api_compat tests.test_qianchuan_performance tests.test_template_workbook_import -v
if (-not $env:FACAI_TEST_DATABASE_URL) { throw 'FACAI_TEST_DATABASE_URL is required' }
python scripts/assert_disposable_postgres.py --env FACAI_TEST_DATABASE_URL --ack-env FACAI_DESTRUCTIVE_TEST_DATABASE_ACK
$env:FACAI_MIGRATION_DATABASE_URL = $env:FACAI_TEST_DATABASE_URL
python -m unittest tests.test_alembic_postgres -v
alembic downgrade 20260713_0002
alembic upgrade head
```

Seed a collision-free legacy binding set before downgrade and prove 0003→0002→0003 preserves IDs and backfilled keys. In a separate transaction seed two API distinctions that would collapse to one old key and prove downgrade aborts without changing the revision. Expected: all old tests plus new multi-account cases pass, `down_revision` is exactly 0002, the safe round trip passes and the lossy downgrade fails closed.

- [ ] **Step 7: Commit compatibility work**

Commit: `git add services/qianchuan_performance.py models.py database.py integrations/migration.py routers/templates.py alembic/versions/20260713_0003_qianchuan_binding_keys.py tests/test_qianchuan_api_compat.py tests/test_qianchuan_performance.py tests/test_sqlite_to_postgres_migration.py && git commit -m "feat: unify Qianchuan API and Excel performance"`

---

### Task 6: Complete Qianchuan Live Acceptance

**Files:**
- Update: `docs/integrations/provider-contracts/qianchuan.md`
- Create: `docs/runbooks/qianchuan-live-acceptance.md`

- [ ] **Step 1: Pass offline tests with no network**

Run:

```powershell
python -m unittest tests.test_qianchuan_operation_catalog tests.test_qianchuan_connector tests.test_qianchuan_normalization tests.test_qianchuan_api_compat tests.test_qianchuan_performance -v
```

- [ ] **Step 2: Perform real OAuth and refresh with one法采 authorization**

Use the configured HTTPS callback. Verify all discovered advertisers, scopes, token expiry and one locked refresh. Confirm logs/API/DB safe views never expose credentials.

- [ ] **Step 3: Run historical and incremental sync**

Backfill from capability-reported earliest date, terminate/restart worker during a multi-page window, confirm cursor resume, then run one scheduled and one manual date-range sync.

- [ ] **Step 4: Reconcile with an official platform export**

For the same completed attribution window, randomly sample 20 entity/date rows. Entity IDs must match; spend/transaction amounts must differ by no more than `max(0.01 CNY, 0.1%)`. Record counts, chosen IDs, aggregate deltas and timestamps without Token/PII.

- [ ] **Step 5: Verify existing script behavior**

Use one Excel-bound and one API-bound material. Confirm page payload, summary, explicit binding, high-conversion flag and no forced rebind are consistent.

- [ ] **Step 6: Mark live stage and commit evidence**

Only after OAuth, refresh, backfill, incremental and reconciliation pass, set capability verification stage through `reconciled` and allow connection `active`.

Commit: `git add docs/integrations/provider-contracts/qianchuan.md docs/runbooks/qianchuan-live-acceptance.md && git commit -m "docs: verify Qianchuan live integration"`
