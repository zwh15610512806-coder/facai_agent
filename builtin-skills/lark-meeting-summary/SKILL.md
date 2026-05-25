---
name: lark-meeting-summary
description: |
  整理飞书会议纪要。查询指定时间范围内的会议记录，生成结构化的会议纪要，
  包括关键决策、讨论要点和行动项。
trigger: |
  用户要求整理会议纪要、生成会议总结、回顾会议内容、"昨天的会"、"上周的会议"、
  "会议纪要"、"总结一下会议"等
do-not-trigger: |
  用户只是询问会议时间、地点，不需要内容总结
user-invocable: true
argument-hint: <日期范围或会议主题>
allowed-tools:
  - lark_list_meetings
  - lark_get_meeting_minutes
  - lark_get_meeting_transcript
  - lark_get_calendar_events
tags:
  - meeting
  - summary
  - 会议
  - 纪要
  - 妙记
---

# 会议纪要整理

从飞书会议记录中提取关键信息，生成结构化纪要。

## 工作流程

### 第一步：获取会议列表
使用 `lark_list_meetings(start_date, end_date)` 查询会议记录。
如果用户只提到"昨天"或"这周"，自动计算日期范围。
如不确定，同时查飞书日历：`lark_get_calendar_events(start_date, end_date)`。

### 第二步：获取会议内容
对每个重要会议，调用 `lark_get_meeting_minutes(meeting_id)` 获取 AI 生成的纪要（含总结、章节、待办）。
如果需要详细回顾，再调用 `lark_get_meeting_transcript(meeting_id)` 获取逐字稿。

### 第三步：提取关键信息
从纪要中提取：
- **会议主题和目的** — 1 句话概括
- **关键决策** — 达成了什么共识，确定了什么方向
- **讨论要点** — 各方观点和核心讨论
- **行动项** — 谁做什么，截止时间
- **未解决的问题** — 需要后续跟进的事项

### 第四步：输出格式

```markdown
## 会议纪要汇总 — YYYY年MM月DD日

### 会议一：[会议主题]
- **时间**：HH:MM - HH:MM
- **参会人**：张三、李四、王五
- **关键决策**：
  1. 决策内容一
  2. 决策内容二
- **行动项**：
  - [ ] 张三：完成XX设计 — 截止 3月15日
  - [ ] 李四：对接XX接口 — 截止 3月10日

### 会议二：...

## 待办总览
| 负责人 | 任务 | 截止日期 |
|--------|------|----------|
| 张三 | XX设计 | 3月15日 |
| 李四 | XX接口 | 3月10日 |
```

## 注意事项
- 如果某个会议没有妙记，用日历事件信息做个简要说明
- 行动项要具体可执行，不要模糊描述
- 如果同一事项在多个会议中讨论，标注演进过程
