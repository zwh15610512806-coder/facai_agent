# 法采新媒体运营 Agent

法采新媒体运营 Agent 是一个本地运行的短视频脚本生成工具，面向法采烘焙原材料运营团队使用。系统把产品资料、产品卖点、价格体系、脚本模板和 AI 生成能力整合在一起，用于快速生成抖音/短视频带货脚本。

## 主要功能

- 产品库管理：维护法采产品、品类、价格、卖点和产品资料。
- 脚本生成：按“选择产品 -> 选择视频类型 -> 生成脚本”的流程生成短视频脚本。
- 脚本改写：基于参考脚本和目标产品生成更贴近产品卖点的新脚本。
- 模板库：管理法采高成交脚本和其他参考脚本。
- 产品资料同步：从本地产品资料、2026 产品知识库、价格表中导入产品和 SKU 售价。
- 关键词搜索：产品搜索按产品名称精确匹配，避免无关产品混入。
- 向量检索：使用 ChromaDB + 火山方舟 embedding 为产品和脚本提供语义检索；显式语义检索/重建失败时返回清晰错误，脚本生成等后台参考检索可继续降级到关键词逻辑。
- 本机服务守护：提供 Windows 登录自启和看门狗脚本，服务异常时自动重启。

## 技术栈

- Python 3.12
- FastAPI
- SQLite
- SQLAlchemy
- Jinja2
- ChromaDB
- DeepSeek API
- OpenPyXL / Pandas

## 目录说明

```text
.
├── main.py                      # FastAPI 应用入口
├── models.py                    # SQLAlchemy 数据模型
├── schemas.py                   # Pydantic 数据结构
├── config.py                    # 环境变量和应用配置
├── import_materials.py          # 产品资料、脚本、价格体系导入逻辑
├── routers/                     # API 路由
├── services/                    # 脚本生成、改写、产品详情等服务
├── templates/                   # 页面模板
├── static/                      # 前端静态资源
├── vector_store/                # ChromaDB 向量库封装
├── tests/                       # 单元测试
├── scripts/                     # Windows 自启和看门狗脚本
└── data/                        # 本地运行数据目录，实际数据不提交 Git
```

## 本地运行

先安装依赖：

```bash
pip install -r requirements.txt
```

创建 `.env`：

```env
DEEPSEEK_API_KEY=你的 DeepSeek Key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
ARK_API_KEY=你的火山方舟 API Key
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
ARK_MODEL=ep-20260703160153-h5cx5
EMBEDDING_PROVIDER=volcengine_ark
EMBEDDING_MODEL_NAME=ark-4e8d208b-a896-43b4-9b77-eda0ceac0370-0a2ef
# 可选：需要单独隔离向量凭据时再配置；默认复用 ARK_API_KEY/ARK_BASE_URL 或 DOUBAO_API_KEY/DOUBAO_BASE_URL
# EMBEDDING_API_KEY=你的火山方舟 Embedding API Key
# EMBEDDING_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
DATABASE_URL=sqlite:///./data/script_agent.db
CHROMA_PERSIST_DIR=./data/chroma_db
```

更换 embedding 模型或从旧索引迁移后，需要显式重建产品和脚本 Chroma collection，避免旧向量与新向量混用：

```bash
curl -X POST http://localhost:8001/api/products/reindex
curl -X POST http://localhost:8001/api/templates/reindex
```

如果重建失败，请优先检查 `ARK_API_KEY`、`ARK_BASE_URL`、`EMBEDDING_MODEL_NAME` 和火山方舟 endpoint 权限。`EMBEDDING_API_KEY` / `EMBEDDING_BASE_URL` 只在需要为向量服务单独配置凭据时使用。

局域网上线前必须设置管理员口令；设置后 `/app/*` 和 `/api/*` 会要求登录或携带 `Authorization: Bearer <口令>`：

```env
FACAI_ADMIN_TOKEN=请换成高强度随机口令
```

AI 配置里的自定义 Base URL 默认只允许已知供应商域名。确实需要新增供应商网关时，再显式加入允许列表：

```env
AI_BASE_URL_ALLOWLIST=api.deepseek.com,dashscope.aliyuncs.com,api.minimax.io,open.bigmodel.cn
```

启动服务：

```bash
python main.py
```

默认访问地址：

```text
http://localhost:8001/app
```

局域网访问时，使用本机局域网 IP：

```text
http://你的局域网IP:8001/app
```

## Windows 稳定运行

项目提供了本机服务器守护脚本：

```text
scripts/facai_agent_service.py
scripts/start-facai-agent-service.cmd
scripts/facai-agent-startup.vbs
scripts/install-facai-agent-startup.ps1
scripts/uninstall-facai-agent-startup.ps1
```

安装登录自启：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install-facai-agent-startup.ps1
```

卸载登录自启：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\uninstall-facai-agent-startup.ps1
```

看门狗会监听 `8001` 端口，服务异常时自动重启。电脑关机期间服务仍然不可用；重启后需要登录 Windows，服务才会自动启动。

## 数据与备份

以下内容不会提交到 GitHub，需要单独备份：

- `.env`
- `data/script_agent.db`
- `data/chroma_db/`
- `data/models/`
- `data/product_files/`
- `data/uploads/`
- `资料/`
- `logs/`

建议定期备份：

```text
data/script_agent.db
data/chroma_db/
data/product_files/
资料/
.env
```

## 导入资料

导入产品、脚本、价格体系：

```bash
python import_materials.py
```

导入前预检查：

```bash
python import_materials.py --dry-run
```

导入逻辑会读取本地 `资料/` 目录中的产品资料、脚本表和价格体系文件。由于这些资料通常包含业务数据，默认不提交到 Git。

## 测试

运行全部测试：

```bash
python -m unittest discover -s tests -v
```

当前测试覆盖产品导入、价格同步、产品详情、页面结构、搜索逻辑、脚本改写和高成交筛选等关键行为。

## Git 使用

常用提交流程：

```bash
git status
git add .
git commit -m "说明本次修改"
git push
```

当前远程仓库：

```text
https://github.com/zwh15610512806-coder/-AGENT
```

## 安全注意事项

- 不要把 `.env` 上传到 GitHub。
- 不要把数据库、产品资料、价格表、原始业务资料上传到公开仓库。
- 如需公网访问，建议加登录保护后再使用 Cloudflare Tunnel、反向代理或云服务器部署。
- 当前项目适合本机或局域网内部使用；正式长期使用建议迁移到云服务器，并配置 HTTPS、进程守护和自动备份。
