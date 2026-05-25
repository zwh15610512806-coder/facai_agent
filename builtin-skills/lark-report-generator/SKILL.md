---
name: lark-report-generator
description: |
  生成工作报告（日报/周报/月报）。自动聚合飞书日历、任务和会议数据，
  生成结构化的工作汇报，可用于发送给上级或团队。
trigger: |
  用户要求生成日报、周报、月报、工作总结、工作汇报、"今天干了什么"、
  "这周做了什么"、"写周报"、"report"等
do-not-trigger: |
  用户只是聊天中提到这些词但没有实际生成报告的意图
user-invocable: true
argument-hint: <报告类型（日报/周报）和时间范围>
allowed-tools:
  - lark_get_calendar_events
  - lark_get_my_tasks
  - lark_list_meetings
  - lark_get_meeting_minutes
  - write_file
tags:
  - report
  - daily
  - weekly
  - 日报
  - 周报
---

# 工作报告生成

自动聚合多个数据源，生成结构化工作报告。

## 工作流程

### 第一步：确定时间范围
- **日报**：今天（或昨天，如果是早上生成）
- **周报**：本周一至周五（或上周一至周五）
- **月报**：本月 1 日至今

### 第二步：并行拉取数据
同时调用以下工具，不要串行：
1. `lark_get_calendar_events(start_date, end_date)` — 获取日程
2. `lark_get_my_tasks()` — 获取任务（筛选完成时间和截止时间在范围内的）
3. `lark_list_meetings(start_date, end_date)` — 获取会议列表

### 第三步：获取会议详情
对于重要会议（标题包含关键词或参与人数较多），调用 `lark_get_meeting_minutes(meeting_id)` 获取要点。

### 第四步：组织报告
按以下结构生成：

```markdown
## [日报/周报] — YYYY年MM月DD日 [— MM月DD日]

### 一、本周完成的工作
1. [项目/模块] 完成XX功能开发，已提测
2. [项目/模块] 对接XX接口，完成联调
3. ...

### 二、关键成果
- XX项目上线，日均UV提升15%
- 完成Q2产品需求文档评审

### 三、会议与沟通
- 周一：[会议主题] — 确定了XX方案
- 周三：[会议主题] — 对齐了XX进度
- ...

### 四、待办与下周计划
- [ ] XX项目性能优化 — 预计下周三完成
- [ ] XX文档更新 — 下周启动
- ...

### 五、遇到的问题/需要支持
- XX项目需要设计资源支持
- ...
```

## 输出选项
- 直接展示在对话中
- 如果用户要求保存，使用 `write_file` 保存为 Markdown 文件
- 如果用户要求发送，可以建议复制内容或通过飞书发送

## 注意事项
- 数据真实：只包含实际发生的事，不要臆造
- 成果量化：尽量用数据说明（完成X项、提升Y%）
- 简明扼要：每条 1-2 行，不要写长篇大论
- 区分优先级：重要成果放前面
