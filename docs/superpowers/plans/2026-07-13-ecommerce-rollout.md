# Ecommerce API Integration Rollout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在公司内网安全完成 PostgreSQL 切换、应用与 worker 启动、公网回调最小暴露、千川/抖店真实回溯与对账，并保留可验证的 SQLite 回滚路径；淘宝/拼多多按实际审批独立启用。

**Architecture:** 上线前在生产副本完成全部迁移与负载验证；维护窗口内停止旧写入、备份/哈希 SQLite、迁入空 PostgreSQL，并先用只读 PostgreSQL 角色隔离 smoke。只有在证明零写入后才能回退 SQLite；一旦开放 PostgreSQL 写流量即进入 point-of-no-return，后续仅做 PostgreSQL 恢复/向前修复。平台连接逐个启用，公网反向代理只转发两类回调。

**Tech Stack:** Windows PowerShell、Alembic/PostgreSQL、existing supervised uvicorn、integration worker heartbeat、HTTPS reverse proxy、FastAPI/live API/browser tests。

## Global Constraints

- 本计划不是自动部署授权。真实数据库账号、DNS/证书、反向代理和平台控制台变更由公司授权人员在明确维护窗口执行。
- 生产 `DATABASE_URL`、Secret、Token 和管理员口令不得出现在命令历史、截图、计划文档或提交；PowerShell 从受控环境/secret store 读取。
- 目标 PostgreSQL 必须为空并有备份策略；迁移命令拒绝非空目标。
- 千川/抖店先上线；淘宝/拼多多未完成真实 gate 不阻塞，但保持 pending。
- 任一数据校验或核心业务 smoke 失败立即停止切换，不“边跑边修”生产数据。
- `/healthz` 只反映应用/数据库；worker 与平台同步健康通过单独管理 API/heartbeat 观察。

---

### Task 1: Add Machine-Readable Readiness And Public-Boundary Checks

**Files:**
- Create: `scripts/check_integration_readiness.py`
- Create: `scripts/verify_public_callback_boundary.py`
- Create: `tests/test_integration_readiness_scripts.py`
- Create: `docs/runbooks/ecommerce-integration-operations.md`

- [ ] **Step 1: Write failing CLI contract tests**

`check_integration_readiness.py --json` must report independent booleans/codes for database dialect/connectivity, Alembic head, login readiness, credential readiness, archive read/write/delete probe, worker heartbeat age, and each provider's catalog/app/OAuth/backfill/incremental/reconciled stages. It never returns environment values.

`verify_public_callback_boundary.py --base-url $env:FACAI_INTEGRATIONS_PUBLIC_BASE_URL` probes only safe GETs and expects:

- OAuth callback path without state: reachable application response (400), not proxy 404;
- event provider without valid signature: 4xx/503, never 2xx acceptance;
- `/`, `/healthz`, `/app`, `/api/integrations/providers`, `/static/js/common.js`: 404 from public boundary.

Reject non-HTTPS/non-test URLs unless `--allow-local-http` and loopback.

- [ ] **Step 2: Run and verify red**

Run: `python -m unittest tests.test_integration_readiness_scripts -v`

Expected: scripts absent.

- [ ] **Step 3: Implement safe readiness output**

Use service functions, `alembic_version`, archive temp probe and heartbeat query. Exit 0 only when requested scope is ready; `--allow-provider-pending taobao,pdd` permits those providers without hiding their false stages. Bound all error messages to stable codes.

- [ ] **Step 4: Implement boundary probe without credentials**

Use `httpx.Client(follow_redirects=False, timeout=10)`. Do not send cookies, tokens, codes or signatures. Print method/path/status/pass JSON. A network/TLS error is failure.

- [ ] **Step 5: Add operations runbook and commit**

Document normal worker start/stop, heartbeat thresholds, task retry, reauthorization, archive/export cleanup, provider rate/permission failures, daily checks and escalation without credential logging.

Run: `python -m unittest tests.test_integration_readiness_scripts -v`

Commit: `git add scripts/check_integration_readiness.py scripts/verify_public_callback_boundary.py tests/test_integration_readiness_scripts.py docs/runbooks/ecommerce-integration-operations.md && git commit -m "ops: add integration readiness checks"`

---

### Task 2: Validate The Entire Release On A Production-Like Copy

**Files:**
- Create: `docs/runbooks/ecommerce-preproduction-validation.md`
- Modify only if tests reveal in-scope defects.

- [ ] **Step 1: Create a clean validation environment**

Use a clean worktree/checkout of the release commit, Python 3.12 virtual environment, `python -m pip install -r requirements.txt`, `npm.cmd ci`, a frozen approved SQLite production-data copy, a private archive directory, and two isolated disposable PostgreSQL databases on the same target major version:

- `FACAI_TEST_DATABASE_URL`: automated test/Alembic round-trip database; tests may drop/recreate it.
- `FACAI_MIGRATION_TEST_DATABASE_URL`: initially empty migration target used only by the SQLite copier, then retained as the populated preproduction application/worker database.

Never point both names at the same database. Assert their parsed host/database pairs differ before any destructive test. Scrub external credentials unless live staging is explicitly authorized.

- [ ] **Step 2: Run all automated gates**

Run:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q .
npm.cmd run test:e2e
```

Expected: zero failures; PostgreSQL tests run with `FACAI_TEST_DATABASE_URL` and do not skip.

Before the suite, run `python scripts/assert_disposable_postgres.py --env FACAI_TEST_DATABASE_URL --ack-env FACAI_DESTRUCTIVE_TEST_DATABASE_ACK`; the acknowledgement must equal the exact `_test`/`_ci` database name. The suite itself repeats the guard before any destructive setup.

- [ ] **Step 3: Exercise migration round-trip**

Run Alembic downgrade/upgrade only on `FACAI_TEST_DATABASE_URL`. Independently require the migration target and create schema there before the copier:

```powershell
if (-not $env:FACAI_SQLITE_MIGRATION_SOURCE) { throw 'FACAI_SQLITE_MIGRATION_SOURCE is required' }
python scripts/migrate_sqlite_to_postgres.py --source $env:FACAI_SQLITE_MIGRATION_SOURCE --backup-only
if (-not $env:FACAI_MIGRATION_TEST_DATABASE_URL) { throw 'FACAI_MIGRATION_TEST_DATABASE_URL is required' }
$env:FACAI_MIGRATION_DATABASE_URL = $env:FACAI_MIGRATION_TEST_DATABASE_URL
alembic upgrade head
python scripts/migrate_sqlite_to_postgres.py --source $env:FACAI_SQLITE_MIGRATION_SOURCE --target-env FACAI_MIGRATION_TEST_DATABASE_URL --dry-run
python scripts/migrate_sqlite_to_postgres.py --source $env:FACAI_SQLITE_MIGRATION_SOURCE --target-env FACAI_MIGRATION_TEST_DATABASE_URL --apply
```

Before dry-run, assert every metadata table in the migration target is empty and fail if not. Confirm source/target rows, key amount totals, JSON, FK, uniqueness and sequences. Insert one safe test row per major existing domain and prove generated IDs exceed migrated maxima. Do not run the destructive automated suite against this now-populated target.

- [ ] **Step 4: Run application/worker smoke and recovery**

Set the validation process `DATABASE_URL` to `FACAI_MIGRATION_TEST_DATABASE_URL`, start uvicorn and integration worker, and verify `/healthz`, existing product/script/template/creator/search/AI-work pages, integration login, data center and heartbeat. Terminate worker during a multi-page fake/staging sync; restart and prove cursor resumes.

- [ ] **Step 5: Record exact evidence**

Runbook records release commit, test counts, database source/target SHA-256 identifiers, migration report path, smoke result, E2E result and reviewer—no secrets or buyer PII.

- [ ] **Step 6: Commit runbook evidence template**

Commit: `git add docs/runbooks/ecommerce-preproduction-validation.md && git commit -m "docs: add ecommerce preproduction validation"`

---

### Task 3: Configure The HTTPS Callback Boundary

**Files:**
- Create: `docs/runbooks/ecommerce-callback-proxy.md`
- No production proxy write is performed by repository code.

- [ ] **Step 1: Obtain authorized infrastructure inputs**

Required: stable public HTTPS callback hostname, separate stable internal HTTPS admin origin, valid certificates, internal upstream address, proxy owner, DNS/ACL approval and four platform callback settings. The public hostname must differ from `FACAI_INTEGRATIONS_INTERNAL_BASE_URL`; register both exact hostname/port pairs in the application Host allowlist with no wildcard. The public proxy exposes only callbacks, while OAuth completion 303 redirects the initiating browser back to the configured internal origin.

- [ ] **Step 2: Configure exact allowlist at the reverse proxy**

Forward only:

```text
GET  /integrations/oauth/callback/qianchuan
GET  /integrations/oauth/callback/doudian
GET  /integrations/oauth/callback/taobao
GET  /integrations/oauth/callback/pdd
GET|POST /integrations/events/qianchuan
GET|POST /integrations/events/doudian
```

Only expose the Qianchuan event path when its SPI verifier is actually enabled; Doudian requires its verified message contract. Taobao TMC and Pinduoduo WebSocket are not HTTP callbacks and their `/events` paths stay unproxied. Do not proxy `/app`, `/api`, `/healthz`, `/static`, docs or arbitrary suffixes. Preserve the validated Host and bound request size; terminate TLS at the authorized proxy. Configure proxy access logs to omit/redact callback query values such as OAuth `code/state`, then prove a controlled fake code appears in neither proxy nor application logs.

For any authorized internal proxy that carries the administrator login route, set `FACAI_INTEGRATIONS_TRUSTED_PROXY_CIDRS` to its exact CIDR and configure that proxy to overwrite `X-Forwarded-For` with its verified client chain and `X-Forwarded-Proto` with the terminated client scheme. Never trust a catch-all network and never append an inbound client-supplied forwarding header. Confirm the deployed Uvicorn launch has automatic proxy-header rewriting disabled, then test two client addresses behind the same proxy, Secure cookie issuance on TLS termination, and an untrusted source/scheme spoof attempt.

- [ ] **Step 3: Register platform callback URLs**

Use the exact `FACAI_INTEGRATIONS_PUBLIC_BASE_URL`-derived URLs in each approved platform console. Do not add wildcard callbacks or temporary tunnels to production credentials.

- [ ] **Step 4: Probe from an external network**

Run: `python scripts/verify_public_callback_boundary.py --base-url $env:FACAI_INTEGRATIONS_PUBLIC_BASE_URL`

Expected: only callback routes reach the app; every business/health/static path is externally 404.

- [ ] **Step 5: Record owner/config evidence**

Document proxy product/config reference, certificate expiry owner, test timestamp and statuses without copying private keys or full config secrets.

---

### Task 4: Perform The SQLite-To-PostgreSQL Maintenance-Window Cutover

**Files:**
- Follow: `docs/runbooks/postgres-cutover.md`
- Update: `docs/runbooks/ecommerce-preproduction-validation.md` with production-safe evidence references.

- [ ] **Step 1: Freeze scope and capture rollback inputs**

Record release commit, old SQLite `DATABASE_URL` secret reference, new PostgreSQL secret reference, start time, operator/reviewer and rollback decision owner. Confirm target DB empty, backups enabled and no platform worker enabled.

- [ ] **Step 2: Stop all writers**

Stop the supervised uvicorn child, vector/background writes and integration worker. Confirm no process holds/writes the SQLite file and no import/generation jobs are running.

- [ ] **Step 3: Back up and hash SQLite**

Run `python scripts/migrate_sqlite_to_postgres.py --source $env:FACAI_SQLITE_MIGRATION_SOURCE --backup-only`. Use the migration tool's SQLite backup API, not a live filesystem copy. Store source/backup SHA-256, integrity result and size in the maintenance record. Keep the original file read-only after freeze. Do not prepare or open the target until this command succeeds.

- [ ] **Step 4: Prepare and dry-run target**

Set target `DATABASE_URL` only in the maintenance shell/secret manager, run `alembic upgrade head`, then migration `--dry-run`. Review every table count, amount, FK, unique and JSON result. Any failure stops the cutover.

- [ ] **Step 5: Apply once and revalidate**

Run migration `--apply`. Independently query total tables/rows, newest record timestamps and a random safe sample across products, scripts, templates, Qianchuan legacy data and creator domain. Verify sequences.

- [ ] **Step 6: Smoke through a read-only PostgreSQL role with all traffic closed**

Create/use a least-privilege PostgreSQL login with `SELECT` and sequence-read permission only, set it in the isolated maintenance process, leave `FACAI_INTEGRATION_WORKER_ENABLED=0`, keep the reverse proxy/user traffic closed, and bind smoke access to the operator host. Perform GET/read-only smoke for `/healthz`, `/app`, products, scripts, templates, creators, search, AI configuration, legacy Qianchuan read and the integration login page. Verify password/session crypto with the focused offline test; do not POST login/import/generation or any mutation during this reversible window.

- [ ] **Step 7: Make the cutover decision**

Compare every table count, max updated timestamp and migration manifest digest to the immediate post-apply baseline and require zero changes. If any critical smoke fails or any row changed, keep traffic closed, investigate, and only when zero legitimate PostgreSQL writes occurred may the decision owner stop the new service, restore the old SQLite URL/original supervisor, and verify core pages. Preserve failed PostgreSQL for diagnosis; never reverse-write it.

- [ ] **Step 8: Record point-of-no-return and open PostgreSQL writes**

If all evidence passes, record reviewer approval and an exact `sqlite_rollback_closed_at` timestamp, switch the managed `DATABASE_URL` to the PostgreSQL write role, start the normal app, then open internal traffic. The first successful application write permanently closes simple SQLite rollback. From this point, incidents use PostgreSQL backup/PITR or a forward fix under a new change record; do not restore the frozen SQLite. Keep the integration worker running with no active provider schedules until Task 5 enables them one by one.

---

### Task 5: Enable Providers Incrementally And Reconcile

**Files:**
- Follow provider live-acceptance runbooks.
- Update safe acceptance records only.

- [ ] **Step 1: Enable one Qianchuan authorization**

Perform OAuth/probe, run a small recent manual window, verify archive/rows/UI, then start historical backfill at conservative concurrency. Observe rate errors, worker heartbeat, retries and disk growth before adding accounts.

- [ ] **Step 2: Reconcile Qianchuan and then expand**

Pass its 20-row ID/amount and aggregate tolerance. Only then mark reconciled/active and add remaining法采 accounts one at a time.

- [ ] **Step 3: Enable one Doudian shop**

Repeat OAuth/probe/small window/backfill. Verify PII absence, event signature/ack if approved and polling final state. Reconcile 20 orders/amounts to cent before active.

- [ ] **Step 4: Enable remaining Doudian shops one at a time**

Confirm job backlog, rate limits, database load and archive growth remain within operations thresholds.

- [ ] **Step 5: Keep Taobao/PDD pending or run identical live gates**

Without approved catalog/app/OAuth, show pending and schedule nothing. With approvals, complete their provider plan OAuth, renewal, backfill, incremental and export reconciliation before active.

- [ ] **Step 6: Validate unified data center**

For each active connection, compare API data, data-center list/overview, CSV/XLSX export and relevant legacy Qianchuan script view. Filters and totals must use the same backend source.

---

### Task 6: Observe, Exercise Rollback And Close The Release

**Files:**
- Update: `docs/runbooks/ecommerce-integration-operations.md`

- [ ] **Step 1: Observe the first 24 hours**

At least at start, +1h, +4h and next-day 06:00 run, record application health, worker heartbeat age, queue depth/oldest job, failed/partial runs, connection/auth state, PostgreSQL CPU/storage, archive/export storage and rate-limit counts.

- [ ] **Step 2: Verify retention and recovery jobs**

In a controlled test record, confirm export expires after 24h, archive cleanup policy targets >90 days, cleanup failure retries without losing manifest, and worker restart resumes leases/cursors.

- [ ] **Step 3: Exercise rollback in staging after release candidate freeze**

Stop app/worker, restore old SQLite URL and start old mode; verify core pages. Then switch back to PostgreSQL without rerunning SQLite apply and verify current state. Production rollback is invoked only by the documented decision owner.

- [ ] **Step 4: Run final gates on the deployed commit**

Run:

```powershell
python scripts/check_integration_readiness.py --json --allow-provider-pending taobao,pdd
python scripts/verify_public_callback_boundary.py --base-url $env:FACAI_INTEGRATIONS_PUBLIC_BASE_URL
python -m unittest discover -s tests -v
python -m compileall -q .
npm.cmd run test:e2e
```

- [ ] **Step 5: Close only when evidence is complete**

Release record includes deployed commit, migration report, smoke results, active/pending platform stages, reconciliation summaries, public-boundary probe, heartbeat and rollback exercise. Never mark the full program complete solely because code merged.
