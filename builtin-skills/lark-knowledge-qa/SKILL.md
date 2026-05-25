---
name: lark-knowledge-qa
description: |
  搜索公司知识库（飞书文档、Wiki、多维表格、本地文件）回答问题。
  当用户询问公司制度、流程、项目信息、技术文档、产品规格等内容时使用此技能。
trigger: |
  用户询问公司文档、制度、流程、项目信息、产品知识，或提到"查一下"/"公司有没有"/"有没有文档"/"知识库"等
do-not-trigger: |
  用户只是闲聊、询问个人话题、问天气等不涉及公司知识的问题
user-invocable: true
argument-hint: <要查询的问题>
allowed-tools:
  - lark_search_docs
  - lark_get_doc_content
  - lark_search_wiki
  - lark_list_wiki_nodes
  - lark_search_base_records
  - knowledge_search
tags:
  - knowledge
  - search
  - company
  - wiki
  - 知识库
---

# 知识库问答

你的任务是帮用户从公司知识库中找到准确答案。

## 工作流程

### 第一步：分析问题
确定用户问题的范围和类型：
- 制度流程类 → 优先搜索飞书 Wiki
- 产品技术类 → 优先搜索飞书文档
- 结构数据类 → 搜索飞书多维表格（Base）
- 通用问题 → 同时搜索多个来源

### 第二步：并行搜索
不要一个一个搜，在不确定时同时搜索：
- `lark_search_docs(query)` — 搜索云文档
- `lark_search_wiki(query)` — 搜索知识库
- `knowledge_search(query)` — 搜索本地索引
- `lark_search_base_records(app_token, table_id)` — 搜索数据库

### 第三步：深入阅读
对于搜索结果中排名靠前的文档，使用 `lark_get_doc_content(doc_token)` 获取完整内容。
不需要读每一个结果，只读最相关的 1-3 篇。

### 第四步：组织回答
- 开头用 1-2 句话直接回答用户问题
- 列出关键要点，每条标注来源（文档标题）
- 如果内容有冲突，说明不同来源的观点
- 如果没有找到确切答案，如实告知，并建议用户补充关键词

## 注意事项
- 优先引用公司文档，不要凭记忆猜测
- 多个来源内容冲突时，标注各自来源让用户判断
- 敏感信息（薪资、密码等）不要输出
