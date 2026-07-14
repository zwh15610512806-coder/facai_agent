# 电商 API 接入中心设计规格

**日期：** 2026-07-13

**状态：** 已由用户确认，可进入分阶段实施

**适用仓库：** `D:\facai-agent-local`

## 1. 目标与成功标准

在现有法采内网应用中新增一个受保护的“API 接入中心”，支持公司自营的多个巨量千川账户、抖店、淘宝店和拼多多店授权，并通过官方 API 持续获取经营与投放数据。

完成后应满足：

- 桌面端右下角只有一个“工具”入口，展开“数据导入、AI配置、API接入”；移动端三项入口进入顶部工具导航。
- 接入中心可配置平台应用、授权多个店铺或广告账户、查看权限与 Token 状态、立即同步、停用、重授权和永久清除。
- 巨量千川和抖店先完成真实授权、历史回溯、增量同步与平台导出对账。
- 淘宝和拼多多完成真实客户端、授权、签名、分页、字段映射和离线契约测试；只有在获得应用权限并通过真实联调后才显示“已接入”。
- 统一数据中心可查看经营概览、订单、商品、售后、投放和同步记录，可按平台、店铺、日期筛选并导出 CSV/Excel。
- 现有千川 Excel 导入、脚本素材绑定、表现查看和高成交判断继续可用，并能消费新的千川 API 数据。
- 所有连接凭证加密保存且永不回显，买家姓名、手机号和详细地址不以明文落库或进入归档。
- 在 1,000–20,000 单/日的公司总量下，同步任务不阻塞现有页面，失败可续跑，重复分页或事件不会产生重复业务记录。

## 2. 固定范围与非目标

### 2.1 本期范围

- 单公司、单业务空间、多个自营店铺和广告账户。
- 整体迁移到公司内网 PostgreSQL，现有 SQLite 数据完整导入并保留可回滚备份。
- 平台数据尽可能覆盖官方应用实际获批的读取权限：
  - 千川：授权主体、广告账户、余额/资金、计划、创意、素材、商品/直播投放和日报。
  - 抖店：店铺、商品/SKU、库存、订单、售后退款、物流、结算和经营分析。
  - 淘宝、拼多多：对应的店铺、商品、库存、订单、售后、物流、财务/经营与可获批推广数据。
- 首次授权回溯平台允许的最早历史；后续分层自动同步并允许手动立即同步。

### 2.2 非目标

- 不建设对外 SaaS，不提供客户注册、多租户、计费或公开订阅。
- 不保存买家姓名、明文手机号、身份证号或详细收货地址，不承担订单履约操作。
- 不自动把平台商品合并进现有 `Product`；只提供匹配建议和人工关联。
- 不允许用户自定义平台 API Base URL；各 connector 只能访问固定的官方主机。
- 不把外部平台可用性纳入现有 `/healthz`，避免平台故障导致本地服务被判定不可用。
- 不移除现有千川 Excel 导入兜底路径。

## 3. 页面与交互

### 3.1 共享工具菜单

`static/js/common.js` 成为唯一工具入口数据源，维护以下三项：

| 标题 | 路径 | 图标 |
|---|---|---|
| 数据导入 | `/app/import` | `upload` |
| AI配置 | `/app/ai-config` | `settings` |
| API接入 | `/app/api-connections` | `plug-zap` |

桌面端由共享脚本向 `body` 注入一个固定在右下角的 disclosure：按钮使用 `aria-expanded` 和 `aria-controls`，展开内容为普通 `<nav>` 链接。支持鼠标点击、Tab/Shift+Tab、Enter、Escape、点击外部关闭和关闭后的焦点恢复。当前页面对应的工具项不再显示。

移动端隐藏悬浮 launcher，并从同一工具数组向顶部导航注入工具链接。生成页和改写页补载共享脚本，避免现有移动端工具入口缺失。生成页的“回到顶部”按钮位于 launcher 上方；工具菜单展开期间暂时隐藏该按钮，避免重叠。

### 3.2 接入中心

新增：

- `/app/api-connections/login`：接入中心管理员登录。
- `/app/api-connections`：接入中心主页面。

主页面包含七个页签：

1. **接入管理**：平台应用配置、连接卡片、权限、Token 到期、最近同步、立即同步、重授权、停用和永久清除。
2. **经营概览**：店铺实际成交、订单、退款、客单价、商品与库存趋势；广告消耗和广告归因成交独立呈现。
3. **订单**：平台、店铺、日期、状态筛选，服务端分页，无买家敏感明文。
4. **商品**：平台商品/SKU、库存、状态及与产品知识库的人工关联。
5. **售后**：退款/退货状态、金额、订单和商品关联。
6. **投放**：千川及未来获批推广渠道的账户、计划、创意、素材和日报。
7. **同步记录**：任务状态、时间窗、进度、读取/写入/跳过/异常计数和脱敏错误，可按失败时间窗重试。

列表默认每页 50 条、最大 200 条。概览默认最近 30 天；交互查询单次最多 366 天，更长范围走后台导出任务。导出文件生成到 `FACAI_INTEGRATION_ARCHIVE_DIR\exports`，保留 24 小时。

## 4. 安全与网络边界

### 4.1 管理员保护

只有以下范围要求接入中心管理员会话：

- `/app/api-connections*`
- `/api/integrations*`，公开回调路由除外

其中 `GET /app/api-connections/login` 与 `POST /api/integrations/session` 是登录所需的明确公开例外。管理员哈希或会话密钥缺失时，公开登录页显示“安全配置未完成”并禁用表单；其他安全配置缺失时，已登录主页面显示只读提示并禁用保存凭证和发起授权。

其他现有页面和 API 继续保持内网免登录。管理员口令使用 scrypt 哈希配置，不在数据库或仓库保存明文。登录默认限制为同一来源 15 分钟内 5 次失败，之后锁定 15 分钟；成功与失败均写入安全审计记录，但不记录口令。登录来源默认使用 TCP peer；只有 peer 落在 `FACAI_INTEGRATIONS_TRUSTED_PROXY_CIDRS` 时才解析由代理覆盖写入的 `X-Forwarded-For` 和 `X-Forwarded-Proto`，可信代理缺少/提供畸形转发链，或无法从原始 TLS/可信 scheme 确认 HTTPS 时拒绝登录。Uvicorn 不自动改写 peer/scheme，由应用一次性验证真实来源和有效 HTTPS，避免同一代理后的所有用户共享限流或客户端伪造来源/安全 scheme。

会话 cookie 名为 `facai_integrations_session`，有效期 8 小时，设置 `HttpOnly`、`SameSite=Lax`，在 HTTPS 下必须设置 `Secure`。会话签名密钥与数据加密密钥分开配置。生产环境的接入中心必须通过内网 HTTPS 使用；纯 HTTP 只允许 `localhost` 开发环境。

必需环境变量：

- `DATABASE_URL`：公司内网 PostgreSQL URL。
- `FACAI_INTEGRATIONS_ADMIN_PASSWORD_HASH`：管理员口令的 scrypt 编码哈希。
- `FACAI_INTEGRATIONS_SESSION_SECRET`：管理员会话签名密钥。
- `FACAI_INTEGRATIONS_MASTER_KEY`：32 字节凭证加密主密钥。
- `FACAI_INTEGRATIONS_INTERNAL_BASE_URL`：接入中心内网 HTTPS origin，用于 OAuth 完成后安全回跳。
- `FACAI_INTEGRATIONS_PUBLIC_BASE_URL`：稳定 HTTPS 回调根地址。
- `FACAI_INTEGRATION_ARCHIVE_DIR`：内网加密归档目录。
- `FACAI_INTEGRATIONS_TRUSTED_PROXY_CIDRS`：可留空；仅填写会覆盖 `X-Forwarded-For` 的授权代理精确 CIDR，禁止全网段。

任何必需安全配置缺失时，接入中心显示“安全配置未完成”并拒绝保存凭证或发起授权；现有非接入功能仍可使用。

### 4.2 凭证与 OAuth

- 平台 App Secret、Access Token、Refresh Token 使用 AES-GCM 信封格式加密，密文包含版本、随机 nonce 和认证标签；主密钥只来自环境变量。买家 ID 摘要使用从主密钥经 HKDF-SHA256 和固定用途标签派生的独立 HMAC 子密钥，不直接复用加密密钥。
- App ID、店铺/账户外部 ID、scope 和到期时间可明文保存；API 只返回 Secret/Token 是否已配置及尾部掩码，永不返回密文或明文。
- OAuth state 使用至少 32 字节安全随机值，只保存其哈希，绑定平台、发起会话摘要（仅审计）和安全相对回跳地址，10 分钟过期且只能消费一次。公网回调 host 与内网管理 host 分离，因此回调不依赖 host-only 管理员 cookie；一次性 state 本身是完成回调的凭据。
- Token 交换在回调收到 code 后立即完成；state 过期、平台不匹配或重复使用一律拒绝。
- 成功或失败完成页只 303 回跳到经过配置验证的 `FACAI_INTEGRATIONS_INTERNAL_BASE_URL` 加已验证相对路径，不把 code、state、Token 或错误原文带回查询串；公网 callback host 自身永不承载 `/app` 页面。
- Token 属于一次平台授权而不是单个广告账户。Token 刷新按授权记录加数据库租约，并原子替换整组令牌，始终以平台返回的 `expires_at`/`expires_in` 为准；同一授权发现的多个账户不重复保存 Token。

### 4.3 公网回调

公网反向代理只转发：

- `GET /integrations/oauth/callback/{provider}`
- `GET|POST /integrations/events/{provider}`

OAuth 回调严格校验一次性 state。平台事件严格校验各自官方签名，并只负责幂等入队后快速返回；业务处理由后台 worker 完成。回调域名加入 Host allowlist，但 `/api/integrations` 和所有 `/app` 页面不通过公网代理暴露。

内网与公网 origin 的精确 hostname/port 都加入应用 Host allowlist，禁止通配符：内网 host 可访问接入中心，公网 host 仍先经过 callback fence，只能访问已列出的回调路径；任意第三 host 返回拒绝响应。

## 5. 数据平台与迁移

### 5.1 PostgreSQL 成为唯一业务数据库

本期不采用“现有 SQLite + 电商 PostgreSQL”双库模式。所有现有 SQLAlchemy 业务表和新增接入表迁移到同一个公司内网 PostgreSQL，以保留外键、事务和直接关联能力。

引入 Alembic 管理 PostgreSQL 版本：

- `20260713_0001` 建立当前业务表的 PostgreSQL 基线，以及应用配置、授权、连接、OAuth state、登录限流和安全审计等接入安全/控制表。
- `20260713_0002` 建立持久任务、worker 心跳、同步 checkpoint/run/error、归档/导出任务和统一经营数据表；后续平台兼容变更使用独立 revision（例如千川绑定键 `20260713_0003`），并明确串联 `down_revision`。
- 生产启动不自动修改 schema；部署步骤先执行 `alembic upgrade head`。
- 现有 SQLite 专用 PRAGMA、备份和兼容迁移继续由方言判断保护，仅用于旧数据库维护和导入。
- PostgreSQL 使用 SQLAlchemy 约束/索引实现现有枚举、唯一性和外键语义。

新增一次性迁移命令：

```powershell
python scripts/migrate_sqlite_to_postgres.py --source .\data\script_agent.db --backup-only
python scripts/migrate_sqlite_to_postgres.py --source .\data\script_agent.db --target-env DATABASE_URL --dry-run
python scripts/migrate_sqlite_to_postgres.py --source .\data\script_agent.db --target-env DATABASE_URL --apply
```

`--backup-only` 在不连接目标库的情况下用 SQLite backup API 创建一致性备份并输出源/备份 SHA-256。迁移按外键顺序复制并保留主键、时间、JSON 和绑定关系；更新 PostgreSQL sequences。`--dry-run` 和 `--apply` 都输出：每表源/目标行数、关键金额汇总、孤儿外键、重复唯一键和 JSON 解析错误。任何校验失败时不切换应用配置。

### 5.2 核心接入表

- `integration_app_configs`
  - 每个平台一条：`provider`、`app_id`、`app_secret_ciphertext`、配置状态和更新时间。
- `integration_authorizations`
  - 一次 OAuth 授权主体一条：`provider`、外部授权主体 ID、scope、状态、Access/Refresh Token 密文、到期时间、刷新租约和最近授权时间。
  - 千川的一次授权可以关联多个广告账户；抖店、淘宝和拼多多通常每个店铺各有独立授权。
- `integration_connections`
  - `id`、`authorization_id`、`provider`、连接类型（仅店铺/广告账户）、外部账户 ID、显示名、状态、最近成功同步和停用时间；连接本身不保存 Token。代理/授权主体只存在于 `integration_authorizations`，不重复建成 connection。
  - 唯一键：`provider + connection_type + external_account_id`。
- `integration_oauth_states`
  - state 哈希、provider、发起会话摘要、过期时间、消费时间；state 哈希唯一。
- `integration_sync_checkpoints`
  - `connection_id + resource_type + window_start + window_end` 唯一，保存 cursor、状态、尝试次数、下一次重试、租约持有者和租约过期时间。
- `integration_sync_runs`
  - 任务来源（计划/手动/事件/回溯）、资源、窗口、状态、进度、读取/写入/跳过/隔离计数、开始/结束和脱敏错误。
- `integration_sync_errors`
  - 运行、资源外部键哈希、错误类型、脱敏摘要和可重试标记；不保存凭证或买家敏感明文。
- `integration_archive_manifests`
  - provider、connection、resource、窗口、文件路径、SHA-256、记录数、创建和过期时间。
- `integration_export_jobs`
  - 请求人会话摘要、资源、筛选条件、格式、状态、文件路径、行数、创建/完成/过期时间和脱敏错误；请求人摘要只用于审计，不作为访问控制。任一当前有效的接入管理员会话都可查询/下载不可猜测 UUID 对应的任务；未登录一律拒绝。下载文件 24 小时后过期。
- `integration_security_audit`
  - 管理员登录、配置变更、授权、断开、重授权、同步、导出和永久清除事件。
- `integration_login_throttles`
  - 仅保存来源摘要、失败窗口、失败次数和锁定时间，使管理员登录限流在多进程与重启后仍然生效。
- `integration_jobs`
  - 持久任务类型、去重键、脱敏 payload、优先级、可运行时间、尝试次数、租约、心跳和脱敏错误；由 PostgreSQL worker 领取。
- `integration_worker_heartbeats`
  - worker ID、进程 ID、启动时间、最近心跳和活跃任务数，用于运行状态监控。

### 5.3 统一经营数据

新增规范化实体：

- `commerce_shops`
- `commerce_products`
- `commerce_skus`
- `commerce_inventory_snapshots`
- `commerce_product_links`（平台商品到现有 `Product` 的人工映射；SKU 通过所属平台商品继承该关联）
- `commerce_orders`
- `commerce_order_items`
- `commerce_refunds`
- `commerce_shipments`
- `commerce_settlements`
- `commerce_daily_metrics`
- `commerce_ad_accounts`
- `commerce_ad_entities`（计划/广告组/创意/素材，使用 `entity_type` 区分）
- `commerce_ad_daily_metrics`
- `commerce_ad_balance_snapshots`
- `commerce_ad_finance_transactions`
- `commerce_event_inbox`

每个业务表必须包含 `connection_id`、`provider`、平台外部主键和平台更新时间。幂等唯一键以 `connection_id + platform_external_id` 为基础；日报增加 `stat_date + granularity`，库存快照增加 `captured_at`。订单金额、退款、消耗和成交金额使用 `NUMERIC(20,2)`，比例使用 `NUMERIC(20,6)`；时间以带时区 UTC 存储，UI 按 `Asia/Shanghai` 展示。

平台订单仅保存经营所需字段：平台订单号、店铺、商品/SKU、数量、金额、状态、支付/发货/完成时间和省市级地区。买家外部 ID 使用 HMAC 摘要；姓名、手机号、身份证和详细地址在适配器边界直接删除。

## 6. Connector 接口与平台实现

四个平台实现同一内部协议：

```python
class EcommerceConnector(Protocol):
    provider: Literal["qianchuan", "doudian", "taobao", "pdd"]

    def authorization_url(self, *, state: str, redirect_uri: str) -> str: ...
    async def exchange_code(self, *, code: str, redirect_uri: str) -> TokenBundle: ...
    async def refresh_tokens(self, tokens: TokenBundle) -> TokenBundle: ...
    async def discover_accounts(self, tokens: TokenBundle) -> list[AccountIdentity]: ...
    async def probe_capabilities(self, connection: ConnectionContext) -> CapabilityReport: ...
    async def fetch_page(
        self,
        *,
        connection: ConnectionContext,
        resource: ResourceType,
        window: TimeWindow | None,
        cursor: str | None,
    ) -> FetchPage: ...
    async def revoke(self, connection: ConnectionContext) -> RevokeResult: ...
```

`FetchPage` 固定包含 `items`、`next_cursor`、`has_more`、`request_id`、`rate_limit_hint` 和平台水位时间。适配器完成签名、分页、平台错误翻译和敏感字段删除；统一同步层负责幂等写入、任务、重试和归档。

平台分离：

- **巨量千川**：独立 OAuth、令牌刷新和 `Access-Token` 请求头；同步授权主体/广告账户及投放数据。可选 SPI 事件使用官方签名校验。
- **抖店**：独立店铺 OAuth；请求使用官方 HMAC-SHA256 签名。消息回调验签后必须用官方安全主体字段解析到唯一启用店铺，并按控制台证据确认 `msg_id` 是平台全局还是主体内唯一后生成幂等键；无法唯一路由的事件不进入业务任务。轮询仍负责最终对账。
- **淘宝**：独立店铺 OAuth/session 和 TOP 签名。首版以 15 分钟轮询为一致性来源；若后续启用 TMC，必须作为独立消息 consumer，不能伪装成 HTTP webhook。
- **拼多多**：独立店铺 OAuth 和官方网关签名。首版以 15 分钟轮询为一致性来源；若后续启用官方消息能力，必须采用独立 WebSocket consumer，不能复用 HTTP webhook。

每个连接授权后先做 capability probe，将“平台理论能力”与“本应用实际获批 scope”分开。页面显示缺失权限、受限资源和可查询的最早日期。未配置应用、未获批权限或未完成真实 OAuth 的平台显示“待配置/待联调”，不得显示“已接入”。

## 7. 同步、调度与归档

### 7.1 Worker

新增独立 `integration-worker` 进程，不在 FastAPI 请求或 lifespan 线程中执行长时间回溯。FastAPI 只创建任务和返回状态；worker 使用 PostgreSQL `FOR UPDATE SKIP LOCKED` 领取任务并定期刷新租约。首版不引入 Redis/Celery，任务、计划和 worker heartbeat 全部持久化在 PostgreSQL。

默认并发为 4 个任务，但同一 `connection_id + resource_type` 只能有一个活跃租约。并发可通过环境变量调低，不能绕过各平台限流。

### 7.2 调度

- 首次回溯：按 connector 报告的最早允许日期分片；订单/售后/物流和日报按天分片，商品/SKU/库存按分页快照。
- 订单与售后：每 15 分钟。
- 商品与库存：每小时。
- 店铺经营与广告日报：每天 06:00（Asia/Shanghai），同时重拉最近 7 天。
- Token：按 `authorization_id` 在 connector 判断进入安全刷新窗口时入队，始终服从平台返回的到期时间。
- 手动同步：管理员可选择连接、数据域和日期范围；与计划任务共享同一幂等与租约机制。

### 7.3 重试和部分失败

- 429、网络错误、超时和 5xx 使用带随机抖动的指数退避，最多自动尝试 6 次；平台返回的重试时间优先。
- 401/鉴权失败只尝试一次按授权加锁的 Token 刷新；再次失败将授权及其关联连接标记为 `reauthorization_required`。
- 明确的权限不足不重试，将连接标记为 `permission_limited` 并列出缺失能力。
- 每成功提交一页才推进 cursor；进程在中间退出时从最后提交页重跑。
- 单条格式异常进入脱敏隔离记录，其他记录继续，运行状态为 `partial_success`；管理员可按失败窗口重试。
- 业务写入采用 upsert 并比较平台更新时间，旧分页或乱序事件不能覆盖更新数据。

### 7.4 归档

平台响应进入持久层前先删除敏感字段，再序列化为 JSONL、gzip 压缩并使用 AES-GCM 加密，最终以原子重命名写入 `FACAI_INTEGRATION_ARCHIVE_DIR`。数据库 manifest 保存文件 SHA-256、记录数和到期时间。每天清理超过 90 天的归档；清理失败产生告警，不删除对应 manifest。

## 8. 现有千川兼容

现有 `QianchuanImportBatch`、`QianchuanMaterialPerformance` 和 `QianchuanScriptBinding` 继续保留历史 Excel 数据。把 `routers/templates.py` 中导入后的持久化、素材候选、绑定和高成交更新拆为可复用服务：

- Excel importer 输出当前规范行。
- 千川 connector 输出同一规范行，再写入统一广告实体/日报表。
- 读取脚本表现时通过兼容查询同时读取历史 Excel 行和 API 行，并以来源、连接、素材 ID、统计日期去重。
- 绑定仍由明确素材 ID 建立；模糊或多候选情况继续进入人工复核，不能因 API 自动同步而强制重绑。
- API 数据按 `connection_id + external_material_id + stat_date + granularity` 幂等，不使用 Excel 文件 SHA 作为 API 去重键。

## 9. API 合约

所有管理和数据端点位于 `/api/integrations`，除登录外都要求接入中心管理员会话：

- `POST /api/integrations/session`、`DELETE /api/integrations/session`
- `GET /api/integrations/providers`
- `PUT /api/integrations/providers/{provider}/app-config`
- `POST /api/integrations/providers/{provider}/authorize`
- `GET /api/integrations/authorizations/{authorization_id}`
- `DELETE /api/integrations/authorizations/{authorization_id}`：撤销整次授权，停用其全部连接
- `GET /api/integrations/connections`
- `GET /api/integrations/connections/{connection_id}`
- `POST /api/integrations/connections/{connection_id}/sync`
- `POST /api/integrations/connections/{connection_id}/reauthorize`
- `DELETE /api/integrations/connections/{connection_id}`：撤销/停用，保留历史数据
- `POST /api/integrations/connections/{connection_id}/purge`：再次验证管理员口令和确认短语后永久删除该连接历史
- `GET /api/integrations/sync-runs`
- `GET /api/integrations/sync-runs/{run_id}`
- `POST /api/integrations/sync-runs/{run_id}/retry`
- `GET /api/integrations/data/overview`
- `GET /api/integrations/data/orders`
- `GET /api/integrations/data/products`
- `GET /api/integrations/data/refunds`
- `GET /api/integrations/data/ad-entities`
- `GET /api/integrations/data/ad-metrics`
- `PUT /api/integrations/data/products/{commerce_product_id}/link`
- `DELETE /api/integrations/data/products/{commerce_product_id}/link`
- `POST /api/integrations/exports`
- `GET /api/integrations/exports/{export_id}`
- `GET /api/integrations/exports/{export_id}/download`

返回连接时只包含平台、外部主体 ID、显示名、状态、最近同步，以及关联授权的 scope、Token 到期和凭证掩码。所有请求模型拒绝未知字段，日期、分页和枚举均在 Pydantic 层验证。

订单、商品、售后和投放实体同时保存平台原始状态与固定规范状态。规范状态枚举由 Pydantic 和数据库约束共享；无法映射的新平台状态归入 `unknown` 并保留原值，不能因未知状态丢弃记录。普通业务页面的工具菜单显示三项；进入数据导入、AI 配置或 API 接入任一工具页时过滤当前项，因此显示两项。

## 10. 状态、断开和清除

连接状态固定为：

- `setup_required`
- `authorizing`
- `active`
- `permission_limited`
- `syncing`
- `degraded`
- `reauthorization_required`
- `disabled`

断开单个连接时只将该账户设为 `disabled` 并保留历史经营数据；若同一授权仍有其他启用账户，不能撤销或清空共享 Token。撤销授权会调用平台 revoke（若支持）、清空授权 Token 密文，并停用其全部连接。永久清除单个连接要求管理员重新输入口令和连接显示名作为确认短语，记录安全审计后按外键级联删除该连接的业务数据、任务和归档；仅当授权不再关联其他连接时才删除授权记录。

## 11. 交付顺序

1. PostgreSQL/Alembic 基线、SQLite 导入与回滚验证。
2. 接入中心管理员保护、凭证加密、公共回调边界和安全审计。
3. 统一 connector、同步任务、worker、规范化表、归档与工具菜单/接入页面。
4. 巨量千川真实 connector，并接通现有脚本表现链路。
5. 抖店真实 connector、订单/售后消息入队和轮询对账。
6. 淘宝 connector、轮询同步和离线契约；取得应用权限后真实联调。TMC 作为后续可选能力。
7. 拼多多 connector、轮询同步和离线契约；取得应用权限后真实联调。WebSocket 消息作为后续可选能力。
8. 统一数据中心、筛选、跨店汇总与导出。
9. 全量回溯、平台导出对账、运行监控、切换和回滚演练。

每一项必须能独立测试和回滚。淘宝或拼多多外部资质未完成不能阻塞千川、抖店与统一数据中心上线，但对应平台必须保持“待联调”。

## 12. 测试与验收

### 12.1 自动化测试

- PostgreSQL 模型、Alembic upgrade/downgrade、SQLite 迁移 dry-run/apply、sequence、行数、金额和外键校验。
- 管理员登录限流、cookie 属性、未授权访问、会话过期和安全审计。
- 密钥加解密、主密钥缺失、密文篡改、API/日志/错误不泄漏 Secret 或 Token。
- OAuth state 平台不匹配、过期、重放、code 交换失败和回调 Host/Origin 边界。
- 四平台签名、Token 交换/刷新、分页、错误翻译和 capability probe，使用固定官方格式夹具，不访问真实网络。
- Doudian 消息重复/乱序，以及淘宝/拼多多轮询窗口重叠、重复分页和迟到更新；后续启用 TMC/WebSocket 时须另补重连与重复消费测试。
- 分页重复、平台更新时间乱序、任务租约、Token 并发刷新、429/5xx 退避、崩溃续跑、部分成功和隔离重试。
- 跨连接数据隔离、商品人工关联、PII 删除、归档加密/过期清理、断开保留和永久清除。
- 千川 Excel 与 API 行产生一致的规范化表现字段，现有绑定和高成交逻辑不回归。
- 工具菜单鼠标/键盘/ARIA、当前页过滤、生成页按钮避让、移动端三入口和接入中心七页签。

### 12.2 真实联调验收

千川和抖店分别使用至少一个法采账户完成：

1. OAuth 授权、权限探测和 Token 刷新。
2. 平台允许的完整历史回溯，断点重启后继续。
3. 一次计划增量同步和一次手动日期范围同步。
4. 同一时间窗与平台导出对账：随机抽查 20 条明细；抖店订单 ID、状态和金额精确到分；千川实体 ID 一致，投放金额差异不超过 `max(0.01 元, 0.1%)`，且在平台报表完成归因更新后比较。
5. 页面、导出、脚本表现和同步记录均显示相同来源数据。

淘宝和拼多多只有在真实 OAuth、权限探测、至少一次全量回溯、一次增量同步和同类对账全部通过后，状态才可从“待联调”改为“已接入”。

### 12.3 项目验证门槛

- 目标单元测试与完整 `python -m unittest discover -s tests -v` 通过。
- `python -m compileall -q .` 通过。
- `npm.cmd run test:e2e` 通过桌面与移动端关键路径。
- PostgreSQL 迁移在生产数据库副本上 dry-run 和 apply 均通过。
- 真实服务重启后 `/healthz` 正常，worker heartbeat 正常，未完成同步能从持久游标恢复。
- 公网探测只能访问两类回调路径，业务页面和管理 API 均不可达。

## 13. 切换与回滚

1. 在维护窗口停止写入，停止 uvicorn 和同步 worker。
2. 使用迁移命令 `--backup-only` 对 SQLite 做一致性备份并记录源文件与备份文件 SHA-256。
3. 对空 PostgreSQL 执行 `alembic upgrade head`，运行迁移 `--dry-run` 后再 `--apply`。
4. 核对所有表行数、关键金额、外键、最新记录和随机样本。
5. 使用 PostgreSQL 只读账号、关闭外部流量和 worker 启动应用，仅做 GET/离线 smoke；核对迁移后基线，证明没有新增写入。
6. 关键验证失败且尚未开放任何写入时：停止新服务，恢复旧 `DATABASE_URL`，使用原 SQLite 启动；失败的 PostgreSQL 实例保留用于排查，不反向写回 SQLite。
7. 验证通过后记录“SQLite 回滚关闭”时间点，切到 PostgreSQL 写账号并恢复业务流量。自首个 PostgreSQL 用户/后台写入起，只允许 PostgreSQL 备份/PITR 或向前修复，不得再切回冻结 SQLite；随后才逐个平台启用同步。

## 14. 外部门槛与默认假设

- 这是公司内部应用，授权主体均为法采自营或同公司控制的店铺/账户。
- 千川和抖店现有应用凭证可先用于真实联调；具体 scope、QPS、历史窗口和收费权限以控制台实际审批为准。
- 淘宝和拼多多应用可能尚未获批，因此代码和离线契约可以交付，但生产“已接入”状态依赖真实凭证与平台审核。
- 用户将在真实 OAuth 前提供一个稳定 HTTPS 域名，并让反向代理只暴露规定回调路径。
- 用户将在迁移前提供公司内网 PostgreSQL 实例、数据库账号、备份策略和加密归档目录。
- 所有经营币种按人民币处理；如平台返回其他币种，connector 必须保留原币种并拒绝混入人民币汇总，直到明确汇率策略。

## 15. 官方文档基线

- 巨量引擎开放平台及千川 API：<https://open.oceanengine.com/labels/12>
- 抖店开放平台 API：<https://op.jinritemai.com/docs/api-docs/>
- 淘宝开放平台：<https://open.taobao.com/>、<https://developer.alibaba.com/docs>
- 拼多多开放平台：<https://open.yangkeduo.com/>

实现前应再次核对控制台当前应用类型、获批 scope、具体 API 限流和最新签名要求；公开文档与真实应用能力冲突时，以控制台批准能力和官方接口返回为准，并在 capability report 中展示差异。
