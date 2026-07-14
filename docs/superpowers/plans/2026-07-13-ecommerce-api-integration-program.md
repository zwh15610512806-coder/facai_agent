# Ecommerce API Integration Program Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有法采内网应用右下角增加统一“工具”入口，并交付一个以 PostgreSQL 为唯一数据库、可安全授权多店铺且能持续同步巨量千川、抖店、淘宝和拼多多数据的 API 接入中心。

**Architecture:** 保留 FastAPI/Jinja2/原生 JavaScript 主体，新增 `integrations` 领域包、独立 worker、PostgreSQL 持久任务队列和平台 connector。业务页面与管理 API 仅内网可达，公网仅转发 OAuth 与平台事件回调；平台原始数据在适配器边界脱敏后加密归档，经营数据写入统一规范表。

**Tech Stack:** Python 3.12、FastAPI 0.139、SQLAlchemy 2.0、Alembic 1.18.5、PostgreSQL、psycopg 3.3.4、httpx 0.27、cryptography 49.0、Jinja2、原生 JavaScript、Playwright E2E、`unittest`。

## Global Constraints

- 以已确认的设计规格 `docs/superpowers/specs/2026-07-13-ecommerce-api-integration-center-design.md` 为唯一产品基线；变更安全边界、数据保留期、公开路由或平台状态语义前必须重新确认设计。
- 保留现有非接入页面的内网免登录行为；接入中心管理员会话只能保护 `/app/api-connections*` 与 `/api/integrations*`。
- PostgreSQL 是切换后的唯一业务数据库。生产启动不得 `create_all()` 或运行手写 schema 修补；必须先执行 `alembic upgrade head`。
- 不在源码、日志、测试夹具、数据库明文字段或导出中保存 App Secret、Access Token、Refresh Token、买家姓名、手机号、身份证或详细地址。
- connector 只能访问代码内固定的官方主机；不接受用户输入 Base URL，不自动跟随到非官方主机。
- 四个平台共用内部协议，但 OAuth、签名、分页、限流、错误翻译和能力探测必须分平台实现。
- 公开文档无法验证的当前方法名、路径或 scope，必须先完成对应应用控制台“操作目录”证据文件并通过契约测试；没有证据时平台保持 `setup_required` 或 `permission_limited`。
- 每个任务严格遵循红—绿—重构：先提交失败测试，运行并记录预期失败，再做最小实现，最后运行目标回归。
- 每个计划独立提交；不得把用户现有的无关改动加入提交。
- 所有中文源码与夹具以 UTF-8 读取验证，不以 PowerShell 终端乱码判断文件损坏。

## Canonical File Layout

所有分计划使用下列固定路径，后续执行不得另建平行实现：

```text
alembic.ini
alembic/
  env.py
  script.py.mako
  versions/
integration_models.py
commerce_models.py
integrations/
  __init__.py
  settings.py
  types.py
  crypto.py
  redaction.py
  admin_auth.py
  audit.py
  app_configs.py
  oauth.py
  connections.py
  db_safety.py
  migration.py
  schemas.py
  reporting.py
  exports.py
  provider_contracts/
    schema.json
    qianchuan.json
    doudian.json
    taobao.json
    pdd.json
  connectors/
    __init__.py
    base.py
    http.py
    registry.py
    qianchuan.py
    doudian.py
    taobao.py
    pdd.py
  sync/
    __init__.py
    queue.py
    scheduler.py
    runner.py
    writer.py
    archive.py
    worker.py
routers/integrations.py
services/qianchuan_performance.py
scripts/integration_worker.py
scripts/migrate_sqlite_to_postgres.py
scripts/generate_integration_secrets.py
scripts/assert_disposable_postgres.py
scripts/check_integration_readiness.py
scripts/verify_public_callback_boundary.py
templates/api_connections_login.html
templates/api_connections.html
static/css/api-connections.css
static/js/api-connections-login.js
static/js/api-connections.js
```

## Execution Order

| 阶段 | 详细计划 | 前置条件 | 可独立交付结果 |
|---|---|---|---|
| 1 | `2026-07-13-ecommerce-api-foundation.md` | 公司测试 PostgreSQL URL；管理员与加密配置可用测试值 | Alembic、SQLite 迁移、安全配置、管理员会话、凭证加密、OAuth 公共边界 |
| 2 | `2026-07-13-ecommerce-sync-core.md` | 阶段 1 | 规范化表、connector 协议、持久任务队列、worker、调度、归档、导出任务 |
| 3 | `2026-07-13-ecommerce-qianchuan-connector.md` | 阶段 2；千川应用控制台权限与回调域名 | 千川真实 OAuth、账户发现、报表同步及现有 Excel 表现兼容 |
| 4 | `2026-07-13-ecommerce-doudian-connector.md` | 阶段 2；抖店应用控制台权限与回调域名 | 抖店订单、商品、SKU、售后同步及事件入队 |
| 5 | `2026-07-13-ecommerce-taobao-connector.md` | 阶段 2；淘宝应用获批后才做真实联调 | TOP 客户端、订单/退款轮询、控制台获批资源同步 |
| 6 | `2026-07-13-ecommerce-pdd-connector.md` | 阶段 2；拼多多应用获批后才做真实联调 | 拼多多客户端、轮询同步、控制台获批资源同步 |
| 7 | `2026-07-13-ecommerce-data-center-ui.md` | 阶段 1 的会话/API，阶段 2 的数据查询服务 | 右下角统一工具菜单、登录、七页签、筛选与导出 UI |
| 8 | `2026-07-13-ecommerce-rollout.md` | 阶段 1–7 中准备上线的平台均通过目标测试 | SQLite→PostgreSQL 切换、历史回溯、平台对账、监控与回滚演练 |

阶段 3 与阶段 4 可在阶段 2 后并行；阶段 5 与阶段 6 也可并行，且不得阻塞千川、抖店与数据中心上线。阶段 7 的静态页面壳可与平台适配并行，但数据动作必须以阶段 2 的稳定 API 合约为准。

## Shared Domain Contracts

平台枚举、游标和资源类型只能定义在 `integrations/types.py`。所有 connector 返回同一结构，禁止平台实现直接写数据库：

```python
@dataclass(frozen=True, slots=True)
class NormalizedRecord:
    resource: ResourceType
    external_id: str
    platform_updated_at: datetime
    payload: Mapping[str, JsonValue]
    sanitized_source_payload: Mapping[str, JsonValue] = field(repr=False)


@dataclass(frozen=True, slots=True)
class FetchPage:
    items: tuple[NormalizedRecord, ...]
    next_cursor: str | None
    has_more: bool
    request_id: str | None
    rate_limit_hint: RateLimitHint | None
    watermark: datetime | None


@dataclass(frozen=True, slots=True)
class VerifiedEvent:
    provider: Provider
    external_event_id: str
    external_subject_id: str
    event_id_scope: EventIdScope
    event_type: str
    external_entity_id: str | None
    platform_updated_at: datetime
    sanitized_payload: Mapping[str, JsonValue] = field(repr=False)


class EcommerceConnector(Protocol):
    provider: Provider

    def authorization_url(self, *, state: str, redirect_uri: str) -> str:
        raise NotImplementedError

    async def exchange_code(self, *, code: str, redirect_uri: str) -> TokenBundle:
        raise NotImplementedError

    async def refresh_tokens(self, tokens: TokenBundle) -> TokenBundle:
        raise NotImplementedError

    async def discover_accounts(self, tokens: TokenBundle) -> list[AccountIdentity]:
        raise NotImplementedError

    async def probe_capabilities(self, connection: ConnectionContext) -> CapabilityReport:
        raise NotImplementedError

    async def fetch_page(
        self,
        *,
        connection: ConnectionContext,
        resource: ResourceType,
        window: TimeWindow | None,
        cursor: str | None,
    ) -> FetchPage:
        raise NotImplementedError

    async def revoke(self, connection: ConnectionContext) -> RevokeResult:
        raise NotImplementedError
```

统一枚举值必须固定为：

```python
class ConnectionStatus(str, Enum):
    SETUP_REQUIRED = "setup_required"
    AUTHORIZING = "authorizing"
    ACTIVE = "active"
    PERMISSION_LIMITED = "permission_limited"
    SYNCING = "syncing"
    DEGRADED = "degraded"
    REAUTHORIZATION_REQUIRED = "reauthorization_required"
    DISABLED = "disabled"


class ConnectionType(str, Enum):
    SHOP = "shop"
    AD_ACCOUNT = "ad_account"


class AuthorizationStatus(str, Enum):
    ACTIVE = "active"
    REAUTHORIZATION_REQUIRED = "reauthorization_required"
    REVOKED = "revoked"
    DISABLED = "disabled"


class EventIdScope(str, Enum):
    PROVIDER = "provider"
    SUBJECT = "subject"


class ResourceType(str, Enum):
    SHOPS = "shops"
    PRODUCTS = "products"
    SKUS = "skus"
    INVENTORY = "inventory"
    ORDERS = "orders"
    ORDER_ITEMS = "order_items"
    REFUNDS = "refunds"
    SHIPMENTS = "shipments"
    SETTLEMENTS = "settlements"
    DAILY_METRICS = "daily_metrics"
    AD_ACCOUNTS = "ad_accounts"
    AD_ENTITIES = "ad_entities"
    AD_DAILY_METRICS = "ad_daily_metrics"
    AD_BALANCE_SNAPSHOTS = "ad_balance_snapshots"
    AD_FINANCE_TRANSACTIONS = "ad_finance_transactions"


class CheckpointStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    COMPLETE = "complete"
    FAILED = "failed"


class SyncStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    SUCCEEDED = "succeeded"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SyncSource(str, Enum):
    SCHEDULED = "scheduled"
    MANUAL = "manual"
    EVENT = "event"
    BACKFILL = "backfill"
    RETRY = "retry"


class JobType(str, Enum):
    SYNC_RESOURCE = "sync_resource"
    REFRESH_AUTHORIZATION = "refresh_authorization"
    PROCESS_EVENT = "process_event"
    ARCHIVE_CLEANUP = "archive_cleanup"
    EXPORT = "export"
    PURGE_CONNECTION = "purge_connection"


class JobStatus(str, Enum):
    QUEUED = "queued"
    LEASED = "leased"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CapabilityStage(str, Enum):
    DOCS_VERIFIED = "docs_verified"
    OAUTH_VERIFIED = "oauth_verified"
    BACKFILL_VERIFIED = "backfill_verified"
    INCREMENTAL_VERIFIED = "incremental_verified"
    RECONCILED = "reconciled"


class ExportStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"
    EXPIRED = "expired"


class OrderStatus(str, Enum):
    UNKNOWN = "unknown"
    PENDING_PAYMENT = "pending_payment"
    PAID = "paid"
    SHIPPED = "shipped"
    COMPLETED = "completed"
    CLOSED = "closed"


class ProductStatus(str, Enum):
    UNKNOWN = "unknown"
    ON_SALE = "on_sale"
    OFF_SHELF = "off_shelf"
    DELETED = "deleted"


class AccountStatus(str, Enum):
    UNKNOWN = "unknown"
    ACTIVE = "active"
    INACTIVE = "inactive"
    CLOSED = "closed"


class RefundStatus(str, Enum):
    UNKNOWN = "unknown"
    REQUESTED = "requested"
    PROCESSING = "processing"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"
    CLOSED = "closed"


class ShipmentStatus(str, Enum):
    UNKNOWN = "unknown"
    PENDING = "pending"
    SHIPPED = "shipped"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    RETURNED = "returned"
    CANCELLED = "cancelled"


class SettlementStatus(str, Enum):
    UNKNOWN = "unknown"
    PENDING = "pending"
    SETTLED = "settled"
    REVERSED = "reversed"


class FinanceTransactionStatus(str, Enum):
    UNKNOWN = "unknown"
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REVERSED = "reversed"


class AdEntityStatus(str, Enum):
    UNKNOWN = "unknown"
    ACTIVE = "active"
    PAUSED = "paused"
    ENDED = "ended"
    DELETED = "deleted"
```

`order_items` 由 `orders` 页面随主记录写入，不单独创建计划 checkpoint。状态机只允许以下转换；终态不得被旧 worker 重新打开：

| 状态机 | 允许转换 |
|---|---|
| connection | `setup_required→authorizing/disabled`；`authorizing→active/permission_limited/reauthorization_required/disabled`；`active↔syncing`；`active/syncing→permission_limited/degraded/reauthorization_required/disabled`；`permission_limited→authorizing/active/degraded/reauthorization_required/disabled`；`degraded→authorizing/active/permission_limited/reauthorization_required/disabled`；`reauthorization_required→authorizing/disabled` |
| authorization | `active→reauthorization_required/revoked/disabled`；`reauthorization_required→active/revoked/disabled` |
| checkpoint | `pending→running`；`running→complete/retry_wait/failed`；`retry_wait→running/failed` |
| sync run | `queued→running/cancelled`；`running→succeeded/partial_success/retry_wait/failed/cancelled`；`retry_wait→running/failed/cancelled` |
| job | `queued→leased/cancelled`；`leased→running/queued`；`running→succeeded/retry_wait/failed/cancelled`；`retry_wait→queued/failed/cancelled` |
| capability | 只按表中顺序前进；应用凭证、scope 或操作目录发生变化时可回退到 `docs_verified` 并重新验收 |
| export | `queued→running/failed`；`running→ready/failed`；`ready→expired`；清理失败不提前标记 `expired` |

Connection 状态描述授权主体的总体健康度，resource capability 描述单个资源能否运行。`permission_limited` 连接仍可调度已完成 `docs_verified`、已获 scope 且 probe 成功的资源，并始终保持 `permission_limited`；缺权资源不得入队。`syncing` 只作为总体状态为 `active` 时的持久活动态；`permission_limited`/`degraded` 的运行活动由 sync run/job 展示，不覆盖其更高优先级健康状态。`degraded` 只允许已存在 checkpoint 的受控重试，不能启动新的回溯。UI 同时显示 connection 健康状态和独立的活动同步计数。

规范化 DTO 的字段矩阵也属于跨阶段固定合约。除下表字段外，writer 不接收平台临时字段；每条 `NormalizedRecord` 信封共同包含非空 `external_id`、aware UTC `platform_updated_at`、严格 `payload` 和经过允许列表过滤的 `sanitized_source_payload`，`provider` 与 `connection_id` 由 runner 注入。`platform_updated_at` 只在信封中，不在 payload 重复。下表带 `?` 的字段可省略或为 `None`，其余字段必须存在且非空/类型有效；`integrations/schemas.py` 只能收紧，不能放宽该合约：

| ResourceType | `payload` 固定字段 |
|---|---|
| `shops` | `external_shop_id`, `name`, `normalized_status`, `raw_status` |
| `products` | `external_product_id`, `external_shop_id?`, `title`, `normalized_status`, `raw_status`, `category?`, `price?`, `currency?` |
| `skus` | `external_sku_id`, `external_product_id`, `title?`, `attributes`, `normalized_status`, `raw_status`, `price?`, `currency?` |
| `inventory` | `external_sku_id`, `quantity`, `available_quantity?`, `captured_at` |
| `orders` | `external_order_id`, `external_shop_id?`, `normalized_status`, `raw_status`, `buyer_digest?`, `province?`, `city?`, `currency`, `order_amount`, `paid_amount`, `discount_amount`, `shipping_amount`, `created_at?`, `paid_at?`, `shipped_at?`, `completed_at?` |
| `order_items` | `external_item_id`, `external_order_id`, `external_product_id?`, `external_sku_id?`, `title`, `quantity`, `unit_amount`, `paid_amount`, `currency` |
| `refunds` | `external_refund_id`, `external_order_id`, `external_item_id?`, `normalized_status`, `raw_status`, `amount`, `currency`, `reason_code?`, `created_at?`, `updated_at?`, `completed_at?` |
| `shipments` | `external_shipment_id`, `external_order_id`, `normalized_status`, `raw_status`, `carrier_code?`, `tracking_number?`, `shipped_at?`, `delivered_at?` |
| `settlements` | `external_settlement_id`, `external_order_id?`, `normalized_status`, `raw_status`, `currency`, `gross_amount`, `fee_amount`, `net_amount`, `settlement_date` |
| `daily_metrics` | `stat_date`, `granularity`, `actual_sales`, `order_count`, `refund_amount`, `refund_count`, `visitor_count`, `buyer_count`, `currency` |
| `ad_accounts` | `external_account_id`, `name`, `normalized_status`, `raw_status`, `currency` |
| `ad_entities` | `entity_type`, `external_entity_id`, `external_parent_id?`, `name`, `normalized_status`, `raw_status` |
| `ad_daily_metrics` | `entity_type`, `external_entity_id`, `stat_date`, `granularity`, `spend`, `impressions`, `clicks`, `orders`, `attributed_sales`, `ctr?`, `cvr?`, `roi?`, `play_count?`, `play_rate?`, `currency` |
| `ad_balance_snapshots` | `external_account_id`, `balance`, `currency`, `captured_at` |
| `ad_finance_transactions` | `external_transaction_id`, `external_account_id`, `transaction_type`, `amount`, `currency`, `normalized_status`, `raw_status`, `transaction_at` |

所有字符串外部 ID 保持字符串；金额使用 `Decimal`，时间为 aware UTC，日报日期按平台业务时区解释。`attributes` 必须是安全的 JSON object，非适用指标不得伪造为零：只有官方契约明确“缺失即零”时才归零，否则使用上表可空字段。姓名、手机号、证件号、详细地址和任何凭证都不在 DTO 合约内。

Writer 的时间冲突规则固定为：较新平台时间戳按允许列表更新，且 `None` 不擦除已有非空详情；较旧记录跳过；相同时间戳且规范 payload 相同为幂等 no-op，相同时间戳但 payload 不同则保留现值、隔离冲突并触发可用的权威详情重取。禁止用到达顺序或 hash 大小决定赢家。

## Required External Inputs

执行时按阶段收集，不把真实值写入仓库：

- `FACAI_TEST_DATABASE_URL`：可清空的 PostgreSQL 测试库，用于 Alembic、租约与迁移集成测试。
- `FACAI_DESTRUCTIVE_TEST_DATABASE_ACK`：必须与测试库的精确 database name 相同，作为 drop/downgrade 测试的显式确认；测试库名还必须以 `_test` 或 `_ci` 结尾。
- `FACAI_MIGRATION_TEST_DATABASE_URL`：与测试库不同的空 PostgreSQL，用于完整 SQLite 迁移后作为预生产 smoke 数据库。
- `DATABASE_URL`：最终公司内网 PostgreSQL URL。
- `FACAI_INTEGRATIONS_ADMIN_PASSWORD_HASH`、`FACAI_INTEGRATIONS_SESSION_SECRET`、`FACAI_INTEGRATIONS_MASTER_KEY`。
- `FACAI_INTEGRATIONS_INTERNAL_BASE_URL`：内网接入中心 HTTPS origin；OAuth 回调只可 303 回到该 origin 下的安全相对路径。
- `FACAI_INTEGRATIONS_PUBLIC_BASE_URL`：稳定 HTTPS 根地址，四个平台控制台均使用从它派生的固定回调 URL。
- `FACAI_INTEGRATION_ARCHIVE_DIR`：应用和 worker 都可读写的内网目录。
- `FACAI_INTEGRATIONS_TRUSTED_PROXY_CIDRS`：仅包含会覆盖 `X-Forwarded-For` 的生产反向代理 CIDR；直连开发环境留空。
- 每个平台的 App ID/Secret、获批 scope、QPS/配额和官方控制台操作目录截图或 JSON 记录；记录必须遮盖 Secret 和 Token。

## Program Verification Gate

- [ ] 阶段 1–8 的目标测试全部通过。
- [ ] `python -m unittest discover -s tests -v` 通过。
- [ ] `python -m compileall -q .` 通过。
- [ ] `npm.cmd run test:e2e` 通过桌面与移动端关键路径。
- [ ] 在生产数据库副本上完成 Alembic upgrade/downgrade/upgrade 与 SQLite 迁移 dry-run/apply 对账。
- [ ] 千川、抖店各至少一个真实账户完成 OAuth、刷新、历史回溯、增量同步和平台导出对账。
- [ ] 淘宝、拼多多只有通过相同真实验收后才显示 `active`；否则 UI 必须显示“待配置/待联调”。
- [ ] 公网探测只能访问 `/integrations/oauth/callback/{provider}` 和 `/integrations/events/{provider}`，其余 `/app`、`/api` 与静态管理资源均不可达。
- [ ] 切换后 `/healthz` 正常，worker heartbeat 在阈值内，崩溃任务能从已提交 cursor 恢复。
- [ ] 在 PostgreSQL 写流量开放前，回滚演练可恢复原 SQLite URL；记录 point-of-no-return 后的演练使用 PostgreSQL 备份/PITR 或向前修复，且 PostgreSQL 永不反向写入 SQLite。
