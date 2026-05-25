---
name: lark-task-manager
description: |
  管理飞书任务。查看、创建、更新待办事项，跟踪任务进度。
  帮助用户高效管理个人和团队任务。
trigger: |
  用户提到任务、待办、todo、task、"我的任务"、"有什么要做的"、"创建任务"、
  "完成任务"、"任务进度"等
do-not-trigger: |
  用户只是在聊天中提到"任务"这个词但不涉及实际操作
user-invocable: true
argument-hint: <操作类型和内容>
allowed-tools:
  - lark_get_my_tasks
  - lark_create_task
  - lark_update_task
  - lark_get_calendar_events
tags:
  - task
  - todo
  - 任务
  - 待办
---

# 任务管理

帮助用户管理飞书任务系统中的待办事项。

## 工作流程

### 查看任务
使用 `lark_get_my_tasks()` 获取当前任务列表。
- 默认显示待处理的任务
- 可按状态筛选：`status: 'pending'` 或 `'completed'`
- 可按截止日期筛选：`due_date_before: 'YYYY-MM-DD'`

### 创建任务
使用 `lark_create_task(title, description?, due_date?, assignee?)` 创建新任务。
- 标题要简洁明确（如"完成Q2产品需求文档"）
- 描述包含任务背景、验收标准
- 截止日期格式：YYYY-MM-DD
- 给出负责人后可分配

### 更新任务
使用 `lark_update_task(task_id, status?, description?, due_date?)` 更新任务。
- 完成任务：`status: 'completed'`
- 修改截止日期
- 补充描述

### 任务分析
从会议纪要和日历中提取潜在任务：
1. 查看最近的会议纪要，提取未完成的行动项
2. 查看日历中即将到来的截止日期
3. 列出所有待办，按优先级排序
4. 发现冲突或遗漏时主动提醒

## 输出格式

```markdown
## 任务总览 — YYYY年MM月DD日

### 📋 待处理（X项）
| 优先级 | 任务 | 截止日期 | 来源 |
|--------|------|----------|------|
| 🔴 高 | 完成Q2 PRD | 3月15日 | 周会纪要 |
| 🟡 中 | 更新技术文档 | 3月20日 | 自建 |

### ✅ 今日截止
- 完成Q2 PRD — 今天截止！

### 📊 本周完成
- 完成了X项任务
```

## 注意事项
- 创建任务前先检查是否有重复
- 任务标题要包含关键动词（完成/对接/提交/评审）
- 提醒即将到期或已逾期的任务
