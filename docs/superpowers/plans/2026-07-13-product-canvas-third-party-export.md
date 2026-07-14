# Product Canvas Third-Party Providers And Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Seedream 生成闭环之上加入可安全配置的 OpenAI Images-compatible 与声明式第三方 HTTP 图片模型，完成凭据加密、模型管理、SSRF 防护、能力驱动交互，以及单图、ZIP、详情切片和详情长图导出。

**Architecture:** 所有模型继续经过统一 Provider Registry 和持久 Generation/Attempt 状态机。第三方连接保存版本化非密钥配置，凭据使用数据库外主密钥进行 Fernet 加密。所有出站流量走验证 DNS、固定目标 IP、保留 TLS SNI 的安全客户端；远程图片先下载为同源资产。导出是持久化本地 Operation，服务端按用户选中的结果版本权威生成。

**Tech Stack:** FastAPI, SQLAlchemy, cryptography/Fernet 49.0.0, httpx 0.27.2, httpcore 1.0.9, Pillow, ZIP, TypeScript, Vitest, Playwright.

## Global Constraints

- 先验收前三个切片；本计划只实现交付切片 4。
- 本阶段支持第三方 API，不实现 ComfyUI、不加载任意本地权重、不执行用户脚本或自定义 Python。
- 只支持三类已审计适配器：Seedream、OpenAI Images-compatible、声明式 HTTP JSON/Multipart；特殊协议需新增代码适配器。
- 通用映射只允许固定变量与受限字段路径；禁止 Jinja、表达式、`eval`、脚本、任意模板代码和动态绝对 URL。
- Provider/Model 配置是全局目录，项目只引用 ID 和配置版本；历史任务保存无密钥快照。
- UI/响应/日志/事件/项目状态/任务快照/导出永远不返回明文凭据。
- 不复用 `AIInterfaceSetting.api_key_secret` 或其他现有明文字段；图片 Provider 使用独立密文列。
- Provider 提交零重定向；远程结果最多两次重定向，每一跳重新验证且不携带 Provider 鉴权。
- 默认拒绝回环、私网、链路本地、保留和云元数据地址；元数据地址在任何配置下都拒绝。
- 第三方模型仍只生成背景或受保护区域；最终锁定产品层和文字由服务端 compositor 合成。
- 浏览器只能加载同源 `/api/canvas/assets/{id}/content`，不接触第三方临时 URL。
- 自动测试全部使用本地假 Transport/Provider；真实付费冒烟必须由用户明确授权并设置独立开关。
- 每项 TDD、独立提交，只暂存列出的文件。

---

### Task 1: Add Encryption And Provider-Network Configuration

**Files:**
- Modify: `requirements.txt`
- Modify: `config.py`
- Modify: `.env.example`
- Create: `tests/test_canvas_provider_config.py`

- [ ] **Step 1: Write failing configuration tests**

Validate:

```text
CANVAS_PROVIDER_SECRET_KEY
CANVAS_PROVIDER_ALLOWED_HOSTS
CANVAS_PROVIDER_PRIVATE_ALLOWED_HOSTS
CANVAS_PROVIDER_PRIVATE_ALLOWED_IPS
CANVAS_ALLOW_INSECURE_PROVIDER_HTTP=0
CANVAS_PROVIDER_CONNECT_TIMEOUT_SECONDS
CANVAS_PROVIDER_TOTAL_TIMEOUT_SECONDS
CANVAS_PROVIDER_MAX_JSON_BYTES
CANVAS_REMOTE_IMAGE_MAX_BYTES=26214400
```

Exact host allowlists are administrator configuration, never user-controlled Provider fields. Environment parsing rejects wildcards, schemes, paths and invalid IP entries; CIDR ranges are not accepted where the policy requires an exact IP.
`CANVAS_REMOTE_IMAGE_MAX_BYTES` already exists from the Seedream slice; this task verifies and reuses that same default while extending the surrounding third-party network settings. It must not introduce a second remote-image limit or change the 25 MB default.

- [ ] **Step 2: Pin security runtime**

Add:

```text
cryptography==49.0.0
```

Keep the existing pinned `httpx==0.27.2` and the `httpcore==1.0.9` baseline introduced with Seedream.

- [ ] **Step 3: Run and commit**

```powershell
python -m unittest tests.test_canvas_provider_config -v
git add requirements.txt config.py .env.example tests/test_canvas_provider_config.py
git commit -m "build: add secure canvas provider runtime"
```

---

### Task 2: Encrypt Credentials And Expose Versioned Provider Management

**Files:**
- Modify: `canvas_models.py`
- Modify: `database.py`
- Create: `services/canvas/credentials.py`
- Modify: `services/canvas/provider_catalog.py`
- Modify: `services/canvas/provider_schemas.py`
- Modify: `services/canvas/providers/base.py`
- Modify: `routers/canvas/providers.py`
- Modify: `routers/canvas/__init__.py`
- Create: `docs/canvas-backup-and-provider-operations.md`
- Create: `tests/test_canvas_providers.py`

- [ ] **Step 1: Write failing encryption/catalog/API tests**

Cover:

- API-created secret is stored only as `fernet:v1:<token>` and plaintext is absent from DB rows.
- Missing/invalid `CANVAS_PROVIDER_SECRET_KEY` refuses credential saves; no plaintext fallback.
- Read APIs expose `credential_configured` and a safe hint only.
- Update with an omitted credential preserves ciphertext; explicit replace creates new ciphertext.
- Decryption failure soft-disables the Provider and preserves original ciphertext.
- No online master-key rotation endpoint is added in this version. `docs/canvas-backup-and-provider-operations.md` defines one consistent backup window covering the SQLite database, `data/canvas_projects/` and `CANVAS_PROVIDER_SECRET_KEY`; rembg cache is explicitly rebuildable. Its restore checklist verifies containment, sampled asset SHA/path resolution and Provider decryptability before serving paid calls.
- Provider/Model delete means soft disable and historical snapshots remain readable.
- Config version increments on material configuration/capability changes.
- Every create/update/disable/test action requires Canvas paid access.
- Provider create/update schemas cannot name or read arbitrary server environment variables. Environment credential references are server-managed, read-only fields available only to built-in adapters such as Seedream.
- Project/state/event/log serializations contain no test secret.

- [ ] **Step 2: Implement the codec**

```python
class ProviderSecretCodec:
    @classmethod
    def from_env(cls) -> "ProviderSecretCodec": ...
    def encrypt_json(self, secret_fields: dict[str, str]) -> str: ...
    def decrypt_json(self, value: str) -> dict[str, str]: ...
```

Require a valid URL-safe 32-byte Fernet master key outside the DB. Catch `InvalidToken` as a configuration error, never overwrite it.

- [ ] **Step 3: Implement catalog services**

```python
def create_provider(db: Session, *, request: ProviderCreate,
                    codec: ProviderSecretCodec) -> ProviderView: ...
def update_provider(db: Session, *, provider_id: str,
                    request: ProviderUpdate,
                    codec: ProviderSecretCodec) -> ProviderView: ...
def disable_provider(db: Session, *, provider_id: str) -> ProviderView: ...
def create_model_profile(db: Session, *, provider_id: str,
                         request: ModelProfileCreate) -> ModelProfileView: ...
def update_model_profile(db: Session, *, model_profile_id: str,
                         request: ModelProfileUpdate) -> ModelProfileView: ...
```

Extend the one `ModelCapabilities` contract from `services/canvas/providers/base.py` and its matching frontend type; do not create a second capability schema. It explicitly lists text-to-image/image-to-image/mask edit, sizes, ratios, quantity, references, transfer method, sync/async, cancellation, idempotency, concurrency and optional price. A profile that accepts only public reference-image URLs is marked unsupported for local product references; the service never sends localhost/LAN URLs.

- [ ] **Step 4: Expose protected APIs**

```text
GET/POST    /api/canvas/model-providers
PATCH/DELETE /api/canvas/model-providers/{provider_id}
POST         /api/canvas/model-providers/{provider_id}/test
GET/POST     /api/canvas/model-providers/{provider_id}/models
PATCH        /api/canvas/models/{model_profile_id}
```

Connection tests prefer a free metadata/model-list endpoint. If a Provider can only test by generating, require `allow_paid_probe=true` and return quantity/possible-fee confirmation data before submission.

- [ ] **Step 5: Run and commit**

```powershell
python -m unittest tests.test_canvas_providers -v
git add canvas_models.py database.py services/canvas/credentials.py services/canvas/provider_catalog.py services/canvas/provider_schemas.py services/canvas/providers/base.py routers/canvas/providers.py routers/canvas/__init__.py docs/canvas-backup-and-provider-operations.md tests/test_canvas_providers.py
git commit -m "feat: manage encrypted image providers"
```

---

### Task 3: Build A DNS-Pinned SSRF-Safe Transport

**Files:**
- Modify: `services/canvas/provider_network.py`
- Modify: `services/canvas/remote_images.py`
- Create: `tests/test_canvas_provider_security.py`

- [ ] **Step 1: Write the complete security matrix as failing tests**

Test IPv4/IPv6 loopback, RFC1918, link-local, multicast, reserved, unspecified, IPv4-mapped IPv6, decimal/hex IP forms, DNS rebinding, mixed public/private DNS answers, userinfo, fragment, absolute endpoint, wildcard host, malicious redirect, proxy environment leakage and cloud metadata hosts/IPs.

Also assert:

- Default only HTTPS and exact allowed Host.
- Private HTTP needs `CANVAS_ALLOW_INSECURE_PROVIDER_HTTP=1` plus exact private Host and resolved IP allowlists.
- Metadata destinations fail even if explicitly listed.
- Submit requests do not redirect.
- Remote image redirects are at most two, revalidate every hop, and carry no auth/query secret.
- JSON/binary byte caps and content-type/decode checks abort streaming promptly.

- [ ] **Step 2: Validate origins and endpoints**

```python
def validate_provider_base_url(value: str, *,
                               policy: ProviderNetworkPolicy) -> ValidatedOrigin: ...
def validate_relative_endpoint(value: str) -> str: ...
def resolve_pinned_target(origin: ValidatedOrigin, *,
                          resolver: HostResolver,
                          policy: ProviderNetworkPolicy) -> PinnedTarget: ...
```

Normalize IDNA hostnames, reject ambiguous IP encodings and validate every resolved address before choosing one.

- [ ] **Step 3: Pin TCP while retaining Host and SNI**

Implement an `httpcore.AsyncNetworkBackend` that connects `connect_tcp()` to the validated IP while leaving the original Host header and TLS `server_hostname` intact. Build `SafeProviderHttpClient` with `trust_env=False`, no submit redirects, bounded timeouts and redacted request summaries.

- [ ] **Step 4: Implement safe remote image download**

```python
async def download_remote_image(url: str, *,
                                policy: ProviderNetworkPolicy,
                                max_bytes: int = 25 * 1024 * 1024) -> DownloadedImage: ...
```

At every hop resolve/pin again. Accept only supported image MIME and verify magic/full decode. Return a bounded `VerifiedRemoteImage` bytes/controlled-temp DTO only; do not accept a Session or write the DB during network await. The caller persists it in a later short transaction through `persist_derived_image()` and never returns the raw URL to frontend.

- [ ] **Step 5: Run and commit**

```powershell
python -m unittest tests.test_canvas_provider_security -v
git add services/canvas/provider_network.py services/canvas/remote_images.py tests/test_canvas_provider_security.py
git commit -m "feat: harden third-party provider networking"
```

---

### Task 4: Add The OpenAI Images-Compatible Adapter

**Files:**
- Create: `services/canvas/providers/openai_images.py`
- Modify: `services/canvas/providers/registry.py`
- Create: `tests/test_canvas_openai_images_provider.py`

- [ ] **Step 1: Write failing adapter tests**

Cover text-to-image requests, capability-gated references/masks, `b64_json` and URL results, multiple result mismatch, 401/429/timeout/moderation/empty data/invalid JSON/response drift, redaction and disabled profiles.

- [ ] **Step 2: Implement through the safe transport**

Use `SafeProviderHttpClient` rather than the OpenAI SDK so custom origins obey DNS pinning and SSRF rules.

```python
class OpenAIImagesAdapter:
    adapter_type = "openai_images"

    async def submit(self, request: ProviderGenerationRequest,
                     runtime: ProviderRuntime) -> ProviderSubmission: ...
```

For generation, send only declared supported fields such as `model`, `prompt`, `n=1`, `size` and `response_format`. Reference/mask endpoints are used only when the model capability and strict protected-product policy allow them; otherwise generate a background.

- [ ] **Step 3: Normalize and persist results**

Decode Base64 with byte caps or pass URL through `download_remote_image()`. Map upstream errors to stable codes with safe summary and retryability; raw bodies and secrets do not enter DB/events.

- [ ] **Step 4: Run and commit**

```powershell
python -m unittest tests.test_canvas_openai_images_provider -v
git add services/canvas/providers/openai_images.py services/canvas/providers/registry.py tests/test_canvas_openai_images_provider.py
git commit -m "feat: add OpenAI-compatible image provider"
```

---

### Task 5: Add Declarative JSON And Multipart HTTP Providers

**Files:**
- Create: `services/canvas/providers/declarative_http.py`
- Modify: `services/canvas/provider_schemas.py`
- Modify: `services/canvas/providers/registry.py`
- Create: `tests/test_canvas_declarative_provider.py`

- [ ] **Step 1: Define and test the safe mapping language**

Only allow these input variables:

```text
model_id, prompt, negative_prompt, quantity, ratio, width, height,
reference_image_bytes, reference_image_base64, mask_bytes, seed
```

Field paths support bounded object keys plus numeric array indexes in canonical forms such as `data.0.url` or `data[0].url`. Keys match `[A-Za-z_][A-Za-z0-9_-]{0,63}`, indexes are 0–99, total depth is at most 12, and prototype/meta keys are rejected. No wildcards, expressions, filters, loops, conditionals or function calls.

- [ ] **Step 2: Implement deterministic request mapping**

```python
def set_declared_path(target: dict, path: str, value: JSONValue) -> None: ...
def get_declared_path(source: JSONValue, path: str) -> JSONValue: ...
def build_declared_request(config: DeclarativeHttpConfig,
                           variables: ProviderVariables) -> DeclaredRequest: ...
```

Support:

- Submit uses POST/PUT only; poll uses GET/POST; cancel uses POST/DELETE.
- JSON or Multipart bodies.
- Bearer, one controlled API-key Header, or one controlled Query key.
- Fixed non-secret headers from an allowlist.
- Sync binary/Base64/URL result.
- Async task ID/status/error/result paths, bounded polling interval and optional cancel endpoint.
- Poll/cancel Endpoint with only `{external_task_id}` as one percent-encoded path-segment substitution. Values containing `..`, slash, query/fragment delimiters or encoded separators cannot rewrite the configured Endpoint.

- [ ] **Step 3: Reject executable or dangerous configuration**

Tests must reject Jinja markers, shell/code strings used as templates, absolute endpoints, CRLF headers, arbitrary Authorization templates, nested external URLs, overdeep paths and fields outside the fixed variable set. Poll/cancel tests include external task IDs containing `../`, `/`, `?`, `#`, `%2f` and double-encoded separators and prove none can alter the endpoint path/query.

- [ ] **Step 4: Test sync/async state integration**

Use FakeTransport for synchronous Base64/URL, asynchronous submit/poll/cancel, rate limits, malformed fields and external task recovery. Confirm existing Attempt worker never re-submits a saved async task.

- [ ] **Step 5: Run and commit**

```powershell
python -m unittest tests.test_canvas_declarative_provider -v
git add services/canvas/providers/declarative_http.py services/canvas/provider_schemas.py services/canvas/providers/registry.py tests/test_canvas_declarative_provider.py
git commit -m "feat: add declarative HTTP image providers"
```

---

### Task 6: Build Capability-Driven Model Management UI

**Files:**
- Modify: `frontend/canvas/src/api/providers.ts`
- Modify: `frontend/canvas/src/domain/providers.ts`
- Create: `frontend/canvas/src/domain/providers.test.ts`
- Create: `frontend/canvas/src/components/model-manager.ts`
- Create: `frontend/canvas/src/components/provider-editor.ts`
- Create: `frontend/canvas/src/components/model-profile-editor.ts`
- Modify: `frontend/canvas/src/components/model-selector.ts`
- Modify: `frontend/canvas/src/components/workspace.ts`

- [ ] **Step 1: Write UI/domain tests**

Assert:

- Seedream, OpenAI-compatible and generic HTTP are interactive choices; none becomes a project output default.
- Disabled models cannot be selected.
- Capabilities disable unsupported reference/mask/size/quantity controls with a reason.
- Different output types/nodes retain their own selected models.
- Credentials are write-only and never rendered from GET responses.
- 401 reopens unlock while preserving the unsaved Provider form and secret only in component memory; 503 explains server token configuration.
- Paid connection probe requires a second explicit confirmation showing count and possible cost.
- ComfyUI and local-weight execution are absent from selectable adapter types.

- [ ] **Step 2: Implement typed clients and forms**

DOM components submit Pydantic-compatible shapes and keep secrets in ephemeral component memory only. On 401/503 or a retryable transport error, retain the secret only until the immediate unlock/retry flow completes and never write it to storage. Clear it on successful save, explicit cancel/navigation, or a non-retryable validation failure; retain non-secret fields for retry.

- [ ] **Step 3: Implement capability-aware selectors**

Model selector consumes enabled profiles/version/capabilities. It never silently changes a model or deletes unsupported user parameters; it reports the conflict and disables Generate until resolved.

- [ ] **Step 4: Run and commit**

```powershell
npm.cmd run typecheck:canvas
npm.cmd run test:canvas -- frontend/canvas/src/domain/providers.test.ts
npm.cmd run build:canvas
git add frontend/canvas/src static/canvas/canvas.js static/canvas/canvas.css
git commit -m "feat: add third-party canvas model manager"
```

---

### Task 7: Implement Persistent Authoritative Exports

**Files:**
- Create: `services/canvas/export_schemas.py`
- Create: `services/canvas/exports.py`
- Modify: `services/canvas/compositor.py`
- Create: `routers/canvas/exports.py`
- Modify: `routers/canvas/__init__.py`
- Modify: `services/canvas/operation_worker.py`
- Modify: `services/canvas/assets.py`
- Create: `tests/test_canvas_exports.py`

- [ ] **Step 1: Write failing export/API tests**

Cover:

- `POST /api/canvas/projects/{project_id}/exports` requires `Idempotency-Key` and creates/reuses an export Operation by request fingerprint.
- Same key/different selected versions/spec returns 409.
- A stale project revision returns 409 before an export Operation or temp file is created.
- Only selected, same-project composed asset versions can export.
- PNG/JPEG/WebP single output, category ZIP, ordered detail slices and ordered long image.
- JPEG uses an explicit validated background color for alpha.
- Detail order follows saved board order snapshot.
- Editing text, product placement or z-band after generation and before export changes the authoritative export; stale text baked into a historical preview asset is never reused.
- Filename cleaning handles Chinese, reserved Windows names, slash/backslash, control chars, duplicates and ZIP traversal.
- Project/total/free-space quotas apply; partial files are cleaned on failure.
- Selected composed assets referenced by any export Operation/request snapshot are reported by `delete_asset()` and cannot be soft-deleted; exported assets remain protected while referenced by a project board or download record.
- `GET /api/canvas/assets/{asset_id}/download` returns a safe attachment filename and `nosniff`.

- [ ] **Step 2: Define export requests**

```python
class CanvasExportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_revision: int
    mode: Literal["single", "category_zip", "detail_slices_zip", "detail_long"]
    format: Literal["png", "jpeg", "webp"]
    selected_boards: list[SelectedBoardVersion]
    jpeg_background: str | None

def enqueue_canvas_export(db: Session, *, project_id: str,
                          request: CanvasExportCreate,
                          idempotency_key: str) -> CanvasAssetOperation: ...
```

At enqueue time, require the current project revision and snapshot the selected board/result IDs plus the current locked product assets, composition layout/hash, text layers, font version, output sizes and stable detail order. Resolve every selected composed result back to its immutable Generation Item/Attempt background asset. Fingerprint includes the background SHA values, current product SHA values, project revision, layout/text/font snapshot, stable order, format and rendering settings.

- [ ] **Step 3: Implement deterministic file builders**

```python
def render_single_export(...) -> bytes: ...
def build_category_zip(...) -> Path: ...
def build_detail_slices_zip(...) -> Path: ...
def build_detail_long_image(...) -> bytes: ...
def safe_export_component(value: str) -> str: ...
```

For every output, call the authoritative compositor again with the selected version’s background plus the export Operation’s current-project product/layout/text snapshot; do not simply transcode the historical composed preview. This preserves text editability until export. Build in project `tmp/`, fsync/atomically promote to `exports/`, then create an `export` asset. File layout follows project/image type/SKU/ordinal and never embeds source paths.
Do not add a system watermark.

- [ ] **Step 4: Process through the local Operation worker**

Exports use the recoverable local queue, not the paid Generation queue. Expired local leases may rerun safely by fingerprint; success never overwrites a different export asset.

- [ ] **Step 5: Run and commit**

```powershell
python -m unittest tests.test_canvas_exports -v
git add services/canvas/export_schemas.py services/canvas/exports.py services/canvas/compositor.py services/canvas/assets.py routers/canvas/exports.py routers/canvas/__init__.py services/canvas/operation_worker.py tests/test_canvas_exports.py
git commit -m "feat: export canvas image deliverables"
```

---

### Task 8: Add Export Selection And Download UI

**Files:**
- Create: `frontend/canvas/src/api/exports.ts`
- Create: `frontend/canvas/src/domain/exports.ts`
- Create: `frontend/canvas/src/domain/exports.test.ts`
- Create: `frontend/canvas/src/components/export-dialog.ts`
- Modify: `frontend/canvas/src/components/result-board.ts`
- Modify: `frontend/canvas/src/components/top-toolbar.ts`
- Modify: `frontend/canvas/src/components/status-bar.ts`

- [ ] **Step 1: Write export projection tests**

Assert explicit version selection, detail drag order, single/category/slices/long modes, actual item count, format validation, JPEG background requirement, duplicate click idempotency and operation progress. Edit a text layer after generation and click Export without waiting for debounce: `AutoSaveController.flush()` must finish first, the request uses the returned project revision/current text snapshot and retains the chosen background version. Offline/conflict/failed flush creates no Export Operation.

- [ ] **Step 2: Implement export dialog**

The dialog shows selected current versions, allows reordering detail boards, keeps text editable in project state and explains that only exported files rasterize text. On submit it flushes project state, adopts the returned revision, rebuilds the export request/fingerprint inputs, then creates the idempotency key and posts; it does not race autosave. It uses server APIs; no Fabric/browser `toDataURL()` is an authoritative export.

- [ ] **Step 3: Wire operation events and downloads**

SSE drives queued/running/failed/succeeded states. Completed downloads use the same-origin asset download URL; a retry uses the Operation retry endpoint.

- [ ] **Step 4: Run and commit**

```powershell
npm.cmd run typecheck:canvas
npm.cmd run test:canvas
npm.cmd run build:canvas
git add frontend/canvas/src static/canvas/canvas.js static/canvas/canvas.css
git commit -m "feat: add canvas export controls"
```

---

### Task 9: Run Security, Provider, Export, And Full Browser Gates

**Files:**
- Create: `e2e/canvas-provider-export.spec.js`
- Create: `scripts/canvas_provider_smoke.py`
- Modify: `scripts/e2e_server.py`
- Modify: `e2e/app.spec.js`
- Rebuild: `static/canvas/canvas.js`
- Rebuild: `static/canvas/canvas.css`

- [ ] **Step 1: Add fake provider browser flows**

Cover:

- Locked/unconfigured access states and unsaved form retention.
- Encrypted Provider CRUD without secret reflection.
- Seedream/OpenAI-compatible/declarative JSON/declarative Multipart model selection.
- Capability errors, sync/async progress and third-party URL persisted as same-origin asset.
- SSRF rejections surface safe messages with no secret.
- Main/SKU/detail results export as PNG/JPEG/WebP, category ZIP, detail slices and long image.
- Selected retry version and detail order are honored after reload.
- A quantity-3 output exports three distinct selected boards/files in the category ZIP.
- Desktop/mobile workspace has no console errors or document overflow.

- [ ] **Step 2: Add a deliberately gated live smoke helper**

`scripts/canvas_provider_smoke.py` exits without network unless `CANVAS_ALLOW_PAID_SMOKE=1` and the operator supplies an existing Provider/Model ID. It generates exactly one image, waits for terminal Item state, exports one result and prints only model ID, safe statuses, counts and local asset IDs.

- [ ] **Step 3: Run focused and full verification**

```powershell
python -m unittest tests.test_canvas_providers tests.test_canvas_provider_config tests.test_canvas_provider_security tests.test_canvas_openai_images_provider tests.test_canvas_declarative_provider tests.test_canvas_exports -v
python -m unittest tests.test_canvas_projects tests.test_canvas_assets tests.test_canvas_generations -v
python -m unittest discover -s tests -v
python -m compileall -q .
npm.cmd run typecheck:canvas
npm.cmd run test:canvas
npm.cmd run build:canvas
npm.cmd run test:e2e
git diff --check
```

Expected: all commands pass; the gated live-smoke script is not invoked by tests.

- [ ] **Step 4: Verify production runtime**

Restart the supervised Uvicorn child, then verify `/healthz`, `/app`, `/app/canvas`, a real project URL, asset/SSE routes and one local export using the browser. Confirm `npm.cmd run build:canvas` leaves all tracked `static/canvas/` bundle/font/license files clean.

- [ ] **Step 5: Commit acceptance coverage**

```powershell
git add e2e/canvas-provider-export.spec.js scripts/canvas_provider_smoke.py scripts/e2e_server.py e2e/app.spec.js static/canvas/canvas.js static/canvas/canvas.css
git commit -m "test: verify canvas providers and exports"
```

- [ ] **Step 6: Run live paid smoke only with explicit authorization**

After the user confirms possible charges and supplies configured credentials, set `CANVAS_ALLOW_PAID_SMOKE=1` and run exactly one Seedream full-model Item plus one chosen third-party Item. Record model ID, terminal status, count and export asset ID without storing prompts, credentials or upstream raw responses.

### Slice 4 Acceptance

- 用户可交互选择 Seedream、OpenAI-compatible 或声明式第三方模型；任何模型都不被强制设为默认。
- 第三方密钥加密落库且不在任何响应、日志、任务或项目状态泄露。
- DNS 重绑定、私网/元数据地址、危险重定向、超限与伪图片响应均有拒绝证据。
- 声明式 JSON/Multipart 支持同步与异步常见协议，但不执行任意代码；ComfyUI 明确不在当前范围。
- 模型输出先落同源资产，产品层仍由服务端严格保真合成。
- 单图、分类 ZIP、详情切片和详情长图均使用用户选择的结果版本和稳定顺序。
- 全套单元、前端、E2E、编译和活体验证门通过；付费冒烟只有明确授权才执行。
