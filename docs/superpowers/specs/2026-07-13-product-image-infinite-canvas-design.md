# 商品图生成无限画布设计

## 1. 背景

当前项目是 FastAPI、Jinja2、SQLite 和静态 JavaScript 组成的本地 AI 工作台，`/app` 是主要 AI 工作入口。用户希望在现有入口中增加一个独立的商品视觉工作区：上传产品图并输入提示词后，可在无限画布中生成和编辑主图、SKU 图、详情页图片。

该功能同时需要满足两类使用方式：

- 完整套图模式：面向快速批量生产，用户按需选择主图、SKU 图、详情图并配置数量、比例、提示词和模型。
- 高级节点模式：面向精细调整，以预定义节点组合产品素材、提示词、模型生成、构图、文字和导出流程。

两个模式不是两个独立产品，而是同一个项目语义数据的两种操作界面。所有项目、素材、任务和结果必须服务端持久化，浏览器刷新或服务重启后仍可恢复。

## 2. 目标与成功标准

### 2.1 目标

- 从现有 `/app` 工具栏进入独立、全屏的商品视觉画布。
- 支持独立项目，并允许按项目新建、搜索、切换、重命名、归档、恢复和删除。
- 上传产品原图和可选的 SKU 参考图，自动获得可用于合成的透明产品素材。
- 由用户交互选择要生成的主图、SKU 图、详情图，不预选输出类型，也不提供固定套图套餐。
- 内置 Seedream 5.0 完整版，并支持通过 HTTP API 接入第三方图片模型。
- 生成模型负责背景和场景；产品包装、Logo、标签文字和外形由原始产品图层锁定合成。
- 同一组 SKU 只强制统一构图，背景、光线、色彩和装饰风格不做硬性统一。
- 营销文案、价格、规格等使用可编辑文字图层，不由图片模型烘焙。
- 支持逐图状态、部分失败、单张重试、取消和服务重启恢复，避免静默重复调用付费模型。
- 支持单张图片、分类 ZIP、详情切片和详情长图导出。

### 2.2 成功标准

一个新用户可以完成以下闭环：

1. 从 `/app` 进入画布并新建项目。
2. 上传透明图时系统跳过抠图；上传白底或复杂背景的不透明图片时系统自动抠图。
3. 按需选择主图、SKU 图或详情图，配置每类输出并选择 Seedream 或已启用的第三方模型。
4. 生成的最终图片中，产品主体来自锁定原图层，而不是模型重绘结果。
5. 同组 SKU 在不同图片中保持统一的归一化产品位置、比例、安全区和镜头框架。
6. 可以在完整套图模式和高级节点模式之间切换而不丢失项目数据。
7. 失败图片可单独重试，成功图片不会重复生成。
8. 浏览器刷新和服务重启后，项目、素材、画布、任务和结果仍可恢复。
9. 成品可按单张、分类 ZIP、详情切片或详情长图导出，且无系统水印。

## 3. 已确认范围

### 3.1 当前版本包含

- 无限画布、项目侧栏、属性面板、节点工具栏和任务状态栏。
- 完整套图模式与高级预定义节点模式。
- 产品原图、SKU 参考图、提示词、构图组、可编辑文字和输出画板。
- 自动透明检测与自动 `rembg` 抠图。
- Seedream 5.0 完整版内置适配器。
- OpenAI Images-compatible 适配器。
- 声明式通用 HTTP API 适配器，支持同步返回和提交后轮询。
- 项目自动保存、版本冲突处理、任务队列、取消、恢复和逐图重试。
- 服务端权威合成与导出。

### 3.2 当前版本不包含

- ComfyUI 工作流导入。
- 直接加载或运行本地模型权重。
- 任意 Python、JavaScript、Jinja、`eval` 或用户脚本型模型适配器。
- 凭空生成没有对应原图的新产品角度。
- 让生成模型重绘、补字、修复或改变产品包装。
- 将价格、规格或营销文字直接烘焙进模型生成图。

“任意第三方模型”在本设计中指能通过 HTTP(S) JSON 或 Multipart API，以 Bearer/API-Key 等常见鉴权方式完成同步生成或“提交任务后轮询”的图片模型。OAuth 刷新、HMAC 签名、WebSocket、gRPC 或其他特殊私有协议需要后续增加独立适配器，但不需要改动画布和任务领域模型。

## 4. 技术架构

### 4.1 总体结构

- `/app` 保持现有 Jinja2 AI 工作页，只新增一个“产品视觉画布”工具按钮。
- `/app/canvas` 负责项目空状态、项目选择和新建；创建或选择项目后进入 `/app/canvas/{project_id}`。
- `/app/canvas/{project_id}` 是独立全屏工作区，不把画布逻辑继续塞进现有大型 `inspiration.js`。
- FastAPI 继续提供页面入口、项目 API、素材 API、模型管理、任务队列、SSE 事件和文件下载。
- SQLite 保存领域数据和任务状态；图片文件保存到项目专属目录，不以 Base64 存入数据库。

### 4.2 前端技术

采用 Vite + TypeScript + Fabric.js，不引入 React：

- 源码放在 `frontend/canvas/`。
- 构建产物放在 `static/canvas/`，生产运行不依赖 Vite 开发服务器。
- Vite 固定输出 `static/canvas/canvas.js` 和 `static/canvas/canvas.css`，这两个生产构建产物随仓库提交，保证仅启动 Python 服务时页面也可用；CI 在测试前重新构建并检查产物无漂移。
- `templates/canvas.html` 只提供根节点、启动配置以及上述固定资源入口。
- `ProjectStore` 使用类型化 state、action 和 reducer 管理项目语义状态，并且是前端唯一权威状态。
- `CanvasAdapter` 是 Fabric.js 的唯一封装层，负责画布对象、节点、连线、选择、缩放、平移和从 Store 到画布的增量映射。
- Fabric 的 `added`、`modified`、`removed` 等事件只能派发类型化 action；服务端不保存 `canvas.toJSON()` 或其他 Fabric 内部 JSON。
- DOM 组件按项目侧栏、顶部工具栏、完整套图面板、节点工具栏、属性栏、模型选择器和状态栏拆分，不直接读写 Fabric 内部对象。
- Fabric.js 负责交互编辑和预览，不作为最终成品渲染器。

前端状态分为：

- `semanticState`：产品/SKU ID引用、提示词、输出类型、数量、比例、模型选择、构图组、节点和连线。SKU 名称、参考图和 SKU 配置以服务端 SKU 表为唯一权威。
- `layoutState`：节点位置、视口、输出画板、产品层和文字层的确定性变换。
- `runtimeState`：当前选中对象、面板展开、上传进度、连接预览等临时状态，不保存进项目。
- 服务端任务状态：由任务 API 和 SSE 提供，不复制进 Fabric JSON。

项目 JSON 只引用稳定的项目 ID、节点 ID、SKU ID、构图组 ID和资产 ID；禁止嵌入 Fabric JSON、Base64、API 密钥、第三方临时图片 URL或未校验的任意外部 URL。切换项目时销毁旧 Fabric 实例、取消未完成图片加载并移除全部旧事件监听，防止项目状态串漏。

### 4.3 服务端模块边界

- `canvas_projects`：项目、SKU 和画布状态。
- `canvas_assets`：上传、检测、抠图、预览和安全文件访问。
- `canvas_providers`：模型提供商、模型目录、能力和凭据。
- `canvas_generation`：任务编排、适配器调用、恢复、取消和重试。
- `canvas_compositor`：产品锁定合成、文字渲染和导出。
- `canvas_events`：从数据库状态产生 SSE 快照与增量事件。

现有 `JobRun` 只能表达总进度，缺少逐图状态、租约、幂等、外部任务 ID和尝试历史，因此不能作为画布生成任务的权威存储。它可以保留为全局运维摘要，但画布必须使用独立任务表。

## 5. 页面布局与项目交互

### 5.1 工作区布局

- 左侧：项目侧栏，支持新建、搜索、切换、重命名、归档、恢复和删除。
- 顶部：返回 AI 工作、模式切换、撤销/重做、缩放、模型管理、保存状态和导出。
- 中央：可无限平移和缩放的 Fabric 画布，包含节点、连线、输出画板和生成结果。
- 右侧：当前节点、产品层、构图组、文字层或输出画板的属性面板。
- 底部：项目保存状态、抠图状态、生成进度、失败数量和成本提示。

### 5.2 项目行为

- 项目列表以服务端为权威，不以 `localStorage` 为权威。
- 新建项目后创建空白语义图，不继承其他项目的输出选择、提示词、SKU、模型或构图。
- 切换项目前先刷新待保存变更，再关闭旧项目的 SSE 和轮询。保存失败时提供“重试、留在当前项目、放弃本地变更”，不得直接切走。
- 自动保存采用 1 秒防抖；`visibilitychange` 和 `pagehide` 时尝试刷新。页面仍为 dirty 时用 `beforeunload` 警告，不承诺异步保存一定在关闭前完成。
- 保存携带 `revision`。服务端版本不一致时返回 `409`，界面提示“项目已在其他标签页更新”，不做静默覆盖。
- 状态栏明确显示“保存中、已保存、保存失败、服务离线、版本冲突”。
- 有非终态任务或未处理的 `unknown` 任务时禁止归档和永久删除；用户必须先取消任务，或把未知项显式标记为放弃/重新尝试。
- 归档可恢复。永久删除需要二次确认，项目先进入 `deleting` 状态，再由可恢复的本地清理任务删除受控项目目录和数据库记录，避免数据库与文件删除中断后产生悬空状态。
- 撤销/重做基于 reducer command history，覆盖节点、连线、布局、文字和构图修改；不撤销上传、付费调用、任务状态或 Provider 配置。切换项目或刷新后清空历史。

## 6. 两种工作模式

### 6.1 完整套图模式

新项目中“主图、SKU 图、详情图”三个输出按钮均不选中。用户选择某类输出后，才展开该类设置：

- 图片数量。
- 比例或精确尺寸。
- 类型级提示词。
- 模型选择和模型能力参数。
- 主产品或具体 SKU 参考资产。

没有选择任何输出类型、没有完成数量/比例配置、没有产品素材或没有选择可用模型时，生成按钮保持禁用，并显示具体缺失项。

每种输出类型可以选择不同模型；提供显式的“应用同一模型到全部已选类型”操作，但不自动覆盖用户已有选择。提交前显示本次实际图片数量；配置了价格信息时显示预估费用，否则明确显示“供应商未提供可估算价格”。

### 6.2 高级节点模式

只允许使用预定义、带类型端口的节点：

- 产品源图节点。
- SKU 参考图节点。
- 自动抠图节点。
- 提示词节点。
- 模型生成节点。
- 主图输出节点。
- SKU 输出节点。
- 详情图输出节点。
- 可编辑文字节点。
- 构图组节点。
- 导出节点。

端口按 `product_asset`、`cutout_asset`、`prompt`、`background_image`、`composition`、`text_layer` 和 `output_image` 分型，不允许连接不兼容端口。生成前校验必需输入、模型能力、尺寸、SKU 资产和输出连线。

自动抠图节点是上传后由系统自动创建的只读处理状态/结果投影，不是关闭自动抠图的开关。它不能被删除或断开来绕过不透明图片的自动抠图，也不能因模式切换重复调用；重新抠图只能由素材属性中的显式“重新抠图”操作触发。

### 6.3 两种模式的数据一致性

完整套图模式是同一语义图的表单投影，高级模式是该语义图的节点投影，不维护第二份表单状态。

- 完整套图模式创建的节点组标记为 `managedBy: complete-set`。
- 高级模式对完整套图可表达字段的修改实时回写完整套图面板。
- 如果高级模式修改为完整套图面板无法表达的拓扑，项目标记为“已高级自定义”。
- “已高级自定义”状态下，完整套图面板只读展示当前配置；只有用户明确执行“重建套图结构”并二次确认后，才重新生成受管节点。
- 模式切换不得静默删除节点、重置提示词、替换模型或丢弃生成结果。
- 两种模式使用同一个 `ProjectStore` 和同一个 Fabric 实例。完整套图模式隐藏端口与连线但保留相同输出画板和结果；高级模式显示完整节点拓扑。
- “重建套图结构”先展示差异，只替换 `managedBy: complete-set` 的受管节点；自定义节点和历史结果默认保留。

### 6.4 结果版本与输出画板

- 每个输出画板在项目语义状态中有稳定 `output_board_id`、输出节点 ID、类型、SKU ID、排序值和当前选中结果资产 ID；选择结果或调整顺序都会递增项目 revision。
- 每个 generation item 绑定一个输出节点和输出画板；重试成功时新增结果版本，不覆盖旧结果资产。
- 用户在画板版本列表中显式选择“当前预览/导出版本”。
- 从画布移除结果只解除画板引用；只有明确删除且没有任何 SKU、任务、画板或导出引用时，资产才进入软删除。
- 详情画板支持拖拽排序，详情切片和长图导出都以稳定排序值为准。

## 7. 产品素材与自动抠图

### 7.1 上传与检测

支持 JPG、PNG 和 WebP，延续 12 MB 单文件上限，并增加真实解码、动画 WebP 拒绝、最长边和总像素上限。默认安全上限为最长边 16,384 像素、总像素 40 MP，可由服务端配置收紧。

上传流程：

1. 以 `.uploading` 临时文件写入项目目录。
2. 校验魔数、声明 MIME、真实 MIME、格式、尺寸和像素量。
3. 计算 SHA-256，使用 UUID 文件名原子落盘。
4. 保留不可变原始文件，并创建供画布使用的工作资产。
5. 解码 Alpha，判断是否存在有效透明背景。
6. 生成最长边 2,048 像素的同源预览代理；Fabric 只加载代理，原图和高分辨率抠图只供服务端处理与导出。

“存在 Alpha 通道”不等于“透明背景”。处理器 v1 的确定规则是：Alpha 小于或等于 250 的像素形成与图片边缘连通的区域，且该区域至少占全部像素的 0.5%，才认定为已有透明背景。阈值属于有版本的处理器常量；全不透明 PNG、白底 JPG/PNG 和复杂背景图片都视为不透明图片。

所有画布变换保存归一化坐标，不保存预览代理的绝对像素坐标。原图、抠图和预览代理通过资产派生关系关联。

### 7.2 最终自动抠图规则

本规则覆盖此前“勾选后才抠图”的设想，界面不再提供前置启用复选框：

- 已有有效透明背景：直接使用原图工作资产，`rembg` 调用次数为 0。
- 所有不透明图片，包括白底图片：自动创建抠图任务，调用 `rembg` 的 `isnet-general-use` CPU 模型。
- 抠图结果只取 Alpha 蒙版，再应用到从原始文件解码得到的 RGB；不接受 `rembg` 重写产品内部 RGB。
- 原图和抠图结果同时保留，提供棋盘格对比、原图/抠图切换、重新抠图和回退。
- 抠图失败只影响该素材，显示错误和重试按钮，不删除原图。
- 依赖该素材的生成默认等待抠图成功；用户可以明确选择“使用原图矩形继续”，系统不得静默降级。

`rembg`、ONNX Runtime、Pillow 和模型缓存目录属于明确运行依赖。模型未下载、下载失败或运行环境不兼容时，界面必须显示可恢复错误，不能伪造透明结果。

## 8. 产品严格保真与 SKU 构图

### 8.1 严格保真的可测试定义

“严格保持原图”定义为：

- 产品图层的 RGB 内容只能来源于用户上传原图。
- 图片模型不得重绘、修复、补字、调色、滤镜化或改变包装、Logo、标签文字和外形。
- 产品主体只允许等比缩放、平移和必要的确定性旋转；禁止非等比拉伸、自由裁切、颜色调整和生成式填充。
- 自动抠图只改变 Alpha 蒙版。
- 最终导出由服务端按布局快照重建。模型背景和模型装饰永远位于锁定产品层下方；用户主动创建的可编辑文字可按显式层级位于产品上方或下方，但不会改变产品源像素。
- 缩放、旋转和最终编码会发生确定性重采样，因此不承诺导出文件与原图逐字节相同；承诺的是产品内容不经过 AI 重绘或调色。

如果需要新的产品角度，用户必须上传对应角度的产品图。系统不允许模型凭空生成角度后冒充真实产品素材。

### 8.2 模型生成策略

- 支持遮罩编辑的模型：可接收场景底图和受保护产品遮罩，只生成产品周围区域；最终仍覆盖原始产品层。
- 仅支持文生图的模型：只生成背景和场景，再由本地合成产品。
- 只有图生图但不支持安全锁区的模型：不得接收产品图去重绘主体，只能按背景生成能力使用。
- 只接受公网参考图 URL、但不能上传图片字节的第三方模型：在当前本地部署中标记为“不支持参考图”，不能向其发送 localhost 或 LAN URL。

### 8.3 SKU 规则

每个 SKU 保存稳定 SKU ID、名称、可选参考图、数量、比例和提示词。若不同 SKU 的包装或外形不同，必须上传对应 SKU 参考图；未提供 SKU 图时沿用主产品锁定素材，SKU 名称只作为项目元数据和可编辑文字，不能让模型发明不同包装。

同组 SKU 统一：

- 归一化产品槽位。
- 锚点和基线。
- 产品在画布中的相对占比。
- `contain` 等比适配规则。
- 安全区和镜头框架。
- 旋转规则和构图组布局哈希。

不同外形 SKU 放入同一归一化槽位但不拉伸。同组 SKU 即使使用不同输出比例，也由相同归一化坐标映射到各自画板。背景、光线、颜色、装饰元素和模型可以不同，不做硬性统一。

画布修改共享构图组时同步更新整组；生成提交和服务端导出时校验 `composition_group_id` 与布局哈希，防止个别 SKU 静默偏离。

## 9. 可编辑文字

- 价格、规格、促销语、卖点和其他营销文案使用独立文字图层。
- 文字图层可以编辑内容、位置、字号、颜色、对齐、行距和层级。
- 文字不随提示词发送给图片模型，也不出现在模型生成背景中。
- 项目保存文字的语义和布局；导出时由服务端把文字合成到成品。
- 文字状态保存字体资源版本、文本框宽度、显式换行、逐行位置、字号、字距、行距、对齐和基线；服务端按该布局快照渲染，不重新自动换行。服务端导出是权威结果，浏览器预览使用同一字体资源和布局数据。

## 10. 图片模型提供商

### 10.1 适配器策略

采用混合适配器架构：

1. Seedream 专用适配器。
2. OpenAI Images-compatible 适配器。
3. 通用 HTTP API 适配器。

所有适配器实现统一接口：

- 校验模型能力和生成请求。
- 构建不含日志泄密的上游请求。
- 提交同步或异步任务。
- 保存上游任务 ID和上游幂等键。
- 轮询、取消、解析结果和规范化错误。
- 返回图片字节或受控远程结果供服务端下载。

### 10.2 Seedream 5.0

- UI 名称：`Seedream 5.0 Pro（完整版）`。
- 官方模型 ID：`doubao-seedream-5-0-260128`。
- 不得误用 Lite 模型。
- 使用火山方舟/豆包图片生成 API 的专用字段、错误码和异步行为。
- 可以复用现有 `ARK_API_KEY`/`DOUBAO_API_KEY` 环境凭据，但不复用现有聊天接口配置表中的明文密钥字段。

### 10.3 通用 HTTP API

模型管理页允许配置：

- 提供商名称、Base URL、Endpoint、HTTP 方法和同步/异步模式。
- Bearer、API-Key Header 或受控 Query 参数鉴权。
- JSON 或 Multipart 请求映射。
- 固定允许变量：模型 ID、提示词、负面提示词、数量、比例、宽高、参考图片字节、参考图片 Base64、遮罩字节和种子。
- 同步响应中的二进制、Base64 或图片 URL字段。
- 异步响应中的任务 ID、状态、错误、结果和轮询间隔字段路径。
- 超时、最大响应大小和供应商并发限制。

通用映射只能使用声明式字段路径和固定变量插值，禁止执行模板代码、表达式或脚本。特殊鉴权和协议通过新的代码适配器实现。

### 10.4 能力清单

每个模型声明：

- 文生图、图生图、遮罩编辑。
- 支持的比例、分辨率和数量。
- 最大参考图数量和参考图传输方式。
- 同步或异步协议。
- 是否支持取消和幂等键。
- 单模型并发限制和可选价格元数据。

项目内只选择已启用模型。完整套图模式按输出类型选择模型，高级模式按生成节点选择模型。界面根据能力禁用不支持的控件并解释原因，不允许静默删除用户参数或自动切换模型。

## 11. 数据模型

新增独立 `canvas_models.py` 并在 `database.init_db()` 中显式导入。核心表如下：

### 11.1 `canvas_projects`

- UUID 主键、名称、状态。
- `semantic_state`、`layout_state`、`schema_version`。
- `revision` 乐观锁。
- 创建、更新、归档时间。

### 11.2 `canvas_project_skus`

- 项目 FK、稳定 SKU ID、名称、排序。
- 参考源资产、提示词和 SKU 配置。
- SKU 后续改名不影响历史生成，因为任务保存名称快照。
- 本表是 SKU 业务数据的唯一权威；项目语义图只保存 SKU ID引用。SKU CRUD 与画布状态保存共用项目 `revision`，每次修改都递增 revision。

### 11.3 `canvas_assets`

- 项目 FK、资产类型、受控相对路径、原文件名、MIME、字节数、宽高和 SHA-256。
- 类型覆盖原图、工作图、2,048px 预览代理、抠图、生成背景、最终合成和导出文件。
- 源资产关系、透明状态、处理器版本、元数据和软删除时间。

### 11.4 `image_provider_connections`

- 名称、适配器类型、Base URL、鉴权类型、加密凭据和启用状态。
- 配置版本、创建和更新时间。

### 11.5 `image_model_profiles`

- Provider FK、模型 ID、显示名和能力清单。
- 请求映射、响应映射、协议、超时、轮询和并发限制。
- 配置版本；历史任务使用保存的非密钥配置快照。

### 11.6 `canvas_asset_operations`

- 项目、源资产、操作类型、状态和尝试次数。
- `lease_expires_at`、`heartbeat_at`、`next_attempt_at` 和 `cancel_requested_at`。
- 输出资产、错误、创建、开始和完成时间。
- 用于自动抠图、合成和导出等本地任务。

### 11.7 `canvas_generations`

- 项目、完整套图/高级节点模式、状态和项目 revision。
- 请求快照、请求指纹、幂等键、总数、成功数、失败数和取消标记。
- 租约、创建、开始和完成时间。
- `(project_id, idempotency_key)` 唯一约束。

### 11.8 `canvas_generation_items`

- Generation FK、输出类型、SKU ID与名称快照、序号、比例和尺寸。
- 输出节点 ID、输出画板 ID和提交时的画板排序快照。画板当前选中结果只保存在项目语义状态中，不在 Item 重复保存。
- 提示词、构图组、布局哈希和布局快照。
- Provider ID、Model Profile ID、模型配置版本、提交时非密钥配置快照、状态、最终背景资产和最终合成资产。
- 当前错误、尝试次数和时间戳。

### 11.9 `canvas_generation_item_inputs`

- Item FK、资产 FK、输入角色、顺序和输入资产 SHA-256 快照。
- 输入角色覆盖主产品、SKU 产品、角度参考、遮罩和其他明确参考图。
- 数据库外键阻止仍被生成任务引用的源资产被删除。

### 11.10 `canvas_generation_attempts`

- 每一次真正上游调用的独立记录。
- `attempt_no`、Provider、模型、非密钥配置快照、`provider_request_id`、`external_task_id` 和幂等键。
- `lease_expires_at`、`heartbeat_at`、`next_poll_at` 和 `submitted_at`；调度器以 Attempt 为远程领取粒度。
- 状态、开始/完成时间、用量、输出资产、规范化错误和原始安全错误码。
- 单张重试新增 attempt，不覆盖之前的成功或失败记录。

### 11.11 `canvas_events`

- 单调递增事件 ID、项目 FK、可选 Operation/Generation/Item FK、事件类型、安全 Payload 和创建时间。
- 项目级 SSE 按事件 ID重放；Payload 只保存状态引用和脱敏摘要。
- 每个项目至少保留最近 10,000 个事件或 7 天事件。客户端请求的事件已被清理时，服务端先发送完整数据库快照再继续增量事件。

图片文件保存到：

```text
data/canvas_projects/{project_uuid}/
  source/
  working/
  cutout/
  generated/
  composed/
  exports/
  tmp/
```

数据库只保存受控相对路径和元数据。所有路径访问都执行项目根目录 containment 校验，所有远程图片先下载并验证后保存为同源资产。

Canvas 新表加入 `_schema_migration_required()` 的必需表集合，旧数据库升级前继续使用现有 SQLite 一致性备份机制。初始化、重复初始化、索引、外键和级联行为必须有迁移回归测试。

Provider 和 Model 被项目或历史任务引用后只能软禁用，不能硬删除。历史 Attempt 使用提交时的非密钥配置快照，但每次恢复仍必须通过当前 SSRF 策略并取得当前有效凭据，历史配置不能绕过新的安全规则。

## 12. API 设计

### 12.1 项目与状态

- `GET /api/canvas/projects`
- `POST /api/canvas/projects`
- `GET /api/canvas/projects/{project_id}`
- `PATCH /api/canvas/projects/{project_id}`
- `PUT /api/canvas/projects/{project_id}/state`
- `POST /api/canvas/projects/{project_id}/archive`
- `POST /api/canvas/projects/{project_id}/restore`
- `DELETE /api/canvas/projects/{project_id}`

保存状态请求必须带当前 `revision`。所有写入 Schema 使用 Pydantic `extra="forbid"`，限制名称、提示词、节点数量和 JSON 大小。

默认限制为：项目状态 JSON 5 MB、单提示词 4,000 字符、项目节点 500 个、连线 1,000 条、文字总量 100,000 字符、单输出组 20 张、单次 Generation 合计 50 张。Canvas 12 MB 单文件上传对应的 Multipart 请求体上限设为 14 MB，并在现有请求体限制函数中为这些路由单独配置。

### 12.2 SKU 与素材

- `GET/POST /api/canvas/projects/{project_id}/skus`
- `PATCH/DELETE /api/canvas/projects/{project_id}/skus/{sku_id}`
- `GET/POST /api/canvas/projects/{project_id}/assets`
- `GET /api/canvas/assets/{asset_id}/content`
- `GET /api/canvas/assets/{asset_id}/content?variant=preview`
- `DELETE /api/canvas/assets/{asset_id}`
- `POST /api/canvas/assets/{asset_id}/cutout/retry`
- `GET /api/canvas/projects/{project_id}/operations`
- `GET /api/canvas/operations/{operation_id}`
- `POST /api/canvas/operations/{operation_id}/retry`

文件只能通过数据库资产 ID访问；接口不接受调用方提交任意服务器路径。仍被 SKU、任务、画板或导出引用的资产拒绝删除。

### 12.3 模型管理

- `GET/POST /api/canvas/model-providers`
- `PATCH/DELETE /api/canvas/model-providers/{provider_id}`
- `POST /api/canvas/model-providers/{provider_id}/test`
- `GET/POST /api/canvas/model-providers/{provider_id}/models`
- `PATCH /api/canvas/models/{model_profile_id}`

提供商是服务端全局目录，项目只保存 Provider/Model ID和配置版本，不复制密钥或 Base URL。

Provider/Model `DELETE` 的语义是软禁用；历史引用和配置版本继续保留。测试连接优先使用免费的元数据/模型列表接口；如果只能通过出图验证，请求必须带 `allow_paid_probe=true`，界面二次确认图片数量和可能费用。

### 12.4 生成、事件和导出

- `POST /api/canvas/projects/{project_id}/generations`
- `GET /api/canvas/generations/{generation_id}`
- `GET /api/canvas/generations/{generation_id}/events`
- `GET /api/canvas/projects/{project_id}/events`
- `POST /api/canvas/generations/{generation_id}/cancel`
- `POST /api/canvas/generation-items/{item_id}/retry`
- `POST /api/canvas/generation-items/{item_id}/resolve-unknown`
- `POST /api/canvas/projects/{project_id}/exports`
- `GET /api/canvas/assets/{asset_id}/download`

项目级 SSE 统一覆盖上传检测、抠图、生成、合成和导出。SSE 支持 `Last-Event-ID`，从 `canvas_events` 重放；事件缺口已被清理时先返回完整任务快照，再继续消费增量事件。Generation 事件端点是同一事件源的任务过滤视图。

导出请求也携带幂等键并创建 `canvas_asset_operations`；客户端通过 Operation API或项目事件流查询进度。

### 12.5 Canvas 访问会话

- `GET /api/canvas/access/status`
- `POST /api/canvas/access/unlock`
- `POST /api/canvas/access/lock`

解锁对话框只向 `/unlock` 提交一次 `CANVAS_ACCESS_TOKEN`。服务端校验后设置不含原始 Token 的 HttpOnly、SameSite=Strict 浏览器会话 Cookie，HTTPS 时同时设置 Secure；Token 不进入项目状态、日志、`localStorage` 或 `sessionStorage`。401/403 时前端保留未提交配置并重新打开解锁对话框。

## 13. 任务队列、幂等与恢复

### 13.1 并发

- 使用 SQLite 持久队列和进程内调度器，适配当前单实例本地部署。
- 同一项目同时只运行一个生成任务。
- 全局图片生成默认并发为 1，可由服务端配置。
- `rembg` 使用独立 CPU 队列，默认并发为 1，不能阻塞 FastAPI 事件循环。
- 通过短事务领取任务和更新租约；远程调用期间不持有 SQLite Session。
- Worker 的启动、停止、租约回收和恢复挂入 FastAPI lifespan；服务关闭时停止领取新任务并尽力落盘当前阶段。

### 13.2 状态

生成任务状态：

`queued`、`running`、`partially_failed`、`succeeded`、`failed`、`cancel_requested`、`cancelled`、`interrupted`、`unknown`。

逐图 attempt 状态：

`queued`、`submitting`、`polling`、`succeeded`、`failed`、`cancel_requested`、`cancelled`、`unknown`。

合法转换由服务层集中定义：Attempt 从 `queued` 进入 `submitting`，同步成功可直接进入 `succeeded`，异步提交进入 `polling`，再进入终态；中断窗口进入 `unknown`。Generation 根据所有 Item 聚合：存在活动项时为 `running`，全部成功为 `succeeded`，成功与失败/未知并存为 `partially_failed`，无成功且存在未知项为 `unknown`，无成功且全部失败为 `failed`，取消完成为 `cancelled`。`partially_failed` 创建重试后可回到 `running`。`unknown` 在用户处理前视为终态但阻止归档和删除；用户可将其标记为放弃并归入失败，或明确创建新 attempt。

### 13.3 幂等与逐图重试

- 创建生成任务必须携带客户端幂等键；同项目相同键且请求指纹一致时返回既有任务，相同键但指纹不同时返回 `409`。
- 请求指纹覆盖项目 revision、Provider/Model 配置版本、提示词、布局快照、输出规格和全部输入资产 SHA-256。
- 供应商支持幂等键时，attempt 必须透传稳定上游幂等键。
- 同一 Generation 的重试接口不重跑成功项；部分失败只为失败项创建新的 attempt。用户仍可显式新建另一次 Generation。
- 上游不支持幂等时，界面明确说明无法绝对保证供应商不重复计费。
- 没有上游幂等能力时，系统禁止自动重新提交付费请求；只允许自动重试轮询、结果下载和本地处理。

### 13.4 服务重启恢复

- 尚未提交上游的排队项可安全恢复排队。
- 本地抠图、合成和导出任务租约过期后可重新领取。
- 已保存 `external_task_id` 的异步任务只恢复轮询，绝不重新提交。
- 同步付费请求若在“请求已发出、响应未落盘”阶段中断，标记为 `unknown`，不自动重试；由用户明确确认后创建新 attempt。
- 异步提交已被上游接收但 `external_task_id` 尚未落库时同样标记为 `unknown`。供应商支持幂等查询时用原键查询恢复；不支持时不得自动重提。
- 已完成资产和成功项不因服务重启而重建。

### 13.5 取消

- 支持取消的供应商：调用上游取消并记录结果。
- 不支持取消的供应商：取消尚未提交项，对已提交异步项继续低频轮询直到上游终态，以保留最终结果和费用状态；界面显示“供应商可能继续执行”并明确提示仍可能产生费用。
- 取消不删除已成功结果。

## 14. 权威合成与导出

Fabric 只负责交互预览。最终合成在服务端执行，输入为经过校验的项目资产、归一化布局快照、文字层和输出尺寸。

合成使用受控层级带：

1. 模型生成背景与模型装饰层，永远位于产品下方。
2. 用户明确设置为“产品下方”的可编辑文字层。
3. 锁定产品图层，RGB只来自原图。
4. 用户明确设置为“产品上方”的可编辑文字层。

模型输出永远不能覆盖产品；用户主动放在产品上方的文字可能遮挡产品，但不会修改产品源像素。Fabric 预览和服务端导出执行相同层级规则。

产品缩放使用固定、高质量且可测试的重采样方式；同一布局和输入应产生确定性输出。文字按持久化的逐行布局快照渲染，服务端不重新自动换行。

导出支持：

- 单张 PNG、JPEG、WebP。
- 主图、SKU 图、详情图分类 ZIP。
- 详情图按画板排序导出为独立切片。
- 详情画板按显式顺序拼接成长图。
- 文件名按“项目/图片类型/SKU/序号”生成并清理非法字符。
- 项目中保持可编辑文字；只在导出成品中栅格化。
- 无系统水印。

第三方返回图先由服务端下载到项目资产目录，再以同源 URL供 Fabric 预览，避免跨域污染、临时 URL过期和浏览器导出不一致。

## 15. 错误处理与安全边界

### 15.1 文件安全

- 校验扩展名、声明 MIME、魔数、真实解码、尺寸和像素量。
- 拒绝动画 WebP、解压炸弹和超限远程图片。
- 上游单图下载默认限制 25 MB，可由服务端收紧。
- 上传、预览、下载、导出和删除都执行根目录 containment 校验。
- 项目数据目录加入 `.gitignore`，备份策略覆盖数据库和 `data/canvas_projects/`。
- `.uploading` 和 `tmp` 中超过 24 小时的孤儿文件由本地清理任务删除。
- 默认每项目配额 5 GB、Canvas 总配额 20 GB，并要求写入后至少保留 2 GB磁盘空间；三项均可由服务端配置。达到阈值时停止新上传和生成，但不删除已有结果。

### 15.2 第三方 HTTP 与 SSRF

- Base URL默认只允许 HTTPS，Host 必须进入管理员维护的精确白名单；Endpoint 必须是相对路径，禁止用户信息、Fragment 和绝对 URL。企业内网 HTTP只有在精确私网白名单命中且显式启用 `CANVAS_ALLOW_INSECURE_PROVIDER_HTTP=1` 时才允许。
- Provider 提交请求不跟随重定向，防止 Bearer、Header 或 Query 密钥泄漏。
- 默认拒绝回环、私网、链路本地、保留地址和云元数据地址。企业内网第三方 API只能通过独立的精确私网 Host/IP白名单显式放行；云元数据地址始终禁止。
- 连接前解析并校验 DNS，将连接固定到已验证 IP，同时保留原 Host/TLS SNI；解析或证书不匹配时拒绝请求，以降低 DNS 重绑定风险。
- 远程结果图片最多跟随两次重定向，每一跳重新执行协议、Host、DNS 和 IP校验，且绝不携带 Provider 鉴权。
- 限制超时、响应字节数和允许的 Content-Type，不直接把远程 URL交给浏览器。
- 日志不记录 Authorization、API-Key、Query 密钥、完整请求头或未脱敏上游响应。

### 15.3 凭据

- 不复用现有 `AIInterfaceSetting.api_key_secret` 明文字段。
- UI 保存的图片模型密钥使用 `cryptography.fernet.Fernet` 加密；`CANVAS_PROVIDER_SECRET_KEY` 是数据库外的 URL-safe 32-byte 主密钥。数据库保存带版本的 Fernet Token，主密钥缺失时拒绝保存，不能降级为明文。
- 环境变量凭据是首选方式，Seedream 可使用现有 Ark/豆包环境变量。
- API 只返回“是否已配置”和脱敏摘要；项目 JSON、任务快照、日志和导出文件永远不包含明文密钥。
- 解密失败时软禁用 Provider 并显示配置错误，不清空或覆盖原密文。初版不提供在线密钥轮换；备份与恢复必须同时保护数据库和独立 `.env` 主密钥。

### 15.4 局域网付费调用保护

当前应用的全局登录已停用。本功能不恢复全站登录，但模型管理和所有可能产生费用的生成、取消、重试接口必须增加独立 `CANVAS_ACCESS_TOKEN` 保护：

- 仅浏览、编辑和本地保存项目不触发付费模型时，可按现有局域网访问策略运行。
- Provider/Model 新增、修改、软删除、测试，以及生成、取消和重试都使用同一个访问依赖并要求已解锁 HttpOnly 会话 Cookie。
- 未配置 `CANVAS_ACCESS_TOKEN` 时，项目页面与本地编辑仍可打开，但上述受保护接口返回 `503`；已配置但未解锁时返回 `401`。
- 项目隔离是数据组织，不是用户权限隔离；现有局域网中的其他用户仍可能查看和编辑项目。该 Token 只保护密钥管理和可能产生费用的操作。
- 非回环 HTTP无法提供传输层机密性，界面必须提示在受信网络中使用，并推荐通过 HTTPS反向代理访问；HTTPS会话 Cookie设置 Secure。

### 15.5 上游错误

- 超时、限流、内容审核、能力不支持、空结果、下载失败和响应结构变化按统一错误码映射到具体逐图 item。
- 不使用占位假图冒充成功结果。
- 失败项保留完整安全错误摘要和可重试性；供应商秘密或原始敏感响应不入库。

## 16. 测试设计

### 16.1 后端单元与迁移测试

- 项目、SKU、资产、Provider、Generation 和 Attempt 表创建、索引、外键和级联。
- 旧数据库升级前备份、重复 `init_db()` 和缺表自愈。
- revision 冲突返回 `409`。
- 透明图跳过抠图；白底图和复杂背景不透明图各调用一次抠图。
- 删除或断开高级模式的自动抠图状态节点不能绕过不透明素材的自动抠图。
- 抠图失败保留原图；抠图前后可见产品区域 RGB 来源不变。
- 文件类型、动画图片、像素上限、路径越界和原子落盘。
- Provider 能力校验、同步结果、异步轮询、错误映射和配置版本快照。
- SSRF、DNS 重绑定、危险重定向、远程 MIME和下载上限。
- 凭据密文落库，API、日志、任务快照和项目 JSON无明文。
- 幂等键、请求指纹、租约、取消、逐图重试和任务恢复矩阵。
- 同组 SKU 的构图组 ID和布局哈希一致。
- 最终合成保证所有模型层位于产品下方，并按显式层级正确处理产品上下方的用户文字。
- 内置 Seedream 模型 ID精确等于 `doubao-seedream-5-0-260128`，Lite ID不能进入该模型配置。
- 跨项目引用另一个项目的 Asset、SKU、Generation Item或 Export ID被拒绝。
- 上游已接收异步任务但任务 ID未落库时进入 `unknown`，不能自动重提。
- 项目事件可从持久事件 ID重放，事件清理后可回退到完整快照。
- 文字分别位于产品下方和用户显式置于产品上方时，服务端按相同层级导出；模型层始终位于产品下方。

### 16.2 前端单元测试

- TypeScript 类型检查和 Vite 正式构建。
- 完整套图与高级节点共享 reducer 状态。
- 高级自定义拓扑保护与显式重建。
- 新项目无默认输出选择。
- 模型能力禁用和不支持原因展示。
- 自动保存、离线、409 冲突和项目切换刷新。
- 抠图状态映射、原图/结果切换和重新抠图。
- 2,048px 预览代理与归一化坐标映射；高分辨率原图不加载进 Fabric。
- 构图组同步、文字层和导出配置。
- reducer 撤销/重做范围和项目切换清空规则。
- 采用 Vitest 执行 `test:canvas`。
- Fabric 通过 `CanvasAdapter` mock 测试，业务状态测试不直接依赖浏览器 Canvas。

### 16.3 浏览器端到端测试

- `/app` 画布入口、`/app/canvas` 空状态和项目路由。
- 新建、切换、重命名、归档、恢复和删除项目。
- 透明图跳过抠图；白底和复杂背景图自动抠图。
- 完整套图与高级节点往返不丢数据。
- 未选输出或模型时禁止生成。
- 同组 SKU 构图锁。
- 模型能力限制、进度、取消、部分失败和单项重试。
- 自动保存后刷新恢复，模拟服务重启后任务恢复。
- 单张、ZIP、详情切片和长图导出。
- 抠图、生成、合成和导出 Operation 的项目级 SSE 断线重连。
- 访问 Token 解锁、401/503 状态和未提交配置保留。
- Playwright 启动服务前执行 `build:canvas`，防止测试旧构建产物。

自动化测试全部使用本地假 Provider，不调用付费模型。发布前人工冒烟分别调用一次 Seedream 5.0 完整版和一个第三方 API，并记录模型 ID、任务状态、生成数量和导出结果。

### 16.4 仓库验证门槛

实施完成后至少执行：

```powershell
python -m unittest tests.test_canvas_projects tests.test_canvas_assets tests.test_canvas_providers tests.test_canvas_generations tests.test_canvas_exports -v
python -m unittest discover -s tests -v
python -m compileall -q .
npm.cmd run typecheck:canvas
npm.cmd run test:canvas
npm.cmd run build:canvas
npm.cmd run test:e2e
git diff --check
```

随后重启受监督的 Uvicorn 子进程，验证 `/healthz`、`/app`、`/app/canvas`、真实项目页、SSE 和文件导出。

## 17. 主要文件与依赖影响

预计新增或修改：

- `frontend/canvas/`：TypeScript 应用、状态、DOM 组件、Fabric 适配层和测试。
- `templates/canvas.html`：独立工作区入口。
- `static/canvas/`：Vite 构建产物。
- `main.py`：页面路由、静态入口和 Canvas Router 注册。
- `routers/canvas/`：项目、素材、模型、生成、事件和导出 API。
- `canvas_models.py`：Canvas 领域 SQLAlchemy 模型。
- `services/canvas/`：存储、抠图、Provider、队列、合成、导出和安全模块。
- `database.py`：显式模型导入、必需表检测和兼容迁移。
- `requirements.txt`：Pillow、`rembg` CPU依赖、ONNX Runtime 和凭据加密库。
- `package.json`：Fabric.js、Vite、TypeScript、Vitest和前端测试脚本。
- `tests/test_canvas_*.py` 与 `e2e/`：后端、迁移和浏览器回归。
- `.gitignore`：`data/canvas_projects/*`、模型缓存和临时导出。
- 现有请求体限制模块：Canvas Multipart 14 MB、状态 JSON 5 MB等路由级限制。

新增 npm 命令：

- `dev:canvas`
- `build:canvas`
- `typecheck:canvas`
- `test:canvas`

## 18. 交付切片

为降低风险，按一个设计、四个可独立验收的切片实施：

1. 项目与画布基础：独立路由、项目侧栏、状态模型、Fabric 适配、自动保存和资产存储。
2. 产品保真基础：透明检测、自动抠图、原图/结果切换、锁定产品层、构图组和服务端合成。
3. 图片生成：Seedream 5.0、任务队列、完整套图和高级节点、逐图状态与恢复。
4. 第三方与交付：OpenAI-compatible、通用 HTTP API、模型管理、安全加固、批量导出和完整 E2E。

每个切片都必须形成独立实施计划和验收门，通过自己的测试后再进入下一切片；最终只以完整验收标准判定功能完成。

## 19. 开源参考与选型依据

- [Jaaz](https://github.com/11cafe/jaaz)：参考项目化 AI 画布、素材与生成流程的交互组织，不直接复制实现。
- [Fabric.js](https://github.com/fabricjs/fabric.js/) 与 [核心概念](https://fabricjs.com/docs/core-concepts/)：作为 MIT 许可的画布对象、变换、分组和序列化基础。
- [tldraw image pipeline](https://tldraw.dev/starter-kits/image-pipeline)：参考图像管线的节点交互思路；因其当前生产许可要求，本项目不采用 tldraw 运行时代码。
- [Konva](https://github.com/konvajs/konva)：作为备选画布方案评估；最终选择更贴合对象编辑和导出的 Fabric.js。
- [rembg](https://github.com/danielgatis/rembg)：用于本地 CPU 自动抠图；原始产品 RGB仍由本项目独立保留和合成。
- [Seedream 模型文档](https://www.volcengine.com/docs/82379/1330310) 与 [图片生成示例](https://www.volcengine.com/docs/82379/1824121)：用于锁定 Seedream 5.0 完整版模型 ID和接口行为。

## 20. 核心风险与处理

- 自动抠图可能误删轮廓：保留原图、棋盘格对比、重新抠图和明确回退；当前版本不加入手工蒙版画笔。
- 图片模型可能重绘包装：模型只生成受控背景，服务端最终覆盖锁定产品层。
- 第三方 API 差异过大：通用适配器覆盖常见 HTTP 协议，特殊协议通过独立适配器扩展。
- 同步请求中断可能重复计费：标记 `unknown`，不自动重试，并尽可能透传上游幂等键。
- 项目 JSON和图片体积过大：数据库保存结构化状态和文件元数据，图片仅存受控文件系统。
- 多标签页覆盖：revision 乐观锁和明确冲突提示。
- 浏览器导出与服务端结果不一致：浏览器只预览，服务端使用相同字体、布局快照和固定合成顺序权威导出。
- 局域网匿名调用付费模型：Provider 管理和付费操作使用独立 Canvas 访问 Token，缺少保护时失败关闭。
