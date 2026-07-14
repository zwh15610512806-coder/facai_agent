# Product Canvas Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在已完成的画布与产品保真管线上接入 Seedream 5.0 Pro 完整版，交付无默认输出的完整套图配置、预定义高级节点、逐图持久任务、进度/取消/重试、幂等与服务重启恢复。

**Architecture:** 每个用户请求创建一个 `CanvasGeneration`，每张图片对应独立 Item 和不可覆盖的 Attempt 历史。SQLite 队列用短事务、租约和进程内 worker 驱动，默认全局并发 1，调高后仍受项目/Provider/Model 限制。Provider 只生成背景/场景，成功结果先持久化为同源背景资产，再由持久 compose Operation 覆盖锁定产品与显式文字。完整套图和高级节点只是在同一语义图上的两种投影。

**Tech Stack:** FastAPI, SQLAlchemy, SQLite leased queue, httpx, Seedream/Volcengine Images API, TypeScript, Fabric.js, SSE, Vitest, Playwright.

## Global Constraints

- 先验收切片 1 和切片 2；本计划只实现交付切片 3。
- 内置 UI 名称精确为 `Seedream 5.0 Pro（完整版）`，模型 ID 精确为 `doubao-seedream-5-0-260128`；Lite ID 不得进入内置配置。
- Provider 不得重绘产品。Seedream 本阶段按背景生成能力使用，不把包装、Logo、标签文字或产品外形交给模型重建；最终产品像素来自 compositor。
- 创建 Generation 必须有用户已选择的输出、素材、数量、比例/尺寸和可用模型；新项目没有默认输出或默认模型。
- 一次 Generation 最多 50 张、每输出组最多 20 张、每 Item 对应一张图和一个稳定输出画板。
- 同项目只运行一个 Generation；全局图片生成默认并发 1。
- 网络调用期间不得持有 SQLAlchemy Session 或 SQLite 写事务。
- 没有上游幂等能力时，已进入 `submitting` 的付费请求中断后标记 `unknown`，绝不自动重提。
- 重试只为失败/用户确认的 unknown Item 创建新 Attempt；成功版本不覆盖、不重跑。
- 所有生成、取消、重试和 unknown 处理要求 Canvas 访问会话；自动测试仅使用 Fake Provider。
- 每项按 TDD 执行并单独提交；不要暂存无关电商文档或工作区改动。

---

### Task 1: Add Durable Provider And Generation Tables

**Files:**
- Modify: `canvas_models.py`
- Modify: `database.py`
- Modify: `services/canvas/assets.py`
- Create: `tests/test_canvas_generation_models.py`
- Modify: `tests/test_canvas_migrations.py`
- Modify: `tests/test_canvas_assets.py`

- [ ] **Step 1: Write failing schema tests**

Assert creation, indexes, uniqueness, FK behavior, backup and idempotent `init_db()` for:

- `image_provider_connections`
- `image_model_profiles`
- `canvas_generations`
- `canvas_generation_items`
- `canvas_generation_item_inputs`
- `canvas_generation_attempts`
- The migration rebuilds `canvas_events` to add nullable `generation_id` and `item_id` FKs with `ON DELETE SET NULL`, preserves existing event IDs, and retains the operation FK added in slice 2.
- Generation inputs and output/background assets use restrictive FKs; `delete_asset()` also reports Generation Item/Input/Attempt references and refuses soft deletion.

Run:

```powershell
python -m unittest tests.test_canvas_generation_models tests.test_canvas_migrations -v
```

Expected: missing-table failures.

- [ ] **Step 2: Define provider catalog models**

The built-in Seedream Provider/Profile uses the same catalog as later third-party models. Include:

- Provider adapter type, name, base URL, auth type, nullable encrypted-credential field, nullable environment credential reference, credential hint, enabled flag and config version. Slice 3 only uses the environment reference for Seedream; the encrypted field is activated by slice 4.
- Model provider FK, model ID, display name, capabilities JSON, non-secret protocol/config JSON, enabled flag and config version.
- Soft disable only; historical generation snapshots cannot cascade away.

- [ ] **Step 3: Define generation history models**

Required invariants:

```text
UNIQUE(canvas_generations.project_id, idempotency_key)
UNIQUE(canvas_generation_item_inputs.item_id, input_role, ordinal)
UNIQUE(canvas_generation_attempts.item_id, attempt_no)
```

`CanvasGeneration` saves project revision, request snapshot, fingerprint, idempotency key, status, totals, `storage_reservation_bytes`, `storage_reservation_remaining_bytes`, safe storage-block reason/time, cancel-requested time, lease/heartbeat and lifecycle timestamps. `CanvasGenerationItem` saves output type, SKU name/ID snapshot, board/node IDs and board-order snapshot, model/provider IDs and versions, the submitted non-secret Provider/Model configuration snapshot, prompt, dimensions, layout/group hash, latest terminal background/composed summary IDs, safe current error, attempt count and status. The board’s currently selected result asset exists only in project semantic state and is never duplicated on the Item. Inputs save asset ID, role, ordinal and SHA snapshot.

Every `CanvasGenerationAttempt` independently saves Provider/Model IDs and versions, submitted non-secret config snapshot, state, `provider_result_stage`, `provider_accepted_at`, `provider_request_id`, `external_task_id`, upstream idempotency key, lease/heartbeat/poll/submission timing, usage JSON, `background_asset_id`, `background_preview_asset_id`, `composed_asset_id`, `composed_preview_asset_id`, `compose_operation_id`, normalized error code/summary, raw safe upstream error code and timestamps. Result stages are `awaiting_provider`, `receiving`, `background_persisted`, `composing` and `complete`. Do not use one ambiguous `output_asset_id` that gets overwritten by composition. Attempt-to-compose is unique, and services validate that Attempt, Operation and all full/preview assets belong to the same project with explicit derived relations. The version endpoint derives one immutable result version per successful composed Attempt; Item asset IDs are latest-summary fields only.

Historical non-secret snapshots rebuild the original request shape after a configuration edit, but every recovery still applies the current SSRF/network policy and obtains the current valid credential. Historical configuration can never relax a new security rule or resurrect a disabled/undecryptable secret.

Use exact states:

```python
GenerationStatus = Literal[
    "queued", "running", "partially_failed", "succeeded", "failed",
    "cancel_requested", "cancelled", "interrupted", "unknown",
]
AttemptStatus = Literal[
    "queued", "submitting", "polling", "succeeded", "failed",
    "cancel_requested", "cancelled", "unknown",
]
ItemStatus = Literal[
    "queued", "running", "composing", "succeeded", "failed",
    "cancel_requested", "cancelled", "unknown",
]
```

- [ ] **Step 4: Register migration requirements and run tests**

```powershell
python -m unittest tests.test_canvas_generation_models tests.test_canvas_migrations -v
```

Expected: all schema tests pass.

- [ ] **Step 5: Commit**

```powershell
git add canvas_models.py database.py services/canvas/assets.py tests/test_canvas_generation_models.py tests/test_canvas_migrations.py tests/test_canvas_assets.py
git commit -m "feat: add durable canvas generation schema"
```

---

### Task 2: Protect Paid Canvas Operations With An Access Session

**Files:**
- Modify: `config.py`
- Modify: `.env.example`
- Create: `services/canvas/access.py`
- Create: `routers/canvas/access.py`
- Modify: `routers/canvas/__init__.py`
- Create: `tests/test_canvas_access.py`

- [ ] **Step 1: Write failing access tests**

Cover:

- `GET /api/canvas/access/status` returns configured/locked state without disclosing a token.
- Missing `CANVAS_ACCESS_TOKEN` makes protected endpoints return 503.
- Wrong token returns 401 and sets no cookie.
- Correct unlock sets an opaque HttpOnly, SameSite=Strict cookie; HTTPS also sets Secure.
- Cookie contains a signed, expiring session proof, not raw token or reversible token bytes.
- Lock clears the cookie; expiry and token change invalidate old sessions.
- Constructing a second app lifespan with a new process-session secret invalidates cookies minted by the first lifespan without persisting the raw token.
- Project browsing/local saves remain available while locked.
- `CANVAS_ACCESS_SESSION_TTL_SECONDS` has a bounded positive default and can be shortened in tests.

- [ ] **Step 2: Implement the dependency and endpoints**

```python
def canvas_access_status(request: Request) -> CanvasAccessStatus: ...
def unlock_canvas_access(request: Request, response: Response, token: str) -> None: ...
def lock_canvas_access(response: Response) -> None: ...
def require_canvas_paid_access(request: Request) -> None: ...
```

Expose exactly:

```text
GET  /api/canvas/access/status
POST /api/canvas/access/unlock
POST /api/canvas/access/lock
```

Use constant-time token comparison. At process startup generate a 32-byte random in-memory session secret, combine it with `CANVAS_ACCESS_TOKEN` and a fixed Canvas-session domain separator, and sign an expiry/nonce payload with HMAC-SHA256. Restarting the process or rotating the token invalidates every old proof, and a captured cookie is not an offline token verifier by itself. Do not store unlock material in project state, logs, localStorage or sessionStorage.

- [ ] **Step 3: Run and commit**

```powershell
python -m unittest tests.test_canvas_access -v
git add config.py .env.example services/canvas/access.py routers/canvas/access.py routers/canvas/__init__.py tests/test_canvas_access.py
git commit -m "feat: protect paid canvas operations"
```

---

### Task 3: Define The Provider Protocol And Built-In Seedream Profile

**Files:**
- Modify: `requirements.txt`
- Create: `services/canvas/providers/__init__.py`
- Create: `services/canvas/providers/base.py`
- Create: `services/canvas/providers/registry.py`
- Create: `services/canvas/providers/bootstrap.py`
- Create: `services/canvas/providers/seedream.py`
- Create: `services/canvas/provider_catalog.py`
- Create: `services/canvas/provider_schemas.py`
- Create: `services/canvas/provider_network.py`
- Create: `services/canvas/remote_images.py`
- Create: `routers/canvas/providers.py`
- Modify: `routers/canvas/__init__.py`
- Modify: `config.py`
- Modify: `.env.example`
- Modify: `services/canvas/runtime.py`
- Modify: `main.py`
- Create: `tests/test_canvas_seedream_provider.py`

- [ ] **Step 1: Write provider contract tests**

Test capability validation, redacted logging, sync completion, async pending contract, normalized errors and stable model bootstrap. Verify `CANVAS_REMOTE_IMAGE_MAX_BYTES` defaults to 26,214,400, accepts a smaller valid administrator value, rejects non-positive/oversized values, and drives both stream and decoded-image rejection. Assert:

```python
SeedreamAdapter.MODEL_ID == "doubao-seedream-5-0-260128"
SeedreamAdapter.DISPLAY_NAME == "Seedream 5.0 Pro（完整版）"
```

Reject any Lite model ID in the built-in profile.

- [ ] **Step 2: Define the common protocol**

Pin `httpcore==1.0.9` alongside the repository’s existing `httpx==0.27.2` so the controlled network backend has a stable interface.

```python
@dataclass(frozen=True)
class ModelCapabilities:
    text_to_image: bool
    image_to_image: bool
    mask_edit: bool
    allowed_ratios: tuple[str, ...]
    allowed_sizes: tuple[str, ...]
    min_width: int | None
    max_width: int | None
    min_height: int | None
    max_height: int | None
    max_quantity: int
    max_reference_images: int
    reference_transfer: Literal["none", "bytes", "base64", "public_url"]
    protocol: Literal["sync", "async", "both"]
    supports_cancel: bool
    supports_idempotency: bool
    supports_idempotency_lookup: bool
    concurrency_limit: int
    price_metadata: dict | None

class ImageProviderAdapter(Protocol):
    def validate_request(self, request: ProviderGenerationRequest,
                         capabilities: ModelCapabilities) -> None: ...
    async def submit(self, request: ProviderGenerationRequest,
                     runtime: ProviderRuntime) -> ProviderSubmission: ...
    async def poll(self, submission: ProviderSubmission,
                   runtime: ProviderRuntime) -> ProviderPollResult: ...
    async def cancel(self, submission: ProviderSubmission,
                     runtime: ProviderRuntime) -> ProviderCancelResult: ...
    async def recover_by_idempotency_key(
        self, upstream_key: str, runtime: ProviderRuntime
    ) -> ProviderRecoveryResult: ...
```

Result DTOs carry bytes or a controlled remote URL only; they never return a URL directly to the browser.
`ProviderRecoveryResult` is a closed union of `found_pending`, `found_completed`, `not_found` and `unsupported`. Submission idempotency and lookup capability are separate; a Provider advertising only duplicate-submit protection is never queried or resubmitted as if it supported lookup.

- [ ] **Step 3: Implement the Seedream request exactly**

Use `ARK_API_KEY` first, then `DOUBAO_API_KEY`, and submit one background per Attempt:

```json
{
  "model": "doubao-seedream-5-0-260128",
  "prompt": "<validated background/scene prompt>",
  "size": "<validated size>",
  "sequential_image_generation": "disabled",
  "stream": false,
  "response_format": "url",
  "watermark": false
}
```

Endpoint is `https://ark.cn-beijing.volces.com/api/v3/images/generations`. Do not include product text layers in the prompt. Do not send a product reference unless a later capability profile and protected-mask path explicitly prove that the subject cannot be redrawn; the built-in slice-3 flow generates backgrounds only.

- [ ] **Step 4: Persist trusted results safely**

The slice-3 `provider_network.py` implements the public-HTTPS subset of the final network policy: resolve and validate every address, pin the TCP connection to a validated IP while retaining the original Host/TLS SNI, ignore proxy environment, and never follow a submit redirect. Set `CANVAS_REMOTE_IMAGE_MAX_BYTES=26214400`; `download_remote_image()` sends no Ark credential, follows at most two result redirects with fresh validation/pinning, rejects loopback/private/link-local/reserved/metadata IPs, enforces that same 25 MB streaming and decoded-image hard cap, validates image MIME/magic/decode and returns a `VerifiedRemoteImage` bytes/controlled-temp DTO without a DB Session. A JSON/Base64 protocol may have its own smaller bounded encoded-response limit, but decoded image bytes still use this shared 25 MB cap. After await completes, a short transaction calls `persist_derived_image(asset_type="generated_background")` and cleans the temp file. Slice 4 extends this same module for administrator allowlists and explicitly permitted enterprise private origins without changing the default cap.

- [ ] **Step 5: Bootstrap idempotently and test**

`main.py` lifespan calls `bootstrap_builtin_image_profiles()` after DB initialization and before generation recovery/worker startup. It creates or upgrades the built-in Provider/Profile by stable IDs and config version without overwriting user enable/disable choice. When neither `ARK_API_KEY` nor `DOUBAO_API_KEY` exists, the catalog returns `availability="missing_credential"` and selectors disable it with a reason rather than choosing another model. Lifespan tests prove the production registry contains the profile after a clean and repeated startup. Tests use a fake HTTP transport and assert Authorization is redacted.

Expose the safe read-only catalog needed for interactive selection:

```text
GET /api/canvas/model-providers
GET /api/canvas/model-providers/{provider_id}/models
```

Responses include IDs, names, enabled/availability state, config version, capabilities and price metadata only—never credential fields or internal environment names. Slice 4 extends these same service/router files with protected write/test operations.

```powershell
python -m unittest tests.test_canvas_seedream_provider -v
git add requirements.txt config.py .env.example services/canvas/providers services/canvas/provider_catalog.py services/canvas/provider_schemas.py services/canvas/provider_network.py services/canvas/remote_images.py routers/canvas/providers.py routers/canvas/__init__.py services/canvas/runtime.py main.py tests/test_canvas_seedream_provider.py
git commit -m "feat: add Seedream 5 full image provider"
```

---

### Task 4: Create Strict Idempotent Generations

**Files:**
- Create: `services/canvas/generation/__init__.py`
- Create: `services/canvas/generation/fingerprints.py`
- Create: `services/canvas/generation/repository.py`
- Create: `services/canvas/generation/schemas.py`
- Create: `routers/canvas/generations.py`
- Modify: `services/canvas/projects.py`
- Modify: `services/canvas/storage.py`
- Modify: `routers/canvas/projects.py`
- Modify: `routers/canvas/__init__.py`
- Create: `tests/test_canvas_generations.py`

- [ ] **Step 1: Write failing creation/API tests**

Cover:

- `POST /api/canvas/projects/{project_id}/generations` requires paid access and `Idempotency-Key` of 16–128 safe characters.
- Request fields use `extra="forbid"` and contain 1–50 explicit Items.
- No output/model/material/count/size results in 422 with itemized missing reasons.
- Same project/key/fingerprint returns the existing task; same key/different fingerprint returns 409.
- Two concurrent same-project/same-key/same-fingerprint POSTs are serialized by the unique constraint/transaction; an insert race catches the integrity conflict and rereads the one existing Generation instead of returning 500 or inserting twice.
- A stale project revision returns 409 before any Item/Attempt is queued.
- Project quota, total quota or the minimum-free-disk guard returns 507 before a Generation/Item/Attempt is inserted and records zero Provider calls.
- The capacity estimate reserves the peak Provider temp/background plus authoritative composed output for every requested Item; active reservations are included so concurrent projects cannot overbook capacity.
- Cross-project SKU, asset, board, node or composition group references are rejected.
- SKU group layout hash is revalidated.
- Generated task snapshots SKU name, provider/model versions, prompt, layout, dimensions and input SHA values.

- [ ] **Step 2: Implement canonical fingerprints**

```python
def compute_generation_fingerprint(*, project_revision: int,
                                   items: Sequence[GenerationItemSnapshot]) -> str: ...
def estimate_generation_storage_reservation(
    items: Sequence[GenerationItemSnapshot], *,
    remote_image_max_bytes: int,
) -> int: ...
```

Fingerprint sorted canonical JSON containing project revision, Provider/Model config versions, prompts, output specs, layout snapshot, composition group/hash and every input asset SHA-256. The storage estimate includes the temporary peak where the bounded `.verified` Provider result and its full background copy coexist until commit, plus conservative encoded-RGBA upper bounds for the composed image and separate 2,048px background/composed proxies of each Item; never use an average compression ratio.

- [ ] **Step 3: Implement creation in one transaction**

```python
def create_generation(db: Session, *, project_id: str,
                      request: CanvasGenerationCreate,
                      idempotency_key: str) -> tuple[CanvasGeneration, bool]: ...
def get_generation_detail(db: Session, *, generation_id: str) -> GenerationDetail: ...
def list_board_result_versions(db: Session, *, project_id: str,
                               board_id: str | None,
                               cursor: str | None,
                               limit: int) -> ResultVersionPage: ...
```

Create one Item/Attempt per output image. Quantity is expanded to individual Items so progress, retry and result versions remain per-image.

The same SQLite write transaction serializes the quota decision, sums containment-scanned project/total files (including `tmp/`) plus every non-terminal Generation's remaining reservation, checks `CANVAS_PROJECT_QUOTA_BYTES`, `CANVAS_TOTAL_QUOTA_BYTES` and `CANVAS_MIN_FREE_BYTES`, and inserts the new Generation with its reservation. A same-key/same-fingerprint replay returns the existing Generation without reserving again. As temp/background/composed bytes are atomically created, storage helpers debit only newly allocated bytes from the reservation; a rename does not double-debit. Terminal/cancelled work releases unused reservation. If actual bytes would exceed the estimate, extend the reservation under the same checks before writing or fail locally without corrupting an existing asset.

- [ ] **Step 4: Expose thin APIs and run**

Expose:

```text
POST /api/canvas/projects/{project_id}/generations
GET  /api/canvas/generations/{generation_id}
GET  /api/canvas/projects/{project_id}/result-versions?board_id=...&cursor=...&limit=...
```

The paginated read endpoint derives immutable successful versions from Item/Attempt rows and returns version/board/Generation/Item/Attempt IDs, full composed/background asset IDs for server-side selection, browser-safe composed/background preview asset IDs, dimensions, model display/config version and creation time. It is not persisted into project JSON and does not change revision. Limit defaults to 50 and is capped at 100. On reload, `result-board.ts` uses it to restore version lists and resolve the selected composed asset back to its background preview; browser code never requests the full generated/composed content URL.

```powershell
python -m unittest tests.test_canvas_generations.GenerationCreationTests -v
git add services/canvas/generation services/canvas/projects.py routers/canvas/generations.py routers/canvas/projects.py routers/canvas/__init__.py tests/test_canvas_generations.py
git commit -m "feat: create idempotent canvas generations"
```

---

### Task 5: Implement The Attempt State Machine And Leased Worker

**Files:**
- Create: `services/canvas/generation/state.py`
- Create: `services/canvas/generation/worker.py`
- Create: `services/canvas/generation/results.py`
- Modify: `services/canvas/generation/repository.py`
- Modify: `services/canvas/operations.py`
- Modify: `services/canvas/operation_worker.py`
- Modify: `services/canvas/storage.py`
- Modify: `config.py`
- Modify: `.env.example`
- Modify: `main.py`
- Create: `tests/test_canvas_generation_queue.py`

- [ ] **Step 1: Write failing state transition and queue tests**

Assert:

- Only documented Attempt/Generation transitions are legal.
- Only documented Item transitions are legal, including `running -> composing -> succeeded/failed`.
- Two workers cannot claim one Attempt.
- One project cannot run two Generations concurrently.
- Global concurrency defaults to 1.
- `CANVAS_GENERATION_CONCURRENCY` is a bounded server setting with default 1. Raising it still respects Provider and Model profile concurrency limits and the one-active-Generation-per-project rule.
- Claim/lease/heartbeat use short transactions.
- Provider await occurs with no open SQLAlchemy Session.
- An Attempt queued while capacity exists but examined after project/total/free-space capacity becomes unavailable is not claimed for submit; a claim that loses capacity immediately before submit is returned to queued with `storage_capacity_exceeded`, and both cases record zero Provider calls until capacity recovers.
- A stable upstream idempotency key is stored per Attempt and passed only when the Provider capability declares support.
- Idempotency-key lookup runs only when the separate capability and adapter method declare support.
- Synchronous success can go `submitting -> succeeded`; async submit goes `submitting -> polling -> succeeded`.
- Persisting a Provider result plus its separate 2,048px background preview and enqueuing its compose Operation occur in one transaction; completing that Operation creates a new immutable composed result plus composed preview without replacing old assets.
- If the output board was deleted while a task ran, completion keeps the result in Item/Attempt history and does not recreate or mutate the board.
- Aggregation yields succeeded, partially_failed, failed, unknown, cancelled and returns partially_failed to running when a retry is queued.

- [ ] **Step 2: Centralize legal transitions**

```python
def transition_attempt(current: str, target: str) -> None: ...
def transition_item(current: str, target: str) -> None: ...
def aggregate_generation_status(item_statuses: Sequence[str],
                                generation_status: str) -> str: ...
```

No router or adapter may write state strings directly.

- [ ] **Step 3: Implement claim/execute/persist separation**

```python
def claim_next_attempt(db: Session, *, worker_id: str,
                       now: datetime) -> ClaimedAttempt | None: ...
async def execute_claimed_attempt(claim: ClaimedAttempt, *,
                                  registry: ProviderRegistry) -> AttemptExecutionResult: ...
def persist_attempt_result(db: Session, *, claim: ClaimedAttempt,
                           result: AttemptExecutionResult) -> None: ...
```

The immutable claim snapshot contains all request data needed outside the transaction. Heartbeats use a separate short-lived Session. The scheduler counts active leases globally, per Provider, per Model profile and per project before claiming; tests raise the global setting and prove a stricter model/provider limit still wins. Before claim and again in the short pre-submit transaction, call the shared capacity guard against actual project/total usage, all remaining reservations and current free disk. A blocked queued Attempt remains unpaid and discoverable, stores only a safe block reason/time, emits a throttled project event, and becomes eligible automatically after capacity recovers. Never hold the capacity-check Session while awaiting the Provider.

- [ ] **Step 4: Compose successful backgrounds**

Download and atomically persist Provider output as the Item’s full background asset, create a distinct longest-edge 2,048px background preview through the shared slice-2 proxy service, then enqueue a durable `CanvasAssetOperation(operation_type="compose")` with an idempotency key derived from Item/Attempt in the same DB transaction. The local Operation worker calls `compose_to_asset()` with the validated product/layout/text snapshot, links the immutable full composed result and its separate 2,048px preview to the Attempt/Item, marks the Item terminal and emits events carrying the operation, generation and item subject IDs. It does not mutate project semantic state or silently select that result. Models never become a layer above the product. Only the full background/composed assets are inputs to authoritative server compose/export; Fabric receives proxy IDs/`content?variant=preview` only.

Recovery boundaries are explicit:

- A synchronous call that crashes after possible upstream acceptance but before a background asset commit remains `submitting` and becomes `unknown`; it is never automatically resubmitted.
- A saved `external_task_id` resumes polling only.
- Provider bytes or a downloaded URL result are streamed to `tmp/provider-results/{attempt_id}.partial`, with the shared hard `CANVAS_REMOTE_IMAGE_MAX_BYTES=26214400` cap applied to streamed and decoded single-image bytes, validated, fsynced and atomically renamed to `{attempt_id}.verified` without a DB Session. Both partial and verified temp bytes count toward project/total usage. The `.verified` file is the recovery source of truth and remains untouched while deterministic background and background-preview candidate files are copied/derived and fsynced. A short transaction atomically promotes those candidates, inserts both Asset rows, debits the reservation and enqueues the compose Operation. Only after that DB commit succeeds may cleanup remove `.verified`; DB/preview/commit failure cleans containment-verified candidates/finals but preserves `.verified`. A crash before commit leaves deterministic candidates plus `.verified`, and recovery reconciles/cleans the candidates then repeats local promotion; a crash after commit sees the Asset/Operation rows and only removes the redundant `.verified`. Tests inject preview creation failure and DB commit failure, restart, and prove local recovery produces the same background/preview/compose chain with zero Provider calls.
- A synchronous URL response that crashes/times out before a verified temp or background exists has no safely persisted locator and becomes `unknown`; retry requires explicit confirmation of a new paid Attempt.
- An asynchronous task with `external_task_id` that fails result download returns to bounded polling/download and never resubmits.
- A committed background plus queued/running compose Operation resumes local composition only.
- A succeeded compose Operation is never rerun merely because the generation worker restarts.
- Temp cleanup consults Attempt stage/ID and never removes an active or recoverable `.verified` result; stale `.partial` files with no active Attempt follow the 24-hour containment cleanup rule.

- [ ] **Step 5: Register lifecycle and run**

Register the generation-compose handler with the existing local Operation worker. Start Generation recovery then the Generation worker during FastAPI lifespan; on shutdown stop claiming and persist the current known stage.

```powershell
python -m unittest tests.test_canvas_generation_queue -v
git add services/canvas/generation services/canvas/operations.py services/canvas/operation_worker.py services/canvas/storage.py config.py .env.example main.py tests/test_canvas_generation_queue.py
git commit -m "feat: run leased canvas generation queue"
```

---

### Task 6: Handle Cancellation, Retry, Unknown, And Restart Recovery

**Files:**
- Create: `services/canvas/generation/recovery.py`
- Modify: `services/canvas/generation/repository.py`
- Modify: `services/canvas/generation/worker.py`
- Modify: `routers/canvas/generations.py`
- Create: `tests/test_canvas_generation_recovery.py`

- [ ] **Step 1: Encode the recovery matrix as failing tests**

```text
queued, never submitted              -> queued
polling with external_task_id        -> resume polling only
submitting with uncertain acceptance -> unknown
submitting + provider lookup by key  -> recover by same key, never new submit
succeeded Provider Attempt           -> unchanged
verified result temp, no DB asset     -> persist background locally, no submit
committed background + expired compose lease -> reclaim compose Operation only
```

Also test cancelled queued Items, cancel-capable upstream, non-cancellable upstream warning, successful Items preserved during cancellation, explicit unknown resolution, and the distinction between an upstream failure and a local compose failure. Include `partially_failed -> unused reservation released -> disk/quota filled -> retry`: paid retry and compose-only retry both return 507 without creating/requeueing work and the Fake Provider records zero calls; after capacity is restored, each atomically restores only the peak reservation required by its missing stages. A restart integration test runs two sequential FastAPI lifespans/workers against the same temporary SQLite/data directory: the first leaves an async Attempt in polling, the second resumes polling by saved external task ID, and the Fake Provider records zero duplicate submits.

- [ ] **Step 2: Implement recovery and user actions**

```python
def recover_canvas_generation_work(db: Session, *, now: datetime) -> RecoverySummary: ...
def request_generation_cancel(db: Session, *, generation_id: str) -> CanvasGeneration: ...
def retry_generation_item(db: Session, *, item_id: str) -> ItemRetryResult: ...
def resolve_unknown_item(db: Session, *, item_id: str,
                         action: Literal["abandon", "retry"]) -> CanvasGenerationAttempt | None: ...
```

For an upstream failure, retry creates `attempt_no + 1` and never mutates prior attempts. A verified temp/background/download or compose failure retries only the corresponding local stage. If a background asset is already committed and only the compose Operation failed, retry requeues/creates an idempotent local compose Operation and does not call the Provider again. An unresolved synchronous post-acceptance `unknown` creates a new paid Attempt only after explicit user confirmation. Without upstream idempotency lookup/query support, automatic re-submit is forbidden. Extend the project activity guard so every non-terminal Generation and every unresolved `unknown` Item blocks archive/permanent delete.

Terminal aggregation releases unused reservation, so `retry_generation_item()` and `resolve_unknown_item(action="retry")` must first recompute the peak bytes still missing from the saved stage: full Provider temp/background plus both proxies and compose output for a new paid Attempt; only background/proxy persistence for a verified temp; only composed full/proxy bytes for compose retry. In the same serialized transaction, rerun project/total/min-free checks, restore `storage_reservation_remaining_bytes`, clear the safe storage block and only then create the new Attempt or requeue the local Operation. Capacity failure returns 507 and leaves Generation/Item/Attempt/Operation state unchanged. Idempotent duplicate retry requests reuse the restored reservation rather than adding it twice.

- [ ] **Step 3: Expose protected endpoints**

```text
POST /api/canvas/generations/{generation_id}/cancel
POST /api/canvas/generation-items/{item_id}/retry
POST /api/canvas/generation-items/{item_id}/resolve-unknown
```

Apply `require_canvas_paid_access` and return clear “供应商可能继续执行/计费” warnings where cancellation is not supported. Cancel a queued compose Operation locally; if composition is already running, allow its deterministic result to finish and preserve it. For an already submitted asynchronous task that cannot be cancelled, mark the local cancellation request but keep low-frequency polling until the upstream terminal state, persist any final result/fee status, and never delete earlier successes.

- [ ] **Step 4: Run and commit**

```powershell
python -m unittest tests.test_canvas_generation_recovery -v
git add services/canvas/generation/recovery.py services/canvas/generation/repository.py services/canvas/generation/worker.py routers/canvas/generations.py tests/test_canvas_generation_recovery.py
git commit -m "feat: recover and retry canvas generations safely"
```

---

### Task 7: Extend Persisted Events For Generation Progress

**Files:**
- Modify: `services/canvas/events.py`
- Modify: `routers/canvas/events.py`
- Modify: `main.py`
- Create: `tests/test_canvas_generation_events.py`

- [ ] **Step 1: Write failing replay/filter tests**

Cover item/attempt/generation status events, project filtering, Generation-only filtering, `Last-Event-ID` replay, heartbeat, disconnect, an initial project snapshot when `Last-Event-ID` is absent, and a snapshot fallback when requested events have been pruned. The initial snapshot test starts with no browser-held Generation ID and still discovers active and unresolved-unknown work. A concurrency-hook test commits a new event between high-water capture and snapshot serialization and proves it appears either in the consistent snapshot or as an `id > high_water` delta, never in neither. A lifespan integration test seeds more than one bounded prune batch, starts the app, and proves startup uses independent Sessions/batches without holding the generation worker startup transaction or deleting in-retention events.

- [ ] **Step 2: Implement safe snapshots and retention**

```python
def generation_snapshot(db: Session, *, project_id: str,
                        generation_id: str | None = None) -> dict: ...
def project_activity_snapshot(db: Session, *, project_id: str) -> dict: ...
def prepare_event_replay(db: Session, *, project_id: str,
                         last_event_id: int | None,
                         generation_id: str | None = None) -> CanvasEventReplay: ...
def prune_canvas_events(db: Session, *, project_id: str,
                        now: datetime, keep_count: int = 10_000,
                        keep_days: int = 7) -> int: ...
```

`prune_canvas_events()` deletes only rows that are both outside the newest 10,000 for that project and older than seven days; IDs are never renumbered. Run bounded prune batches at startup and from a separate maintenance Session after every 100th appended event, never inside the business-state transaction. Tests verify the set union, stable IDs, bounded batches and replay-gap fallback. On every fresh project stream with no `Last-Event-ID`, and whenever replay has a gap, open one read transaction, read the project event `MAX(id)` first to establish the SQLite snapshot, then query `project_activity_snapshot()` in that same transaction, send the snapshot with that high-water ID, and resume only with events `id > high_water`. Never query high-water after building the activity snapshot. The snapshot includes current local Operations (including compose/export), every non-terminal Generation, every unresolved-unknown Item, and at most the newest 100 terminal Generations updated within 24 hours with their Items/latest Attempts. This covers the 30-minute client intent TTL so a response-lost/reloaded client can recover the task ID and resolve `unknown`; the Generation endpoint filters the same snapshot to its task. Business state and its event append commit in one transaction, so the high-water/state cut is coherent. Payloads contain IDs, progress, statuses and safe error summaries only.

- [ ] **Step 3: Expose the filtered endpoint**

Add `GET /api/canvas/generations/{generation_id}/events` as a filtered view of the same event source; do not create a second in-memory event system.

- [ ] **Step 4: Run and commit**

```powershell
python -m unittest tests.test_canvas_generation_events -v
git add services/canvas/events.py routers/canvas/events.py main.py tests/test_canvas_generation_events.py
git commit -m "feat: stream canvas generation progress"
```

---

### Task 8: Build Complete-Set Generation Controls

**Files:**
- Create: `frontend/canvas/src/domain/providers.ts`
- Create: `frontend/canvas/src/domain/generation.ts`
- Create: `frontend/canvas/src/domain/generation.test.ts`
- Create: `frontend/canvas/src/controllers/generation-controller.ts`
- Create: `frontend/canvas/src/controllers/generation-controller.test.ts`
- Create: `frontend/canvas/src/api/providers.ts`
- Create: `frontend/canvas/src/api/generations.ts`
- Create: `frontend/canvas/src/components/complete-set-panel.ts`
- Create: `frontend/canvas/src/components/model-selector.ts`
- Create: `frontend/canvas/src/components/generation-status.ts`
- Create: `frontend/canvas/src/components/access-dialog.ts`
- Modify: `frontend/canvas/src/state/project-store.ts`
- Modify: `frontend/canvas/src/components/workspace.ts`

- [ ] **Step 1: Write failing validation/projection tests**

Assert:

- Main/SKU/detail buttons all start unselected.
- Selecting a type reveals count, ratio/size, prompt, model and reference controls.
- Generate stays disabled with exact reasons until every selected output is valid.
- Each selected type may use a different model.
- The shared `domain/providers.ts` mirrors the complete backend capability contract; later third-party adapters extend catalog data without defining another `ModelProfile` type.
- “应用同一模型到全部已选类型” only runs on explicit click and does not overwrite before confirmation.
- Actual Item count is displayed; price estimate only appears when the profile supplies price metadata.
- SKU items include the same group hash but may use different background prompts/models.
- Main/detail quantity N maps one-to-one to N stable boards and N Items. SKU quantity is stored per SKU and maps each `(skuId, ordinal)` to a distinct board/Item; actual total is the sum and must remain within 50.
- Clicking Generate immediately after an edit calls `AutoSaveController.flush()` before creating any paid request. A failed/offline/conflict flush creates no Generation; a successful flush adopts the returned revision, rebuilds validation/request/fingerprint inputs, then allocates the client idempotency key and submits.
- Concurrent double-clicks produce one logical submit. If the server succeeds but the response is lost, or a network/5xx/401/503 retry is needed, the same canonical fingerprint reuses the exact same client `Idempotency-Key`; tests prove one Generation and one eventual upstream call. Editing any fingerprint input or choosing explicit “新建一次生成” retires that pending key and allocates a new one.

- [ ] **Step 2: Build typed request projection**

```ts
export function buildGenerationRequest(
  project: ProjectState,
  catalog: ModelProfile[],
): { ok: true; request: CanvasGenerationCreate }
 | { ok: false; reasons: ValidationReason[] };
```

```ts
type PendingSubmission = {
  projectId: string;
  fingerprint: string;
  idempotencyKey: string;
  createdAt: string;
};
```

Every generated Item binds one unique output node/board, output type, optional SKU, dimensions, model version, prompt, product asset, composition layout/hash and text snapshot. A count of 3 can never create three Items sharing one board.
`api/generations.ts` also pages the project result-version endpoint by board and hydrates selected composed-to-background provenance after refresh.

- [ ] **Step 3: Implement access and progress UX**

The generation controller depends on the existing `AutoSaveController` rather than racing its one-second debounce. After flush it computes the canonical fingerprint, creates one `PendingSubmission`, disables concurrent submission, and passes its key explicitly into `api/generations.ts`. Persist a per-project map containing only `{projectId,fingerprint,idempotencyKey,createdAt}` in per-tab `sessionStorage` with a 30-minute TTL; do not persist the request body or access token. A timeout, lost response, 5xx, 401 or 503 keeps this pending key. On retry/reload, first reconcile the fresh project activity snapshot: adopt and clear if the Generation already exists; otherwise rebuild from saved project state, flush, and only when the canonical fingerprint still matches repeat POST with the same key. If the first POST transaction commits just after the snapshot, the same-key concurrent backend path still returns that single Generation. A successful existing/new response clears the pending entry only after its ID is adopted. Project switching and “停止本地等待” retain that project's intent; returning later reconciles it. TTL expiry first performs reconciliation before clearing. A fingerprint-changing edit retires only that project's mismatched intent, while explicit “新建一次生成” clears it only after confirmation that an earlier request may already be running/charged. Unlock submits the raw token only to `/unlock`; on 401/503 retain the unsubmitted Generation configuration and reopen the dialog, then re-check/flush revision before retrying submission. SSE initial snapshots and updates recover task IDs, cancellation warnings, per-image failure/retry and unknown actions. On non-loopback HTTP, show that the token only protects paid operations, project data is not user-isolated, and an HTTPS reverse proxy is recommended on a trusted LAN.

- [ ] **Step 4: Run frontend gate**

```powershell
npm.cmd run typecheck:canvas
npm.cmd run test:canvas -- frontend/canvas/src/domain/generation.test.ts
npm.cmd run build:canvas
```

Expected: pass.

- [ ] **Step 5: Commit complete-set generation controls**

```powershell
git add frontend/canvas/src/domain/providers.ts frontend/canvas/src/domain/generation.ts frontend/canvas/src/domain/generation.test.ts frontend/canvas/src/controllers/generation-controller.ts frontend/canvas/src/controllers/generation-controller.test.ts frontend/canvas/src/api/providers.ts frontend/canvas/src/api/generations.ts frontend/canvas/src/components/complete-set-panel.ts frontend/canvas/src/components/model-selector.ts frontend/canvas/src/components/generation-status.ts frontend/canvas/src/components/access-dialog.ts frontend/canvas/src/state/project-store.ts frontend/canvas/src/components/workspace.ts static/canvas/canvas.js static/canvas/canvas.css
git commit -m "feat: add complete-set image generation controls"
```

---

### Task 9: Complete The Predefined Advanced Node Flow And Result Versions

**Files:**
- Create: `frontend/canvas/src/domain/node-ports.ts`
- Create: `frontend/canvas/src/domain/node-ports.test.ts`
- Create: `frontend/canvas/src/components/node-toolbar.ts`
- Create: `frontend/canvas/src/components/node-inspector.ts`
- Create: `frontend/canvas/src/components/result-board.ts`
- Modify: `frontend/canvas/src/canvas/canvas-adapter.ts`
- Modify: `frontend/canvas/src/state/project-store.ts`

- [ ] **Step 1: Write typed-port and graph validation tests**

Only allow the predefined nodes and ports:

```text
product_asset, cutout_asset, prompt, background_image,
composition, text_layer, output_image
```

Reject incompatible connections, missing required inputs, unsupported model capabilities, invalid sizes, a SKU with neither its own reference nor a valid main-product fallback, and unconnected output. A SKU without its own image is valid when it explicitly reuses the main locked product; the SKU name remains metadata/text and cannot invent different packaging. The automatic-cutout projection remains read-only and cannot be deleted/disconnected to bypass processing.

- [ ] **Step 2: Implement graph-to-Generation projection**

Advanced mode builds the same `CanvasGenerationCreate` type as complete-set mode. If a topology cannot be expressed by the form, set advanced-customized; switching modes never deletes nodes/results or resets prompts/models.

- [ ] **Step 3: Implement stable board result versions**

Each board has stable ID, output node, output type, SKU ID, order and selected result asset ID. Available versions are derived from immutable successful Item/Attempt results for that board, while only the user’s current selection is stored in project semantic state. A successful retry adds a version without overwriting prior assets; selecting preview/export version saves project state and increments project revision. Removing a version from a board only removes its project reference.

For live editing, `result-board.ts` resolves the selected composed result to its saved background preview and projects that proxy plus the current locked product proxy and current text layers. It may use the composed preview for a non-editing version thumbnail, but never loads a full generated/composed asset into Fabric and never displays a text-baked composed bitmap underneath the same editable text layers, so text is not doubled. Editing text/layout does not call the Provider; the later export Operation resolves the full background asset server-side and recomposes it with the current project snapshot.

- [ ] **Step 4: Run and commit**

```powershell
npm.cmd run typecheck:canvas
npm.cmd run test:canvas
npm.cmd run build:canvas
git add frontend/canvas/src static/canvas/canvas.js static/canvas/canvas.css
git commit -m "feat: add canvas generation controls and nodes"
```

---

### Task 10: Verify Seedream Workflow With A Fake Provider

**Files:**
- Create: `tests/fakes/canvas_provider.py`
- Modify: `services/canvas/runtime.py`
- Modify: `scripts/e2e_server.py`
- Create: `e2e/canvas-generation.spec.js`
- Rebuild: `static/canvas/canvas.js`
- Rebuild: `static/canvas/canvas.css`

- [ ] **Step 1: Add a deterministic test Provider**

Extend `configure_canvas_test_runtime(app, provider_registry_factory=..., model_profile_seed_factory=...)` on the existing pre-lifespan `app.state` seam. `scripts/e2e_server.py` injects the deterministic Fake Provider registry and an idempotent isolated-DB seeder for at least two test-only profiles (“Fake Sync” and “Fake Async”) after importing `main.app` and before Uvicorn starts. They exercise different per-output selections and capabilities and can produce sync success, async polling, partial failure, delay, cancellation and uncertain submission. The seam refuses post-start mutation; production bindings have no test seeder and never create/select a fake from environment or user input.

- [ ] **Step 2: Add browser flows**

Cover:

- No output/model means Generate is disabled.
- Select main, SKU and detail with different models/specs and verify actual count.
- Configure quantity 3 for one output, verify three stable boards/Items survive refresh, and later export selection can include all three instead of treating them as one board’s versions.
- Same SKU group retains composition while generated backgrounds differ.
- Complete-set/advanced round trip preserves request.
- Progress, cancel, partial failure, single Item retry and unknown abandon/retry.
- Browser refresh reconnects to persisted polling/results without duplicate submit; actual process-restart recovery is covered by the sequential-lifespan integration test in Task 6, not faked inside Playwright’s single webServer.
- Retry adds an immutable result version and the selected current preview version survives reload.
- Reload pages the board result-version API, restores the full version list and resolves every selected composed asset to the correct background.
- Browser network assertions prove every Fabric/thumbnail image request uses a preview asset or `content?variant=preview`; no full generated-background or composed-asset content URL is requested, including quantity-3 and refresh flows.
- Access token 503/401/unlock/lock behavior.
- Edit count/prompt/layout and click Generate without waiting one second; the browser proves save completes first and the paid endpoint sees the returned revision exactly once.
- Double-click Generate, and separately inject “server committed POST but client response was dropped”; after reload the initial project snapshot discovers the same Generation ID, retry reuses the key, unresolved `unknown` remains actionable, and the Fake Provider records exactly one upstream submit.
- Pause the first POST immediately before its insert, reload so the initial snapshot contains no Generation yet, then release the first transaction and retry from the 30-minute `sessionStorage` intent; the same key converges to one Generation and one upstream submit.
- Fill project/total quota or force free disk below `CANVAS_MIN_FREE_BYTES` before creation and after queueing; both paths show a safe capacity message and the Fake Provider records zero submits until capacity is restored.

- [ ] **Step 3: Run the slice gate**

```powershell
python -m unittest tests.test_canvas_generation_models tests.test_canvas_access tests.test_canvas_seedream_provider tests.test_canvas_generations tests.test_canvas_generation_queue tests.test_canvas_generation_recovery tests.test_canvas_generation_events -v
python -m unittest discover -s tests -v
python -m compileall -q canvas_models.py routers services tests
npm.cmd run typecheck:canvas
npm.cmd run test:canvas
npm.cmd run build:canvas
npm.cmd run test:e2e -- e2e/canvas-generation.spec.js
git diff --check
```

Expected: all tests pass and no request reaches Volcengine.

- [ ] **Step 4: Commit acceptance coverage**

```powershell
git add tests/fakes/canvas_provider.py services/canvas/runtime.py scripts/e2e_server.py e2e/canvas-generation.spec.js static/canvas/canvas.js static/canvas/canvas.css
git commit -m "test: verify durable canvas generation"
```

### Slice 3 Acceptance

- UI 和任务快照均使用 Seedream 5.0 完整版精确 ID，自动测试证明 Lite ID 不会进入内置配置。
- 用户自己选择输出类型、数量、比例、提示词和模型；没有任何默认输出。
- 模型只产背景/场景，产品包装、Logo、标签文字、颜色和外形由服务端锁定合成保真。
- 同组 SKU 只有构图被锁定；背景和模型可以不同。
- 逐图进度、版本、取消、部分失败、重试、unknown 和重启恢复均有持久化证据。
- 所有付费操作受 Canvas 访问会话保护；自动测试零付费调用。
