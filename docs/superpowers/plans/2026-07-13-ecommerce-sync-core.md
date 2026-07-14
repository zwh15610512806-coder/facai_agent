# Ecommerce Sync Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 提供四个平台共享的规范数据模型、connector 协议、PostgreSQL 持久任务队列、幂等写入、加密归档、调度和独立 worker，使 API 请求不执行长时间同步且崩溃后可续跑。

**Architecture:** 平台适配器只完成官方请求、分页、错误翻译、PII 删除和规范记录转换；统一 runner 负责租约、重试、Token 刷新、归档、事务 upsert 与 cursor。任务和 worker 心跳持久化到 PostgreSQL，使用 `FOR UPDATE SKIP LOCKED` 领取，不引入 Redis/Celery。

**Tech Stack:** Python 3.12、SQLAlchemy 2.0、PostgreSQL、Alembic、httpx、AES-GCM/gzip、FastAPI 管理 API、`unittest`。

## Global Constraints

- 本计划依赖 `2026-07-13-ecommerce-api-foundation.md` 全部完成，并且 `FACAI_TEST_DATABASE_URL` 指向可清空 PostgreSQL 测试库。
- 集成 worker 必须是独立 OS 进程；不得在 FastAPI lifespan、请求线程或现有 vector worker 线程中运行。
- 同一 `connection_id + resource_type` 同时只能有一个活跃租约；Token 刷新以 `authorization_id` 串行。
- 每页只有在加密归档成功、业务 upsert 成功且同一 DB 事务提交后才能推进 cursor。
- connector 输出进入 writer 前必须通过 `assert_payload_safe()`；平台原始 PII 不得写隔离错误或日志。
- 淘宝 TMC 和拼多多 WebSocket 不进入 v1；抖店事件和可选千川 SPI 只做验签、幂等入队与快速响应，轮询仍做最终对账。
- 所有 PostgreSQL 并发测试不得 skip；没有测试库时本计划处于外部环境阻塞，不能宣称完成。

---

### Task 1: Define A Machine-Checked Provider Contract Evidence Format

**Files:**
- Create: `integrations/provider_contracts/schema.json`
- Create: `integrations/provider_contracts/qianchuan.json`
- Create: `integrations/provider_contracts/doudian.json`
- Create: `integrations/provider_contracts/taobao.json`
- Create: `integrations/provider_contracts/pdd.json`
- Create: `docs/integrations/provider-contracts/qianchuan.md`
- Create: `docs/integrations/provider-contracts/doudian.md`
- Create: `docs/integrations/provider-contracts/taobao.md`
- Create: `docs/integrations/provider-contracts/pdd.md`
- Test: `tests/test_provider_contract_evidence.py`

- [ ] **Step 1: Write failing schema and provenance tests**

Tests validate each JSON document against `schema.json`, reject secrets/tokens, and require every operation to contain:

```json
{
  "key": "stable_internal_operation_key",
  "official_url": "https://official.example/path",
  "http_method": "GET",
  "gateway_or_path": "/official/path-or-method-name",
  "required_scopes": [],
  "window_limit": "human-readable official limit",
  "pagination": {"request": [], "response": []},
  "external_ids": [],
  "rate_limit": "documented value or control_panel_only",
  "verified_at": "YYYY-MM-DD",
  "verification_source": "public_official_doc or approved_app_console"
}
```

Provider documents also carry `provider`, `status`, `official_hosts`, `application_type`, and `operations`. Valid status values are `verification_required`, `public_docs_verified`, and `approved_app_verified`.

- [ ] **Step 2: Run and verify red**

Run: `python -m unittest tests.test_provider_contract_evidence -v`

Expected: missing evidence files.

- [ ] **Step 3: Add only currently verified evidence**

Populate public first-party operations already verified in the approved specification and provider plans. For unverified Qianchuan/PDD resources, set document status to `verification_required` and omit the operation—do not use blank method names or guessed values. Human Markdown records the exact control-panel capture procedure, reviewer, capture date, and sanitized artifact SHA-256.

- [ ] **Step 4: Implement the capability rule**

Add a test helper that maps an absent operation to capability reason `official_contract_not_verified`. This reason must prevent the affected resource from being scheduled and prevent the provider from reporting `active`.

- [ ] **Step 5: Run tests and commit**

Run: `python -m unittest tests.test_provider_contract_evidence -v`

Commit: `git add integrations/provider_contracts docs/integrations/provider-contracts tests/test_provider_contract_evidence.py && git commit -m "docs: add verified provider operation contracts"`

---

### Task 2: Add Sync, Queue And Normalized Commerce Models

**Files:**
- Modify: `integration_models.py`
- Modify: `commerce_models.py`
- Create: `alembic/versions/20260713_0002_sync_and_commerce.py`
- Test: `tests/test_integration_commerce_models.py`
- Test: `tests/test_integration_sync_models.py`
- Test: `tests/test_alembic_postgres.py`

- [ ] **Step 1: Write failing model and uniqueness tests**

On PostgreSQL, assert named uniqueness and FK behavior for every table below. Required idempotency keys:

| Table | Unique key |
|---|---|
| `integration_jobs` | `dedupe_key` |
| `integration_worker_heartbeats` | `worker_id` |
| `integration_sync_checkpoints` | `(connection_id, resource_type, window_start, window_end)` |
| `integration_export_jobs` | `public_id` |
| `commerce_shops` | `(connection_id, external_shop_id)` |
| `commerce_products` | `(connection_id, external_product_id)` |
| `commerce_skus` | `(connection_id, external_sku_id)` |
| `commerce_inventory_snapshots` | `(connection_id, external_sku_id, captured_at)` |
| `commerce_product_links` | `commerce_product_id` (many platform products may link to the same existing `product_id`) |
| `commerce_orders` | `(connection_id, external_order_id)` |
| `commerce_order_items` | `(connection_id, external_item_id)` |
| `commerce_refunds` | `(connection_id, external_refund_id)` |
| `commerce_shipments` | `(connection_id, external_shipment_id)` |
| `commerce_settlements` | `(connection_id, external_settlement_id)` |
| `commerce_daily_metrics` | `(connection_id, stat_date, granularity)` |
| `commerce_ad_accounts` | `(connection_id, external_ad_account_id)` |
| `commerce_ad_entities` | `(connection_id, entity_type, external_entity_id)` |
| `commerce_ad_daily_metrics` | `(connection_id, entity_type, external_entity_id, stat_date, granularity)` |
| `commerce_ad_balance_snapshots` | `(connection_id, external_ad_account_id, captured_at)` |
| `commerce_ad_finance_transactions` | `(connection_id, external_transaction_id)` |
| `commerce_event_inbox` | unique `dedupe_key`; retains provider, external subject/event IDs and declared ID scope for audit |

Also enumerate every persisted sync/commerce enum column—provider, resource, job type/status, checkpoint/run/source/status, export status, event ID/routing status and all normalized business statuses—and assert the exact named CHECK constraint exists. Representative raw invalid INSERT/UPDATE statements for each enum family must fail on PostgreSQL; ORM/Pydantic rejection alone is insufficient.

- [ ] **Step 2: Run and verify red**

Run: `if (-not $env:FACAI_TEST_DATABASE_URL) { throw 'FACAI_TEST_DATABASE_URL is required' }; python -m unittest tests.test_integration_commerce_models tests.test_integration_sync_models -v`

Expected: missing models/tables.

- [ ] **Step 3: Add sync-control models**

Extend `integration_models.py` with:

- `IntegrationJob`: job type, unique SHA-256 dedupe key, sanitized JSON payload, priority, status, available time, attempts/max attempts, lease owner/expiry, heartbeat, last error code/summary, created/updated/completed times.
- `IntegrationWorkerHeartbeat`: worker ID, PID, started/last-seen timestamps, active job count and version.
- `IntegrationSyncCheckpoint`: connection/resource plus non-null aware UTC `window_start/window_end`, JSON cursor, watermark, status, attempts, next retry and resource lease. Snapshot resources use the logical scheduled-slot window even when the connector receives `window=None`, preserving the approved unique key without nullable duplicates.
- `IntegrationSyncRun`: checkpoint/parent IDs, source, status, resource/window, progress, read/written/skipped/quarantined counts, start/end and sanitized failure code/summary.
- `IntegrationSyncError`: run ID, external-key HMAC, error type, sanitized summary and retryable flag.
- `IntegrationArchiveManifest`: run/page/provider/connection/resource/window, relative path, SHA-256, record count, created/expires/deleted times.
- `IntegrationExportJob`: public-safe job UUID, requester session digest, resource, sanitized filters, format/status, relative file path, row count, error code/summary and created/started/completed/expires timestamps. The reporting phase uses this table but does not need another schema revision.
- `CommerceEventInbox`: provider, external event ID, external subject ID, `EventIdScope`, unique SHA-256 dedupe key, nullable resolved connection FK, allowlisted event/entity/update fields, sanitized payload, routing/processing status and timestamps. The dedupe key is canonical SHA-256 of provider + official cataloged scope + subject (only for subject-scoped IDs) + event ID; no connector invents the scope.

Use `JSON().with_variant(JSONB(), "postgresql")`. Reuse the foundation `persisted_enum(..., name="ck_<table>_<column>")` helper for every fixed enum value; do not create PostgreSQL-native enums or unconstrained strings. Job payload may contain only integer IDs, enums, ISO windows and cursor-safe metadata—never credentials or PII.

- [ ] **Step 4: Add normalized commerce models**

Every entity has integer PK, `connection_id`, `provider`, string external key, `platform_updated_at` as timezone-aware UTC and safe JSON `platform_metadata`. Store money as `Numeric(20, 2)`, ratios as `Numeric(20, 6)`, dates as `Date`, timestamps as `DateTime(timezone=True)`, and `currency` as three uppercase characters.

Order fields are limited to order number, shop, normalized/raw status, safe buyer HMAC, province/city, amount components and lifecycle timestamps. No model may declare name, phone, mobile, ID-card or detailed-address columns.

`commerce_product_links` references existing `products.id` and records linking administrator session digest plus timestamps. A platform product has at most one link; many platform products may link to the same existing Product. SKU rows inherit their parent product link. Delete of a Product or commerce product cascades only the link, never either product.

- [ ] **Step 5: Generate and review revision 0002**

Run:

```powershell
python scripts/assert_disposable_postgres.py --env FACAI_TEST_DATABASE_URL --ack-env FACAI_DESTRUCTIVE_TEST_DATABASE_ACK
$env:FACAI_MIGRATION_DATABASE_URL=$env:FACAI_TEST_DATABASE_URL
alembic upgrade 20260713_0001
alembic revision --autogenerate --rev-id 20260713_0002 -m "integration sync and commerce"
```

Assert `alembic current` is exactly 0001 before generation. Rename to the fixed path, set `down_revision = "20260713_0001"` explicitly, inspect explicit DDL, named constraints, NUMERIC precision and timezone columns, then test downgrade to `20260713_0001` and re-upgrade.

- [ ] **Step 6: Run tests and commit**

Run: `if (-not $env:FACAI_TEST_DATABASE_URL) { throw 'FACAI_TEST_DATABASE_URL is required' }; python -m unittest tests.test_integration_commerce_models tests.test_integration_sync_models tests.test_alembic_postgres -v`

Commit: `git add integration_models.py commerce_models.py alembic/versions/20260713_0002_sync_and_commerce.py tests/test_integration_commerce_models.py tests/test_integration_sync_models.py tests/test_alembic_postgres.py && git commit -m "feat: add normalized commerce and sync models"`

---

### Task 3: Complete The Connector Contract And Fixed-Host HTTP Client

**Files:**
- Modify: `integrations/types.py`
- Modify: `integrations/connectors/base.py`
- Modify: `integrations/connectors/registry.py`
- Create: `integrations/connectors/http.py`
- Test: `tests/test_integration_connector_contract.py`

- [ ] **Step 1: Write failing contract tests**

Use `unittest.IsolatedAsyncioTestCase` and `httpx.MockTransport` to assert:

- `TokenBundle` hides tokens from `repr`;
- `TimeWindow` rejects naive timestamps and requires exclusive `end > start`;
- `FetchPage` contains normalized records, cursor, request ID, rate hint and watermark;
- each registered connector implements every protocol method;
- HTTP client rejects non-HTTPS, user-supplied hosts, redirects to a different host and response bodies over the configured byte limit;
- safe request logging omits query/body/header secrets.

- [ ] **Step 2: Run and verify red**

Run: `python -m unittest tests.test_integration_connector_contract -v`

Expected: incomplete protocol/client.

- [ ] **Step 3: Finalize shared transport values**

`NormalizedRecord` is immutable and contains `resource`, `external_id`, `platform_updated_at`, strict normalized payload, and `sanitized_source_payload` marked `repr=False`. Each connector constructs the source payload from an operation-specific allowlist and drops unknown fields; the generic recursive denylist is a second defense. The writer ignores the source payload; archive serializes it after another safety assertion so the 90-day artifact preserves sanitized platform source data. `FetchPage.items` is a tuple of `NormalizedRecord`, not untyped raw dictionaries. `TokenBundle` marks access/refresh values `repr=False`.

- [ ] **Step 4: Implement a fixed-host client**

`OfficialApiClient` is constructed by code with a provider-specific `frozenset` of exact official hosts. It calls `httpx.AsyncClient(follow_redirects=False, timeout=httpx.Timeout(30.0, connect=10.0))`; a 3xx is an error unless the connector validates and explicitly follows a same-host location. Bound response bytes before JSON parsing and translate network/HTTP failures to typed errors: `RateLimited`, `AuthenticationFailed`, `PermissionDenied`, `TransientPlatformError`, `InvalidPlatformResponse`.

- [ ] **Step 5: Run tests and commit**

Run: `python -m unittest tests.test_integration_connector_contract tests.test_integration_redaction -v`

Commit: `git add integrations/types.py integrations/connectors tests/test_integration_connector_contract.py && git commit -m "feat: define secure ecommerce connector contract"`

---

### Task 4: Implement PostgreSQL Job And Resource Leases

**Files:**
- Create: `integrations/sync/__init__.py`
- Create: `integrations/sync/queue.py`
- Test: `tests/test_integration_queue.py`

- [ ] **Step 1: Write failing concurrent PostgreSQL tests**

Tests open two independent sessions and prove:

- enqueue with the same logical key returns one job;
- two workers using `FOR UPDATE SKIP LOCKED` cannot claim the same job;
- an expired lease is reclaimable and a live lease is not;
- heartbeat extends only the current owner's lease;
- same connection/resource checkpoint lease serializes work;
- token refresh jobs dedupe by authorization ID, not connection ID;
- completing/failing a job clears lease fields and preserves sanitized status.

- [ ] **Step 2: Run and verify red**

Run: `if (-not $env:FACAI_TEST_DATABASE_URL) { throw 'FACAI_TEST_DATABASE_URL is required' }; python -m unittest tests.test_integration_queue -v`

Expected: missing queue implementation.

- [ ] **Step 3: Implement stable dedupe keys and enqueue**

Canonicalize logical input with sorted compact JSON and compute:

```python
dedupe_key = sha256(
    f"{job_type}\n{target_id}\n{canonical_logical_request}".encode("utf-8")
).hexdigest()
```

Use PostgreSQL insert-on-conflict for `dedupe_key`; the conflict update may only pull `available_at` earlier for an existing queued/retry job and must never resurrect completed jobs. A new manual request must include its distinct logical request ID.

- [ ] **Step 4: Implement atomic claim and resource lease**

Claim candidates ordered by `priority DESC, available_at ASC, id ASC` using SQLAlchemy `select(IntegrationJob).with_for_update(skip_locked=True).limit(1)`, then update lease fields in the same transaction. Before running a sync job, atomically acquire its checkpoint lease. A job that cannot obtain the resource lease returns to queued with short jitter without consuming a retry attempt.

- [ ] **Step 5: Run tests and commit**

Run: `if (-not $env:FACAI_TEST_DATABASE_URL) { throw 'FACAI_TEST_DATABASE_URL is required' }; python -m unittest tests.test_integration_queue -v`

Commit: `git add integrations/sync tests/test_integration_queue.py && git commit -m "feat: add persistent integration job leases"`

---

### Task 5: Upsert Normalized Records Without Letting Old Pages Win

**Files:**
- Create: `integrations/sync/writer.py`
- Modify: `integrations/schemas.py`
- Test: `tests/test_integration_writer.py`

- [ ] **Step 1: Write failing idempotency and PII tests**

For every `ResourceType`, write one valid golden record and test:

- inserting the same page twice leaves one business row;
- a record with newer `platform_updated_at` updates mutable fields;
- an older record cannot overwrite the newer row;
- an equal-timestamp identical payload is an idempotent no-op; an equal-timestamp divergent payload never overwrites and creates one sanitized `equal_timestamp_conflict` quarantine/refetch signal;
- a newer sparse payload cannot replace an existing non-null optional detail field with `None`;
- separate connections with the same external ID remain isolated;
- unknown raw status maps to normalized `unknown` while preserving the raw string;
- mixed non-CNY currency is stored but rejected from CNY aggregation;
- a row containing any PII/secret sentinel is quarantined before SQL and the sentinel is absent from DB/log/error summary;
- one invalid record makes the page `partial_success` while valid siblings commit.

- [ ] **Step 2: Run and verify red**

Run: `if (-not $env:FACAI_TEST_DATABASE_URL) { throw 'FACAI_TEST_DATABASE_URL is required' }; python -m unittest tests.test_integration_writer -v`

Expected: writer absent.

- [ ] **Step 3: Define strict normalized payload schemas**

In `integrations/schemas.py`, define one `extra="forbid"` Pydantic model per resource. IDs are strings even if the platform sends numbers. Money enters through `Decimal(str(value))`, timestamps must be aware, and status normalization is performed by each connector before validation.

The order schema intentionally exposes only:

```python
class NormalizedOrder(BaseModel):
    model_config = ConfigDict(extra="forbid")
    external_order_id: str
    external_shop_id: str | None
    normalized_status: OrderStatus
    raw_status: str
    buyer_digest: str | None
    province: str | None
    city: str | None
    currency: str = "CNY"
    order_amount: Decimal
    paid_amount: Decimal
    discount_amount: Decimal
    shipping_amount: Decimal
    created_at: datetime | None
    paid_at: datetime | None
    shipped_at: datetime | None
    completed_at: datetime | None
```

`platform_updated_at` belongs to the containing `NormalizedRecord` envelope and must not be duplicated in any payload schema. Every other resource schema matches the program-level field matrix and uses the same `normalized_status` naming.

- [ ] **Step 4: Implement a table-spec registry and conditional PostgreSQL upsert**

Map each resource to its table, conflict columns and allowed update columns. Use `sqlalchemy.dialects.postgresql.insert`. The conflict update includes:

```python
where=excluded.platform_updated_at > table.c.platform_updated_at
```

Build optional-column updates as `COALESCE(excluded.column, table.column)` so sparse list responses cannot erase detail-enriched values; fields whose official semantics permit explicit clearing need a separate cataloged clear flag and test, never an overloaded `None`.

When the upsert does not update, read the existing allowlisted columns in the same transaction. Older input is a counted skip. Equal timestamps compare canonical normalized hashes: identical is an idempotent skip; divergent input leaves the row unchanged, writes a sanitized `equal_timestamp_conflict` sync error, and enqueues one deduped authoritative-detail refetch when that operation exists (otherwise the run is `partial_success` for operator review). Do not choose by arrival order or hash ordering.

Use `DO NOTHING` only for immutable `commerce_event_inbox` event IDs. Finance transactions use this same conditional upsert so a later `platform_updated_at` may correct status or amount; an older/equal-conflicting provider record cannot silently overwrite the stored row. Never pass the normalized payload wholesale to SQL; build an explicit allowlisted values dictionary.

- [ ] **Step 5: Quarantine safe validation failures**

Catch Pydantic/type errors per record, HMAC the external key, and store only error type plus stable field-path/error-code pairs in `IntegrationSyncError`. Do not store rejected values or raw Pydantic input. Increment run counters in the same transaction as business rows.

- [ ] **Step 6: Run tests and commit**

Run: `if (-not $env:FACAI_TEST_DATABASE_URL) { throw 'FACAI_TEST_DATABASE_URL is required' }; python -m unittest tests.test_integration_writer tests.test_integration_commerce_models -v`

Commit: `git add integrations/sync/writer.py integrations/schemas.py tests/test_integration_writer.py && git commit -m "feat: upsert normalized commerce records safely"`

---

### Task 6: Encrypt And Retain Sanitized Page Archives

**Files:**
- Create: `integrations/sync/archive.py`
- Modify: `integrations/crypto.py`
- Test: `tests/test_integration_archive.py`

- [ ] **Step 1: Write failing archive tests**

Cover deterministic logical content, random encryption, tamper failure, path containment, atomic visibility, manifest hash/count, exception cleanup, orphan scavenging and 90-day retention. Assert the decrypted JSONL contains safe normalized platform payload but none of the PII/secret sentinels.

- [ ] **Step 2: Run and verify red**

Run: `python -m unittest tests.test_integration_archive -v`

Expected: archive module absent.

- [ ] **Step 3: Derive an archive-specific encryption key**

Extend `integrations/crypto.py` with HKDF info `facai-integrations/archive-page/v1`. Do not reuse the credential AES key directly. Archive envelope starts with a fixed binary magic/version, then 12-byte nonce, then AES-GCM ciphertext/tag; AAD is the canonical relative path.

- [ ] **Step 4: Implement safe, atomic archive creation**

Canonical path:

```text
{provider}/{connection_id}/{resource}/{YYYY}/{MM}/{run_id}-{page:06d}.jsonl.gz.aes
```

Validate every path component from enums/integers and resolve the result under `archive_dir`. Serialize each record's `sanitized_source_payload` as sorted-key compact JSONL after `assert_payload_safe`, gzip with `mtime=0`, encrypt, write a random `.tmp` sibling, flush/fsync, then `os.replace`. Return relative path, encrypted-file SHA-256 and record count.

Expose an `ArchivePage` context manager: if the surrounding database transaction fails, delete the final file; if the process dies between rename and DB commit, the next orphan scan deletes files older than one hour that lack a manifest.

- [ ] **Step 5: Implement retention cleanup**

Select manifests expired before now and not deleted. Delete the file first; only on success set `deleted_at`. Missing files are treated as deleted but audited. Permission/I/O failures preserve the manifest and enqueue a retry with sanitized error code.

- [ ] **Step 6: Run tests and commit**

Run: `python -m unittest tests.test_integration_archive tests.test_integration_crypto tests.test_integration_redaction -v`

Commit: `git add integrations/sync/archive.py integrations/crypto.py tests/test_integration_archive.py && git commit -m "feat: archive sanitized platform pages securely"`

---

### Task 7: Run Sync Pages With Token Refresh, Retry And Cursor Safety

**Files:**
- Create: `integrations/sync/runner.py`
- Modify: `integrations/sync/queue.py`
- Modify: `integrations/connections.py`
- Test: `tests/test_integration_runner.py`

- [ ] **Step 1: Write failing runner tests with a fake connector**

Fake connector scenarios must prove:

- two-page success advances cursor after each committed page and marks run successful;
- crash before page commit leaves the previous cursor and re-fetches the page safely;
- 429 honors `retry_after`, while network/timeout/5xx use bounded exponential backoff with jitter and at most six attempts;
- 401 triggers exactly one authorization-level locked refresh, atomically replaces both tokens/expiry/tails, then retries once;
- a second auth failure clears token ciphertexts and marks authorization plus all connections `reauthorization_required`;
- permission denial is not retried and yields `permission_limited` with capability reason;
- invalid siblings yield `partial_success` without stopping valid rows;
- platform cursor and watermark persist only after archive manifest and upserts commit.

- [ ] **Step 2: Run and verify red**

Run: `if (-not $env:FACAI_TEST_DATABASE_URL) { throw 'FACAI_TEST_DATABASE_URL is required' }; python -m unittest tests.test_integration_runner -v`

Expected: runner absent.

- [ ] **Step 3: Implement authorization-level token leases**

Acquire refresh lease with a conditional update on `IntegrationAuthorization` where lease is absent/expired. Decrypt tokens only into local `TokenBundle` variables marked `repr=False`; never place them in a job payload. Refresh when connector reports its safety window, always taking platform-returned expiry over local defaults.

- [ ] **Step 4: Implement one-page transaction boundaries**

For each page:

1. fetch and translate through connector;
2. assert/redact records;
3. create encrypted archive within `ArchivePage` context;
4. begin DB transaction, upsert valid rows, insert safe errors, insert manifest, update counters and cursor/watermark;
5. commit; then retain archive;
6. heartbeat job/checkpoint between pages.

If any DB step fails, rollback and let archive context delete the file. A process death may leave an orphan file but cannot advance cursor.

- [ ] **Step 5: Implement retry classification**

Use full-jitter delay `uniform(0, min(900, 2 ** attempt * 5))`, unless typed rate limit provides a later retry time. Store only typed error code and a bounded sanitized summary. Exhausted transient failures mark job/run `failed` and connection `degraded`; a later manual retry creates a child run linked by `parent_run_id`.

- [ ] **Step 6: Run tests and commit**

Run: `if (-not $env:FACAI_TEST_DATABASE_URL) { throw 'FACAI_TEST_DATABASE_URL is required' }; python -m unittest tests.test_integration_runner tests.test_integration_queue tests.test_integration_writer tests.test_integration_archive -v`

Commit: `git add integrations/sync/runner.py integrations/sync/queue.py integrations/connections.py tests/test_integration_runner.py && git commit -m "feat: execute resumable ecommerce sync pages"`

---

### Task 8: Schedule Backfills And Recurring Resource Windows

**Files:**
- Create: `integrations/sync/scheduler.py`
- Test: `tests/test_integration_scheduler.py`

- [ ] **Step 1: Write failing timezone/window tests**

Freeze time around Asia/Shanghai midnight and daylight-independent UTC conversion. Cover:

- first backfill starts at connector capability `earliest_available_at` and ends at now;
- orders/refunds/shipments/daily/ad metrics split by local calendar day with UTC-exclusive boundaries;
- products/SKUs/inventory use a logical scheduled-slot checkpoint window for dedupe while passing `window=None` to APIs that do not support time filtering;
- recurring orders/refunds run every 15 minutes, products/inventory hourly, daily/ads at 06:00 Asia/Shanghai and re-read the most recent seven days;
- all fifteen `ResourceType` values are classified exactly once as direct-scheduled, child-emitted or unavailable-by-capability; no enabled value falls through;
- duplicate scheduler ticks enqueue one logical job;
- disabled/unverified resources are not scheduled;
- token refresh is keyed by authorization and archive cleanup runs daily.

- [ ] **Step 2: Run and verify red**

Run: `python -m unittest tests.test_integration_scheduler -v`

Expected: scheduler absent.

- [ ] **Step 3: Implement pure schedule calculation**

Separate `due_jobs(now, connections, capabilities)` from database enqueueing. Use `zoneinfo.ZoneInfo("Asia/Shanghai")`; all stored boundaries are converted to aware UTC. Treat end as exclusive. Product/SKU/inventory snapshots use the scheduled slot start as their fixed `captured_at`, so retries upsert the same snapshot rather than creating new rows. Never assume a platform supports history earlier than capability report.

Each provider capability assigns every resource exactly one fetch mode: `direct`, `emitted_by:<parent ResourceType>`, or `unavailable`. Validate parent references are acyclic and only schedule `direct`; the runner validates that a parent page emits only its declared children. The default cadence/window matrix below applies only when that exact resource is verified and the catalog may tighten history/QPS:

| Resource | Default cadence/window | Emission rule |
|---|---|---|
| `shops` | daily 05:30, snapshot logical slot | may be emitted by verified account discovery |
| `products` | hourly, snapshot logical slot | direct |
| `skus` | hourly, snapshot logical slot | direct or `emitted_by:products` |
| `inventory` | hourly, snapshot logical slot | direct or `emitted_by:products/skus` as cataloged |
| `orders` | every 15 min, overlap previous 30 min; historical local-day windows | direct; emits `order_items` atomically |
| `order_items` | never independently scheduled | always `emitted_by:orders` |
| `refunds` | every 15 min, overlap previous 30 min; historical local-day windows | direct |
| `shipments` | every 15 min, overlap previous 30 min; historical local-day windows | direct or `emitted_by:orders` |
| `settlements` | daily 06:30, reread latest 7 local days | direct |
| `daily_metrics` | daily 06:00, reread latest 7 local days | direct |
| `ad_accounts` | daily 05:30, snapshot logical slot | direct or verified account discovery |
| `ad_entities` | hourly, snapshot logical slot | direct; catalog may declare entity children |
| `ad_daily_metrics` | daily 06:00, reread latest 7 local days | direct |
| `ad_balance_snapshots` | hourly, snapshot logical slot | direct |
| `ad_finance_transactions` | daily 06:30, reread latest 7 local days | direct |

Tests construct one synthetic fully capable provider and assert the classification set equals `set(ResourceType)`, `order_items` has no checkpoint, child rows commit in the same page transaction as their parent, and any missing/duplicate/cyclic classification fails readiness before scheduling.

- [ ] **Step 4: Implement deduplicated enqueueing**

The scheduler polls once per minute. For each due unit, upsert checkpoint then enqueue a sync job with the checkpoint ID. The seven-day correction window deliberately overlaps prior runs; writer idempotency resolves duplicates.

- [ ] **Step 5: Run tests and commit**

Run: `python -m unittest tests.test_integration_scheduler tests.test_integration_queue -v`

Commit: `git add integrations/sync/scheduler.py tests/test_integration_scheduler.py && git commit -m "feat: schedule ecommerce sync windows"`

---

### Task 9: Operate An Independent Integration Worker Process

**Files:**
- Create: `integrations/sync/worker.py`
- Create: `scripts/integration_worker.py`
- Modify: `scripts/facai_agent_service.py`
- Modify: `scripts/start-facai-agent-service.cmd`
- Modify: `.env.example`
- Test: `tests/test_integration_worker.py`
- Test: `tests/test_service_runtime.py`

- [ ] **Step 1: Write failing worker lifecycle tests**

Test startup readiness, heartbeat insert/update, default concurrency four, graceful SIGTERM, lease renewal, exception isolation, stale worker detection and disabled mode. Extend service-source tests to assert integration worker is a separate child process and is not imported by FastAPI lifespan.

- [ ] **Step 2: Run and verify red**

Run: `python -m unittest tests.test_integration_worker tests.test_service_runtime -v`

Expected: worker and supervision contracts fail.

- [ ] **Step 3: Implement the worker loop**

`python scripts/integration_worker.py` validates PostgreSQL/Alembic/security/archive readiness, assigns a random worker ID, records heartbeat every 10 seconds and runs at most `FACAI_INTEGRATION_WORKER_CONCURRENCY` jobs with `asyncio.TaskGroup`/semaphore. It ticks scheduler and orphan cleanup without blocking claims. SIGTERM stops new claims, waits up to 30 seconds, then releases owned leases for retry.

- [ ] **Step 4: Supervise the second OS process explicitly**

Add `FACAI_INTEGRATION_WORKER_ENABLED=0` to `.env.example`. When it is `1`, `scripts/facai_agent_service.py` starts `scripts/integration_worker.py` as a hidden independent child beside uvicorn, monitors exit and restarts with bounded backoff. Application health remains `/healthz`; worker health comes from `integration_worker_heartbeats` and must not make `/healthz` fail.

Killing/restarting the uvicorn child must not kill a healthy worker. Supervisor shutdown must terminate both children cleanly.

- [ ] **Step 5: Run tests and a controlled smoke process**

Run:

```powershell
if (-not $env:FACAI_TEST_DATABASE_URL) { throw 'FACAI_TEST_DATABASE_URL is required' }
$env:DATABASE_URL=$env:FACAI_TEST_DATABASE_URL
$env:FACAI_INTEGRATION_WORKER_ENABLED='1'
python -m unittest tests.test_integration_worker tests.test_service_runtime -v
python scripts/integration_worker.py --once
```

Expected: heartbeat appears, scheduler tick completes, no long-running child remains after `--once`.

- [ ] **Step 6: Commit worker operation**

Commit: `git add integrations/sync/worker.py scripts/integration_worker.py scripts/facai_agent_service.py scripts/start-facai-agent-service.cmd .env.example tests/test_integration_worker.py tests/test_service_runtime.py && git commit -m "feat: run integration sync in a supervised worker"`

---

### Task 10: Add Connection, Sync, Retry, Disable And Purge APIs

**Files:**
- Modify: `integrations/connections.py`
- Modify: `integrations/schemas.py`
- Modify: `routers/integrations.py`
- Test: `tests/test_integration_management_api.py`
- Test: `tests/test_integration_purge.py`

- [ ] **Step 1: Write failing strict API tests**

Cover every approved endpoint and prove:

- responses expose safe token masks/expiry/scope but no ciphertext/token/secret;
- manual sync validates connection/resource/aware date boundaries and enqueues deduped windows;
- reauthorize starts a fresh OAuth state without deleting historical data;
- disabling one connection preserves data and a shared authorization/token used by another connection;
- deleting an authorization revokes when supported, clears tokens and disables all children;
- retry creates a child run for the failed window;
- purge requires current admin password plus exact display name, is idempotent, preserves audit, removes only the selected connection's business/sync/archive data, and deletes authorization only when no connection remains;
- all mutation bodies reject unknown fields and all mutations audit success/failure.

- [ ] **Step 2: Run and verify red**

Run: `if (-not $env:FACAI_TEST_DATABASE_URL) { throw 'FACAI_TEST_DATABASE_URL is required' }; python -m unittest tests.test_integration_management_api tests.test_integration_purge -v`

Expected: management endpoints absent.

- [ ] **Step 3: Implement safe view and command schemas**

Add `ConnectionView`, `ManualSyncRequest`, `ReauthorizationRequest`, `RetryRunRequest`, `PurgeConnectionRequest` with `extra="forbid"`. `PurgeConnectionRequest` contains `password: SecretStr` and `confirmation: str`; never log/model-dump the password.

- [ ] **Step 4: Implement management transactions**

Add the exact routes from the design. `DELETE /connections/{id}` sets `disabled_at/status` only. `DELETE /authorizations/{id}` calls connector revoke outside the DB transaction, then clears token ciphertext/tails and disables children; a platform revoke failure is audited but local credentials are still cleared.

Purge verifies password synchronously, disables the connection, then enqueues one `purge_connection` job. Worker deletes referenced archive files and all connection-owned rows in FK-safe order in one DB transaction, retaining security audits. After commit, it deletes an unreferenced authorization. File failures keep a retryable purge job and do not report completion.

- [ ] **Step 5: Run tests and commit**

Run: `if (-not $env:FACAI_TEST_DATABASE_URL) { throw 'FACAI_TEST_DATABASE_URL is required' }; python -m unittest tests.test_integration_management_api tests.test_integration_purge tests.test_integration_auth -v`

Commit: `git add integrations/connections.py integrations/schemas.py routers/integrations.py tests/test_integration_management_api.py tests/test_integration_purge.py && git commit -m "feat: manage ecommerce connections and sync jobs"`

---

### Task 11: Sync-Core Verification Gate

**Files:**
- Verify all files in this plan.

- [ ] **Step 1: Run PostgreSQL core tests without skips**

Run:

```powershell
if (-not $env:FACAI_TEST_DATABASE_URL) { throw 'FACAI_TEST_DATABASE_URL is required' }
python -m unittest tests.test_integration_commerce_models tests.test_integration_sync_models tests.test_integration_queue tests.test_integration_writer tests.test_integration_archive tests.test_integration_runner tests.test_integration_scheduler tests.test_integration_worker tests.test_integration_management_api tests.test_integration_purge -v
```

Expected: all pass, zero skips.

- [ ] **Step 2: Run security/connector regressions**

Run:

```powershell
python -m unittest tests.test_provider_contract_evidence tests.test_integration_connector_contract tests.test_integration_crypto tests.test_integration_redaction tests.test_integration_oauth tests.test_integration_public_boundary -v
```

Expected: all pass.

- [ ] **Step 3: Run full gates**

Run:

```powershell
python -m compileall -q .
python -m unittest discover -s tests -v
git diff --check
git status --short
```

Expected: no failures, no secret/PII artifacts, only planned files changed.
