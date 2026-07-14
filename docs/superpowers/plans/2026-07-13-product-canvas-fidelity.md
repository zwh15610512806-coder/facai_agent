# Product Canvas Fidelity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在画布基础之上交付安全图片上传、透明背景确定性检测、所有不透明图自动抠图、严格保留原产品 RGB、SKU 统一构图、可编辑文字和服务端权威合成。

**Architecture:** 原始文件、工作图、预览代理和抠图是显式派生资产；`CanvasAssetOperation` 持久化本地任务、租约和错误。透明图跳过抠图，不透明图自动进入单线程 rembg CPU 队列。rembg 只产生 Alpha 蒙版，服务端合成始终从原始工作资产读取产品 RGB，并按固定层级与归一化布局重建结果。

**Tech Stack:** FastAPI, SQLAlchemy, Pillow 12.3.0, rembg[cpu] 2.0.76, ONNX Runtime 1.27.0, SQLite persistent queue, TypeScript, Fabric.js, Vitest, Playwright.

## Global Constraints

- 先完成并验收 `2026-07-13-product-canvas-foundation.md`；本计划只实现交付切片 2。
- 自动抠图没有启用复选框：已有有效透明背景直接跳过；所有不透明图片（含白底）自动调用 `isnet-general-use`。
- 原图不可变；rembg 的彩色输出不得进入产品层，只允许把其 Alpha 蒙版应用到原始工作图 RGB。
- 包装、Logo、标签文字和外形不允许被模型重绘、修补、调色、滤镜化或生成式填充。
- 新产品角度必须对应用户上传的真实角度素材；系统不允许把模型生成角度标成产品源图。
- Fabric 只加载最长边 2,048px 的同源代理；原图、高分辨率抠图和合成均由服务端处理。
- 产品层只允许等比缩放、平移和确定性旋转；拒绝非等比拉伸、裁切、翻转、skew、滤镜和颜色调整。
- 当前切片不加入手工 Alpha 画笔；误抠通过保留原图、对比、重试和显式矩形回退处理。
- 同组 SKU 只统一构图槽位、锚点、基线、产品占比、安全区、旋转规则和布局哈希；背景、光线、颜色、装饰和模型不强制一致。
- 上传、派生图、合成和删除都执行项目根 containment；API 从不接受服务器路径。
- 所有测试使用程序生成的小图片或确定性 FakeMasker；自动测试不下载 ONNX 模型。
- 每项先写失败测试，提交只包含本计划文件，保留工作区无关改动。

---

### Task 1: Add Image Runtime Dependencies And Canvas Limits

**Files:**
- Modify: `requirements.txt`
- Modify: `config.py`
- Modify: `.env.example`
- Modify: `.gitignore`
- Create: `tests/test_canvas_config.py`

- [ ] **Step 1: Write failing configuration tests**

Assert defaults and stricter environment overrides for:

```text
CANVAS_DATA_DIR=data/canvas_projects
CANVAS_MAX_UPLOAD_BYTES=12582912
CANVAS_MAX_IMAGE_EDGE=16384
CANVAS_MAX_IMAGE_PIXELS=40000000
CANVAS_PREVIEW_MAX_EDGE=2048
CANVAS_PROJECT_QUOTA_BYTES=5368709120
CANVAS_TOTAL_QUOTA_BYTES=21474836480
CANVAS_MIN_FREE_BYTES=2147483648
CANVAS_REMBG_MODEL_DIR=data/models/rembg
CANVAS_REMBG_WORKERS=1
CANVAS_LOCAL_OPERATION_WORKERS=1
```

Run:

```powershell
python -m unittest tests.test_canvas_config -v
```

Expected: missing settings failures.

- [ ] **Step 2: Pin the CPU image stack**

Add exactly:

```text
Pillow==12.3.0
onnxruntime==1.27.0
rembg[cpu]==2.0.76
```

Install:

```powershell
python -m pip install -r requirements.txt
```

Expected: Python 3.12 imports `PIL`, `onnxruntime` and `rembg` successfully.

- [ ] **Step 3: Add data exclusions and documented settings**

Ignore runtime project files, rembg model cache, temporary uploads and exports, while leaving `static/canvas/` build assets tracked.

- [ ] **Step 4: Run and commit**

```powershell
python -m unittest tests.test_canvas_config -v
git add requirements.txt config.py .env.example .gitignore tests/test_canvas_config.py
git commit -m "build: add canvas image processing runtime"
```

---

### Task 2: Persist Asset Operations And Complete Asset Metadata

**Files:**
- Modify: `canvas_models.py`
- Modify: `database.py`
- Create: `tests/test_canvas_assets.py`
- Create: `tests/test_canvas_operations.py`
- Modify: `tests/test_canvas_migrations.py`

- [ ] **Step 1: Write failing schema and migration tests**

Cover:

- `canvas_assets` has project, type, relative path, original filename, MIME, byte count, width, height, SHA-256, source asset, transparency status, processor version, metadata and soft-delete time.
- Allowed asset types are `source`, `working`, `preview`, `cutout`, `generated_background`, `composed` and `export`.
- `canvas_asset_operations` has project, operation type, status, attempt count, lease, heartbeat, next attempt, cancellation, input/output assets, request snapshot, processor version, idempotency key, safe error and timestamps.
- Unique `(project_id, operation_type, idempotency_key)` prevents duplicate local work.
- Required indexes, FK delete behavior, pre-change backup and repeated `init_db()` work.
- The compatibility migration rebuilds `canvas_events` once to attach `operation_id -> canvas_asset_operations.id` with `ON DELETE SET NULL` while preserving event IDs/payloads and the still-unbound generation/item columns.

Run:

```powershell
python -m unittest tests.test_canvas_migrations tests.test_canvas_assets tests.test_canvas_operations -v
```

Expected: missing operation table/fields failures.

- [ ] **Step 2: Add exact model constraints**

```python
OperationType = Literal["cutout", "compose", "export"]
OperationStatus = Literal[
    "queued", "running", "succeeded", "failed",
    "cancel_requested", "cancelled", "interrupted",
]
```

Asset derivation uses direct parent links:

```text
source -> working -> preview
working -> cutout -> preview
working/cutout + background + text -> composed
composed -> export
```

Do not add physical FKs from `canvas_events` to generation tables that do not exist until slice 3. Keep nullable indexed aggregate IDs and validate ownership in `append_canvas_event()`.

- [ ] **Step 3: Update migration detection and run tests**

```powershell
python -m unittest tests.test_canvas_migrations tests.test_canvas_assets tests.test_canvas_operations -v
```

Expected: schema tests pass.

- [ ] **Step 4: Commit**

```powershell
git add canvas_models.py database.py tests/test_canvas_migrations.py tests/test_canvas_assets.py tests/test_canvas_operations.py
git commit -m "feat: persist canvas asset operations"
```

---

### Task 3: Validate And Atomically Persist Image Assets

**Files:**
- Create: `services/canvas/image_validation.py`
- Modify: `services/canvas/storage.py`
- Create: `services/canvas/assets.py`
- Modify: `tests/test_canvas_assets.py`

- [ ] **Step 1: Generate fixtures and write failing validation tests**

Programmatically create valid JPEG/PNG/WebP, fully opaque PNG, corrupt bytes, fake MIME/extension pairs, animated WebP, oversized dimensions and a decompression-bomb case. Assert:

- Only JPG/JPEG, PNG and static WebP are accepted.
- Declared MIME, extension, magic bytes, Pillow format and full decode agree.
- Empty, corrupt, animated, over 12 MB, over 16,384px edge or over 40 MP files are rejected with stable error codes.
- EXIF orientation is applied only to a derived working image; original bytes remain unchanged.

Run:

```powershell
python -m unittest tests.test_canvas_assets.CanvasImageValidationTests -v
```

Expected: import failure.

- [ ] **Step 2: Implement inspection without decompression risk**

Expose:

```python
@dataclass(frozen=True)
class InspectedImage:
    format: Literal["JPEG", "PNG", "WEBP"]
    mime_type: str
    width: int
    height: int
    sha256: str
    has_alpha: bool

def inspect_image(data: bytes, *, filename: str, declared_mime: str) -> InspectedImage: ...
```

Treat `PIL.Image.DecompressionBombError` as rejection, call `verify()` then reopen and fully `load()`, and reject `is_animated`/`n_frames > 1`.

- [ ] **Step 3: Write failing storage tests**

Cover project-root containment, traversal/symlink attempts, quota checks, low disk, `tmp/*.uploading` cleanup, UUID names, SHA, atomic `os.replace()` and DB rollback cleanup.

- [ ] **Step 4: Implement controlled storage**

Expose:

```python
def project_root(project_id: str) -> Path: ...
def resolve_asset_path(asset: CanvasAsset, *, project_id: str) -> Path: ...
def persist_uploaded_source(db: Session, *, project_id: str,
                            filename: str, declared_mime: str,
                            data: bytes) -> UploadedAssetSet: ...
def persist_derived_image(db: Session, *, project_id: str,
                          asset_type: str, data: bytes, mime_type: str,
                          source_asset_id: str | None,
                          metadata: dict) -> CanvasAsset: ...
def canvas_usage_bytes(*, project_id: str | None = None,
                       include_temporary: bool = True) -> int: ...
def assert_canvas_capacity(*, project_id: str, additional_bytes: int,
                           reserved_project_bytes: int = 0,
                           reserved_total_bytes: int = 0) -> None: ...
```

Create `source/`, `working/`, `preview/`, `cutout/`, `generated/`, `composed/`, `exports/` and `tmp/`. Decode the immutable source once, apply EXIF orientation deterministically, convert to the canonical RGB/RGBA working mode without an ICC color transform, and save the working asset as lossless PNG; never re-encode a source JPEG as another JPEG. Write to `.uploading` inside the same filesystem, fsync, then atomically replace. Parent assets must belong to the same project. Capacity accounting scans only containment-validated regular files under project roots, includes `.uploading` and every `tmp/` file, and combines actual bytes with caller-supplied durable reservations before enforcing project/total quotas and minimum remaining disk. Upload rechecks immediately before allocating bytes; later Generation/Export plans reuse these primitives rather than adding inconsistent quota logic.

- [ ] **Step 5: Run storage tests and commit**

```powershell
python -m unittest tests.test_canvas_assets -v
git add services/canvas/image_validation.py services/canvas/storage.py services/canvas/assets.py tests/test_canvas_assets.py
git commit -m "feat: validate and store canvas image assets"
```

---

### Task 4: Detect Effective Transparency And Generate Preview Proxies

**Files:**
- Create: `services/canvas/transparency.py`
- Create: `services/canvas/previews.py`
- Modify: `services/canvas/assets.py`
- Modify: `tests/test_canvas_assets.py`

- [ ] **Step 1: Write exact transparency-vector tests**

Test:

- `alpha <= 250` on an edge-connected region equal to 0.5% returns true.
- `alpha = 251` returns false.
- A region below 0.5%, a central transparent hole, opaque PNG, white JPEG/PNG and complex opaque backgrounds return false.
- Connectivity is deterministic and includes all four edges.

- [ ] **Step 2: Implement the versioned detector**

```python
TRANSPARENCY_PROCESSOR_VERSION = "edge-alpha-v1"

def has_effective_transparent_background(
    image: Image.Image,
    *,
    alpha_threshold: int = 250,
    min_edge_fraction: float = 0.005,
) -> bool: ...
```

Use an iterative 8-neighbor edge flood fill over alpha-qualified pixels and divide unique connected pixels by total pixels. Test diagonal edge connectivity explicitly. “有 Alpha 通道” alone is never sufficient.

- [ ] **Step 3: Test and implement preview proxies**

```python
def create_preview_proxy(db: Session, *, project_id: str,
                         source_asset: CanvasAsset,
                         max_edge: int = 2048) -> CanvasAsset: ...
def resolve_preview_asset(db: Session, *, asset: CanvasAsset) -> CanvasAsset: ...
```

Generate a longest-edge 2,048px same-origin proxy with preserved aspect ratio and alpha; smaller images are not upscaled. Store preview metadata with source asset ID, source dimensions and processor version. The resolver follows an explicit same-project derived-preview relation and never silently falls back to the full working/cutout/generated/composed image when a preview is required. Later generation work reuses the same functions for background and composed proxies.

- [ ] **Step 4: Run and commit**

```powershell
python -m unittest tests.test_canvas_assets.CanvasTransparencyTests tests.test_canvas_assets.CanvasPreviewTests -v
git add services/canvas/transparency.py services/canvas/previews.py services/canvas/assets.py tests/test_canvas_assets.py
git commit -m "feat: detect transparent backgrounds and build previews"
```

---

### Task 5: Expose Upload, Content, Delete, And Operation APIs

**Files:**
- Create: `services/canvas/operations.py`
- Create: `routers/canvas/assets.py`
- Create: `routers/canvas/operations.py`
- Modify: `routers/canvas/__init__.py`
- Modify: `services/canvas/events.py`
- Modify: `services/request_hardening.py`
- Modify: `tests/test_canvas_assets.py`
- Modify: `tests/test_canvas_operations.py`
- Modify: `tests/test_canvas_events.py`
- Modify: `tests/test_request_hardening.py`

- [ ] **Step 1: Write failing API tests**

Cover:

```text
GET/POST /api/canvas/projects/{project_id}/assets
GET      /api/canvas/assets/{asset_id}/content
GET      /api/canvas/assets/{asset_id}/content?variant=preview
DELETE   /api/canvas/assets/{asset_id}
POST     /api/canvas/assets/{asset_id}/cutout/retry
GET      /api/canvas/projects/{project_id}/operations
GET      /api/canvas/operations/{operation_id}
POST     /api/canvas/operations/{operation_id}/retry
```

Assert multipart 14 MB request cap, asset-ID-only access, same-project ownership, `nosniff`, correct MIME, soft delete and reference-safe delete. `variant=preview` resolves an explicit same-project preview relation and returns a stable error if it is absent; it never streams a full-resolution render asset as fallback. The delete service scans SKU reference fields, project semantic/layout Asset IDs, output-board selected results, source/derived relations and active/completed Operations; any reference returns 409 with safe reference kinds.

- [ ] **Step 2: Implement upload transaction behavior**

On upload:

1. Persist immutable source and normalized working image.
2. Detect effective transparency.
3. Create a working preview.
4. If transparent, return with no cutout operation and zero rembg calls.
5. If opaque, atomically enqueue exactly one cutout operation.

Repeated reads, project mode changes and frontend remounts must not enqueue another cutout.
`POST /cutout/retry` requeues a failed operation; when the latest cutout already succeeded it creates a new explicit re-cutout Operation keyed by a client request ID, preserves the previous cutout/preview, and makes a double click idempotent.

Extend the project activity guard so queued/running/cancel-requested local Operations block archive/permanent delete until they reach a safe terminal state.
Extend the replay-gap snapshot with all current project Operations and their safe status/error summaries; later slices add Generations and export Operations to this same snapshot rather than introducing another event source.

- [ ] **Step 3: Implement local operation contracts**

```python
def enqueue_asset_operation(db: Session, *, project_id: str,
                            operation_type: str, input_asset_id: str,
                            idempotency_key: str,
                            request_snapshot: dict) -> CanvasAssetOperation: ...
def claim_next_operation(db: Session, *, worker_id: str,
                         lane: Literal["rembg", "local"],
                         now: datetime) -> ClaimedOperation | None: ...
def retry_asset_operation(db: Session, *, operation_id: str) -> CanvasAssetOperation: ...
```

Emit operation events in the same transaction as status changes.

- [ ] **Step 4: Run and commit**

```powershell
python -m unittest tests.test_canvas_assets tests.test_canvas_operations tests.test_canvas_events tests.test_request_hardening -v
git add services/canvas/operations.py services/canvas/events.py routers/canvas/assets.py routers/canvas/operations.py routers/canvas/__init__.py services/request_hardening.py tests/test_canvas_assets.py tests/test_canvas_operations.py tests/test_canvas_events.py tests/test_request_hardening.py
git commit -m "feat: add canvas asset and operation APIs"
```

---

### Task 6: Run Automatic CPU Cutouts And Recover Local Work

**Files:**
- Create: `services/canvas/rembg_cpu.py`
- Create: `services/canvas/runtime.py`
- Create: `services/canvas/operation_worker.py`
- Modify: `services/canvas/operations.py`
- Modify: `main.py`
- Modify: `tests/test_canvas_assets.py`
- Modify: `tests/test_canvas_operations.py`

- [ ] **Step 1: Write failing cutout and recovery tests**

Assert:

- Effective transparent upload calls rembg zero times.
- White and complex opaque images each call it once.
- Session initializes once with `isnet-general-use` and `CPUExecutionProvider`.
- Only the returned mask is used; every non-transparent output RGB pixel equals the working source RGB at that pixel.
- A successful cutout creates both the full-resolution cutout asset and a separate 2,048px cutout preview; subsequent Fabric projection selects that preview.
- `GET .../content?variant=preview` for the chosen render asset resolves its matching working/cutout preview rather than serving the high-resolution file.
- Failed/model-missing cutout retains original assets and a safe recoverable error.
- Retry creates/requeues controlled work without duplicate successful assets.
- Explicit re-cutout after success creates a new cutout+preview pair and keeps the prior pair available for fallback/history.
- Expired local leases requeue; two workers cannot claim one operation.
- Worker stop stops claiming new jobs and persists current stage.
- rembg uses its own single-thread CPU executor/claim lane and never blocks the FastAPI event loop; compose/export use the separate local Operation lane.
- `configure_canvas_test_runtime(app, masker_factory=...)` may be called only before lifespan starts; production defaults always construct `RembgMasker` and no environment variable can select a fake processor.

- [ ] **Step 2: Implement the mask-only engine**

```python
class RembgMasker:
    def get_session(self): ...
    def create_mask(self, image: Image.Image) -> Image.Image: ...

def apply_alpha_to_source_rgb(source: Image.Image, mask: Image.Image) -> Image.Image: ...
def run_cutout_operation(operation_id: str, *, masker: RembgMasker) -> CanvasAsset: ...
```

Use `new_session("isnet-general-use", providers=["CPUExecutionProvider"])` and `remove(..., only_mask=True, session=session)`. Point `U2NET_HOME` at `CANVAS_REMBG_MODEL_DIR`. Never persist rembg-generated RGB. After persisting the full-resolution cutout, generate a distinct preview derived from that cutout and link both assets.

- [ ] **Step 3: Implement the single-thread worker**

Use short DB transactions to claim/update leases; perform ONNX work outside a Session in a dedicated `ThreadPoolExecutor(max_workers=CANVAS_REMBG_WORKERS)`. `claim_next_operation()` accepts an operation lane so CPU cutouts do not consume the compose/export concurrency lane. `services/canvas/runtime.py` stores typed runtime factories on `app.state` and exposes `configure_canvas_test_runtime()` only as an import-time test seam that refuses changes after startup. Register worker start, recovery, cleanup and stop in FastAPI lifespan. Cleanup removes only containment-verified orphan `.uploading`/`tmp` files older than 24 hours and never referenced assets. A model download/load failure becomes `code="rembg_model_unavailable"`, not a fake transparent result.

- [ ] **Step 4: Implement readiness guard**

```python
def require_compositable_product_asset(
    db: Session, *, project_id: str, source_asset_id: str,
    allow_opaque_fallback: bool = False,
) -> CanvasAsset: ...
```

Default behavior waits/rejects until cutout succeeds. Only an explicit saved `allow_opaque_fallback=true` decision permits using the rectangular working asset.

- [ ] **Step 5: Run and commit**

```powershell
python -m unittest tests.test_canvas_assets tests.test_canvas_operations -v
git add services/canvas/rembg_cpu.py services/canvas/runtime.py services/canvas/operation_worker.py services/canvas/operations.py main.py tests/test_canvas_assets.py tests/test_canvas_operations.py
git commit -m "feat: automate CPU product cutouts safely"
```

---

### Task 7: Build Asset Upload, SKU Reference, And Cutout UI

**Files:**
- Create: `frontend/canvas/src/api/assets.ts`
- Create: `frontend/canvas/src/api/skus.ts`
- Create: `frontend/canvas/src/domain/assets.ts`
- Create: `frontend/canvas/src/domain/assets.test.ts`
- Create: `frontend/canvas/src/components/asset-uploader.ts`
- Create: `frontend/canvas/src/components/asset-inspector.ts`
- Create: `frontend/canvas/src/components/sku-editor.ts`
- Modify: `frontend/canvas/src/api/events.ts`
- Modify: `frontend/canvas/src/components/workspace.ts`
- Modify: `frontend/canvas/src/components/status-bar.ts`

- [ ] **Step 1: Write failing user-flow tests**

Cover:

- File picker and drag/drop accept JPG/PNG/WebP, show client-side size/type feedback, and still treat the server as authoritative.
- Upload progress ends in the returned source/working/preview IDs; project state stores IDs only.
- Fabric receives only `content?variant=preview` URLs and never a source/full cutout URL.
- Transparent assets show ready immediately; opaque assets automatically show queued/running cutout without a checkbox.
- SSE updates the cutout status and swaps to the cutout preview only after success.
- Inspector supports chessboard source/cutout comparison, retry and explicit rectangular-source fallback.
- SKU create/rename/reorder/prompt/reference-asset/delete calls the revisioned SKU API, adopts the returned revision and surfaces 409 without overwriting.
- A SKU without its own reference visibly falls back to the main locked product; its name alone never creates a package image.

- [ ] **Step 2: Implement typed upload and SKU clients**

Use an XHR/fetch upload abstraction that can report progress, abort when switching projects and maps 413/415/422/server errors to safe UI messages. `skus.ts` uses the same conflict result type as project autosave. No component calls `fetch` directly.

- [ ] **Step 3: Implement the user components**

Mount the uploader and SKU editor in the right panel, project assets on the canvas, and cutout/operation summary in the bottom bar. Automatic cutout is a read-only projection derived from server asset state; remounting or mode switching never posts another cutout request.

- [ ] **Step 4: Run and commit**

```powershell
npm.cmd run typecheck:canvas
npm.cmd run test:canvas -- frontend/canvas/src/domain/assets.test.ts
npm.cmd run build:canvas
git add frontend/canvas/src static/canvas/canvas.js static/canvas/canvas.css
git commit -m "feat: add canvas product and SKU asset controls"
```

---

### Task 8: Lock Product Layers And Synchronize SKU Composition

**Files:**
- Create: `services/canvas/composition_schema.py`
- Create: `services/canvas/composition.py`
- Modify: `services/canvas/schemas.py`
- Modify: `services/canvas/project_state.py`
- Create: `tests/test_canvas_composition.py`
- Create: `frontend/canvas/test/fixtures/composition-vectors.json`
- Modify: `frontend/canvas/src/domain/types.ts`
- Modify: `frontend/canvas/src/domain/validation.ts`
- Modify: `frontend/canvas/src/state/project-store.ts`
- Modify: `frontend/canvas/src/canvas/canvas-adapter.ts`
- Create: `frontend/canvas/src/domain/composition.ts`
- Create: `frontend/canvas/src/domain/composition.test.ts`
- Create: `frontend/canvas/src/components/composition-inspector.ts`

- [ ] **Step 1: Define shared canonical layout vectors**

Add one JSON fixture used directly by Python and TypeScript tests for normalized slot, anchor, baseline, relative product fraction, contain rule, safe area, rotation and output ratio. Canonicalize recursively sorted keys and six-decimal floats before SHA-256. Keep the slice-1 camelCase wire schema and schema version; this task tightens validators and does not introduce alternate snake_case fields.

- [ ] **Step 2: Write failing backend/frontend composition tests**

Assert:

- One group update changes all member SKU projections.
- Different aspect ratios map the same normalized group to their boards.
- Different package shapes use contain and are never stretched.
- A mismatched `composition_group_id` or layout hash is rejected.
- Background/model/lighting fields are not part of the group hash.
- SKU without its own reference uses main locked product; its name cannot synthesize a package.
- Adapter rejects nonuniform scale, crop, skew, flip, filter, color changes and product deletion.

- [ ] **Step 3: Implement composition contracts**

```python
def canonical_layout_json(layout: CompositionLayout) -> bytes: ...
def composition_layout_hash(layout: CompositionLayout) -> str: ...
def map_product_to_board(layout: CompositionLayout, *,
                         source_size: tuple[int, int],
                         output_size: tuple[int, int]) -> PixelPlacement: ...
```

Frontend stores immutable `sourceAssetId` and selectable `renderAssetId` separately. SKU product layers reference one `compositionGroupId` rather than copying transforms.

- [ ] **Step 4: Implement the composition inspector**

Expose normalized slot, anchor/baseline, relative product fraction, contain rule, safe area and allowed rotation. Editing one shared group dispatches one Store action and updates every member projection. Background/model/light/color/decoration controls remain outside this inspector and are not synchronized.

- [ ] **Step 5: Run and commit**

```powershell
python -m unittest tests.test_canvas_composition -v
npm.cmd run typecheck:canvas
npm.cmd run test:canvas -- frontend/canvas/src/domain/composition.test.ts
git add services/canvas/composition_schema.py services/canvas/composition.py services/canvas/schemas.py services/canvas/project_state.py tests/test_canvas_composition.py frontend/canvas/src frontend/canvas/test/fixtures/composition-vectors.json
git commit -m "feat: lock product layers and SKU composition"
```

---

### Task 9: Compose Products And Explicit Text Authoritatively

**Files:**
- Create: `services/canvas/text_layout.py`
- Create: `services/canvas/compositor.py`
- Modify: `services/canvas/schemas.py`
- Modify: `services/canvas/project_state.py`
- Modify: `services/canvas/operations.py`
- Modify: `services/canvas/operation_worker.py`
- Create: `tests/test_canvas_compositor.py`
- Modify: `tests/test_canvas_operations.py`
- Create: `frontend/canvas/public/fonts/NotoSansCJKsc-Regular.otf`
- Create: `frontend/canvas/public/fonts/OFL.txt`
- Create: `static/canvas/fonts/NotoSansCJKsc-Regular.otf` (generated from Vite public assets)
- Create: `static/canvas/fonts/OFL.txt` (generated from Vite public assets)
- Modify: `frontend/canvas/src/domain/types.ts`
- Create: `frontend/canvas/src/domain/text-layout.ts`
- Create: `frontend/canvas/src/domain/text-layout.test.ts`
- Create: `frontend/canvas/src/components/text-inspector.ts`
- Modify: `frontend/canvas/src/components/workspace.ts`
- Modify: `frontend/canvas/src/styles.css`

- [ ] **Step 1: Add one shared versioned font resource**

Vendor the OFL-licensed Noto Sans CJK SC Regular OTF under `frontend/canvas/public/fonts/`, retain its license, and derive `fontResourceVersion` from its SHA-256. Vite copies the declared public assets into `static/canvas/fonts/` on every build. Browser and Pillow load that exact built file; do not use a machine font fallback. Build twice and assert source/built font hashes remain equal and the license is not deleted.

- [ ] **Step 2: Write failing text and compositor tests**

Cover:

- Persisted explicit lines, per-line positions, box width, size, letter spacing, line height, alignment, baseline and z-band.
- The text inspector edits content, explicit line breaks/positions, font size, color, alignment, letter/line spacing, baseline and above/below-product z-band through typed Store actions.
- Server never reflows or auto-wraps text.
- Fixed layer order: background/model decoration, below-product text, locked product, above-product user text.
- A model/background layer above product is rejected.
- With identity placement, every visible product RGB pixel exactly matches the working source. Scaled/rotated cases are verified against the fixed deterministic resampling reference; they are not incorrectly asserted byte-identical to untransformed source pixels.
- Same inputs/spec produce the same output SHA.
- Cross-project assets, nonuniform transforms and incorrect group hash fail.

- [ ] **Step 3: Implement explicit text rendering**

```python
def render_text_lines(target: Image.Image, *, layer: TextLayerSnapshot,
                      font_path: Path, expected_font_version: str) -> None: ...
```

Draw each saved line at its saved baseline/position. Validate font digest and reject unsupported metrics instead of silently choosing another font.
Update the existing camelCase project schema validators and property panel; do not create a second text-state shape.

- [ ] **Step 4: Implement authoritative composition**

```python
def compose_image(*, background: Image.Image,
                  products: Sequence[LockedProductLayer],
                  text_layers: Sequence[TextLayerSnapshot],
                  output_size: tuple[int, int]) -> Image.Image: ...
def compose_to_asset(db: Session, *, project_id: str,
                     spec: CompositionSpec,
                     operation_id: str) -> CanvasAsset: ...
```

Use fixed LANCZOS scaling and deterministic rotation settings. Save output through `persist_derived_image()` and record input asset SHA/layout/font versions.
Register `run_compose_operation()` as the only side-effecting compose handler in `operation_worker.py`. API/generation code enqueues a `compose` Operation; it does not invoke `compose_to_asset()` outside the worker. The pure `compose_image()` remains directly unit-testable.

- [ ] **Step 5: Run and commit**

```powershell
python -m unittest tests.test_canvas_compositor tests.test_canvas_operations -v
npm.cmd run typecheck:canvas
npm.cmd run test:canvas
npm.cmd run build:canvas
git add services/canvas/text_layout.py services/canvas/compositor.py services/canvas/schemas.py services/canvas/project_state.py services/canvas/operations.py services/canvas/operation_worker.py tests/test_canvas_compositor.py tests/test_canvas_operations.py frontend/canvas/public/fonts frontend/canvas/src static/canvas/fonts
git commit -m "feat: compose authoritative product images"
```

---

### Task 10: Verify Upload, Cutout, Composition, And Recovery End To End

**Files:**
- Create: `e2e/canvas-fidelity.spec.js`
- Create: `tests/fakes/canvas_processors.py`
- Modify: `scripts/e2e_server.py`
- Modify: `playwright.config.js`
- Rebuild: `static/canvas/canvas.js`
- Rebuild: `static/canvas/canvas.css`

- [ ] **Step 1: Inject test processors only in the isolated E2E app**

`scripts/e2e_server.py` sets up its isolated DB/data first, imports `main.app`, then calls `configure_canvas_test_runtime(main.app, masker_factory=FakeMasker)` before Uvicorn enters lifespan. `FakeMasker` lives in `tests/fakes/canvas_processors.py`. The production default remains real rembg, the seam refuses post-start mutation, and there is no fake-cutout environment switch.

- [ ] **Step 2: Add browser acceptance flows**

Test:

- Transparent PNG uploads with zero cutout operations.
- White and complex opaque products automatically cut out without any checkbox.
- Failed cutout preserves source and exposes retry.
- Source/cutout switching never changes immutable `sourceAssetId`.
- Automatic-cutout node cannot be removed to bypass processing.
- A same-group SKU edit updates all product slots but leaves backgrounds and model selections independent.
- Explicit below/above product text renders in the correct bands.
- Operation SSE resumes with `Last-Event-ID` after disconnect.

- [ ] **Step 3: Run the slice gate**

```powershell
python -m unittest tests.test_canvas_migrations tests.test_canvas_assets tests.test_canvas_operations tests.test_canvas_events tests.test_canvas_composition tests.test_canvas_compositor tests.test_request_hardening -v
python -m unittest discover -s tests -v
python -m compileall -q canvas_models.py routers services tests
npm.cmd run typecheck:canvas
npm.cmd run test:canvas
npm.cmd run build:canvas
npm.cmd run test:e2e -- e2e/canvas-fidelity.spec.js
git diff --check
```

Expected: all commands pass; no ONNX download or external request occurs in automated tests.

- [ ] **Step 4: Rebuild and commit exact production assets**

```powershell
npm.cmd run build:canvas
git add e2e/canvas-fidelity.spec.js tests/fakes/canvas_processors.py scripts/e2e_server.py playwright.config.js static/canvas/canvas.js static/canvas/canvas.css static/canvas/fonts
git commit -m "test: verify canvas product fidelity"
```

### Slice 2 Acceptance

- 透明图零次 rembg；白底和其他不透明图自动调用一次，无启用复选框。
- 抠图只改变 Alpha，原图、工作图、抠图和代理均保留。
- 产品层不可被模型或 Fabric 修改包装、Logo、标签文字、颜色和外形。
- 同组 SKU 构图哈希一致；不同背景、光色、装饰和模型仍可独立。
- 前后端使用同一字体、布局快照、层级和构图哈希；服务端输出是权威成品。
- 失败、重试、租约恢复和 SSE 断线重放均有自动化证据。
