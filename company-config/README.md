# 公司配置说明

本目录包含公司专用的配置文件，需要部署到对应位置才能生效。

## 文件说明

| 文件 | 目标位置 | 用途 |
|------|----------|------|
| `ABU.md` | `{工作目录}/.abu/ABU.md` | 项目规则，Agent 自动遵守 |
| `SOUL.md` | `~/.abu/SOUL.md` | 性格设定，控制语气和风格 |
| `memories/*.md` | `~/.abu/memory/` | 预设记忆，AI 查资料时参考 |

## 安装方式

### 1. 项目规则
```bash
# 在项目工作目录下
mkdir -p .abu
cp company-config/ABU.md .abu/ABU.md
```

### 2. 性格设定
```bash
cp company-config/SOUL.md ~/.abu/SOUL.md
```

### 3. 预设记忆
```bash
mkdir -p ~/.abu/memory
cp company-config/memories/*.md ~/.abu/memory/
```

## 自定义
请根据公司实际情况修改以上文件中的内容，特别是：
- `memories/project-context.md` — 填入实际项目信息
- `memories/team-structure.md` — 填入实际团队架构
- `memories/meeting-cadence.md` — 填入实际会议安排
- `ABU.md` — 调整知识来源的 Space ID 和 Base Token
