import type { ToolDefinition } from '../../../types';
import { TOOL_NAMES } from '../toolNames';
import { runLarkCli } from '../../lark/executor';

// ─── Lark Doc Search ────────────────────────────────────────────

export const larkSearchDocsTool: ToolDefinition = {
  name: TOOL_NAMES.LARK_SEARCH_DOCS,
  description:
    '在飞书云文档中搜索。按关键词搜索飞书文档、知识库内容。返回匹配文档的标题、摘要和链接。当用户询问公司文档、制度、流程、技术文档等内容时使用。',
  inputSchema: {
    type: 'object',
    properties: {
      query: { type: 'string', description: '搜索关键词' },
      max_results: { type: 'number', description: '最大返回条数（默认 10，最多 20）' },
    },
    required: ['query'],
  },
  execute: async (input) => {
    const query = input.query as string;
    const maxResults = Math.min(Math.max(1, Number(input.max_results) || 10), 20);

    const result = await runLarkCli([
      'doc',
      '+search',
      query,
      '--page-size',
      String(maxResults),
    ]);

    if (!result.ok) {
      return `飞书文档搜索失败：${result.stderr || `exit code ${result.exitCode}`}`;
    }

    return result.stdout || `未找到与 "${query}" 相关的飞书文档。`;
  },
  isConcurrencySafe: true,
};

// ─── Lark Get Doc Content ────────────────────────────────────────

export const larkGetDocContentTool: ToolDefinition = {
  name: TOOL_NAMES.LARK_GET_DOC_CONTENT,
  description:
    '获取飞书云文档的完整内容（Markdown 格式）。通过文档 token 或 URL 读取文档正文。用于查看搜索到的文档的具体内容。',
  inputSchema: {
    type: 'object',
    properties: {
      doc_token: { type: 'string', description: '飞书文档 token 或完整 URL' },
    },
    required: ['doc_token'],
  },
  execute: async (input) => {
    const docToken = input.doc_token as string;

    // Extract token from URL if a full URL is provided
    const token = docToken.includes('/')
      ? docToken.split('/').pop()?.split('?')[0] || docToken
      : docToken;

    const result = await runLarkCli(['doc', '+fetch', token, '--api-version', 'v2']);

    if (!result.ok) {
      return `读取飞书文档失败：${result.stderr || `exit code ${result.exitCode}`}`;
    }

    return result.stdout || '文档内容为空。';
  },
  isConcurrencySafe: true,
};

// ─── Lark Wiki Search ────────────────────────────────────────────

export const larkSearchWikiTool: ToolDefinition = {
  name: TOOL_NAMES.LARK_SEARCH_WIKI,
  description:
    '在飞书知识库中搜索。按关键词搜索知识库空间内的文档节点。用于在特定知识库中查找信息。',
  inputSchema: {
    type: 'object',
    properties: {
      query: { type: 'string', description: '搜索关键词' },
      space_id: { type: 'string', description: '知识库空间 ID（可选，不指定则搜索所有可访问空间）' },
      max_results: { type: 'number', description: '最大返回条数（默认 10，最多 20）' },
    },
    required: ['query'],
  },
  execute: async (input) => {
    const query = input.query as string;
    const spaceId = input.space_id as string | undefined;
    const maxResults = Math.min(Math.max(1, Number(input.max_results) || 10), 20);

    const args = ['wiki', '+search', query, '--page-size', String(maxResults)];
    if (spaceId) {
      args.push('--space-id', spaceId);
    }

    const result = await runLarkCli(args);

    if (!result.ok) {
      return `知识库搜索失败：${result.stderr || `exit code ${result.exitCode}`}`;
    }

    return result.stdout || `未在知识库中找到与 "${query}" 相关的内容。`;
  },
  isConcurrencySafe: true,
};

// ─── Lark List Wiki Nodes ────────────────────────────────────────

export const larkListWikiNodesTool: ToolDefinition = {
  name: TOOL_NAMES.LARK_LIST_WIKI_NODES,
  description:
    '列出飞书知识库空间中的文档树结构。用于浏览知识库的目录层次，了解知识库中有哪些文档。',
  inputSchema: {
    type: 'object',
    properties: {
      space_id: { type: 'string', description: '知识库空间 ID' },
      parent_token: { type: 'string', description: '父节点 token（可选，不指定则列出根节点）' },
    },
    required: ['space_id'],
  },
  execute: async (input) => {
    const spaceId = input.space_id as string;
    const parentToken = input.parent_token as string | undefined;

    const args = ['wiki', '+list', spaceId];
    if (parentToken) {
      args.push('--parent', parentToken);
    }

    const result = await runLarkCli(args);

    if (!result.ok) {
      return `获取知识库目录失败：${result.stderr || `exit code ${result.exitCode}`}`;
    }

    return result.stdout || '知识库目录为空。';
  },
  isConcurrencySafe: true,
};

// ─── Lark Base Search ────────────────────────────────────────────

export const larkSearchBaseRecordsTool: ToolDefinition = {
  name: TOOL_NAMES.LARK_SEARCH_BASE_RECORDS,
  description:
    '在飞书多维表格中搜索和查询记录。按条件查询 Base 表格中的数据。用于查找项目信息、员工数据、OKR 等结构化数据。',
  inputSchema: {
    type: 'object',
    properties: {
      app_token: { type: 'string', description: '多维表格 App Token' },
      table_id: { type: 'string', description: '表格 ID' },
      query: { type: 'string', description: '查询关键词或筛选条件' },
      max_results: { type: 'number', description: '最大返回条数（默认 10，最多 50）' },
    },
    required: ['app_token', 'table_id'],
  },
  execute: async (input) => {
    const appToken = input.app_token as string;
    const tableId = input.table_id as string;
    const query = input.query as string | undefined;
    const maxResults = Math.min(Math.max(1, Number(input.max_results) || 10), 50);

    const args = ['base', '+record', appToken, tableId, '--page-size', String(maxResults)];
    if (query) {
      args.push('--filter', query);
    }

    const result = await runLarkCli(args);

    if (!result.ok) {
      return `多维表格查询失败：${result.stderr || `exit code ${result.exitCode}`}`;
    }

    return result.stdout || '未找到匹配的记录。';
  },
  isConcurrencySafe: true,
};

// ─── Lark Calendar Events ────────────────────────────────────────

export const larkGetCalendarEventsTool: ToolDefinition = {
  name: TOOL_NAMES.LARK_GET_CALENDAR_EVENTS,
  description:
    '查询飞书日历中的日程。获取指定时间范围内的日历事件，包括会议、提醒等。返回标题、时间、参与者等信息。',
  inputSchema: {
    type: 'object',
    properties: {
      start_date: { type: 'string', description: '开始日期，格式 YYYY-MM-DD' },
      end_date: { type: 'string', description: '结束日期，格式 YYYY-MM-DD（可选，默认与 start_date 相同）' },
      calendar_id: { type: 'string', description: '日历 ID（可选，默认使用主日历）' },
      max_results: { type: 'number', description: '最大返回条数（默认 20，最多 50）' },
    },
    required: ['start_date'],
  },
  execute: async (input) => {
    const startDate = input.start_date as string;
    const endDate = (input.end_date as string) || startDate;
    const calendarId = input.calendar_id as string | undefined;
    const maxResults = Math.min(Math.max(1, Number(input.max_results) || 20), 50);

    const args = ['calendar', '+agenda', '--start', startDate, '--end', endDate];
    if (calendarId) {
      args.push('--calendar-id', calendarId);
    }
    args.push('--page-size', String(maxResults));

    const result = await runLarkCli(args);

    if (!result.ok) {
      return `日历查询失败：${result.stderr || `exit code ${result.exitCode}`}`;
    }

    return result.stdout || `${startDate} 至 ${endDate} 没有日程安排。`;
  },
  isConcurrencySafe: true,
};

// ─── Lark FreeBusy ───────────────────────────────────────────────

export const larkGetFreebusyTool: ToolDefinition = {
  name: TOOL_NAMES.LARK_GET_FREEBUSY,
  description:
    '查询用户的忙闲状态。用于查看同事是否有空、协调会议时间。',
  inputSchema: {
    type: 'object',
    properties: {
      user_ids: { type: 'string', description: '用户 open_id，多个用逗号分隔' },
      start_time: { type: 'string', description: '开始时间，格式 YYYY-MM-DD HH:MM' },
      end_time: { type: 'string', description: '结束时间，格式 YYYY-MM-DD HH:MM' },
    },
    required: ['user_ids', 'start_time', 'end_time'],
  },
  execute: async (input) => {
    const userIds = input.user_ids as string;
    const startTime = input.start_time as string;
    const endTime = input.end_time as string;

    const args = [
      'calendar',
      '+freebusy',
      '--user-ids', userIds,
      '--start', startTime,
      '--end', endTime,
    ];

    const result = await runLarkCli(args);

    if (!result.ok) {
      return `忙闲查询失败：${result.stderr || `exit code ${result.exitCode}`}`;
    }

    return result.stdout || '未获取到忙闲信息。';
  },
  isConcurrencySafe: true,
};

// ─── Lark My Tasks ───────────────────────────────────────────────

export const larkGetMyTasksTool: ToolDefinition = {
  name: TOOL_NAMES.LARK_GET_MY_TASKS,
  description:
    '查询我的飞书任务列表。获取当前用户的待办任务，可按状态和时间过滤。用于查看待办、跟踪任务进度。',
  inputSchema: {
    type: 'object',
    properties: {
      status: { type: 'string', description: '任务状态筛选：pending（待处理）、completed（已完成）（可选）' },
      due_date_before: { type: 'string', description: '截止日期上限，格式 YYYY-MM-DD（可选）' },
      max_results: { type: 'number', description: '最大返回条数（默认 20，最多 50）' },
    },
    required: [],
  },
  execute: async (input) => {
    const status = input.status as string | undefined;
    const dueDateBefore = input.due_date_before as string | undefined;
    const maxResults = Math.min(Math.max(1, Number(input.max_results) || 20), 50);

    const args = ['task', '+get-my-tasks', '--page-size', String(maxResults)];
    if (status) {
      args.push('--status', status);
    }
    if (dueDateBefore) {
      args.push('--due-before', dueDateBefore);
    }

    const result = await runLarkCli(args);

    if (!result.ok) {
      return `任务查询失败：${result.stderr || `exit code ${result.exitCode}`}`;
    }

    return result.stdout || '没有找到任务。';
  },
  isConcurrencySafe: true,
};

// ─── Lark Create Task ────────────────────────────────────────────

export const larkCreateTaskTool: ToolDefinition = {
  name: TOOL_NAMES.LARK_CREATE_TASK,
  description:
    '创建飞书任务。在飞书任务中新建待办事项，可设置标题、描述、截止日期和负责人。',
  inputSchema: {
    type: 'object',
    properties: {
      title: { type: 'string', description: '任务标题' },
      description: { type: 'string', description: '任务描述（可选）' },
      due_date: { type: 'string', description: '截止日期，格式 YYYY-MM-DD（可选）' },
      assignee: { type: 'string', description: '负责人姓名或 open_id（可选）' },
    },
    required: ['title'],
  },
  execute: async (input) => {
    const title = input.title as string;
    const description = input.description as string | undefined;
    const dueDate = input.due_date as string | undefined;
    const assignee = input.assignee as string | undefined;

    const args = ['task', '+create', title];
    if (description) {
      args.push('--description', description);
    }
    if (dueDate) {
      args.push('--due-date', dueDate);
    }
    if (assignee) {
      args.push('--assignee', assignee);
    }

    const result = await runLarkCli(args);

    if (!result.ok) {
      return `创建任务失败：${result.stderr || `exit code ${result.exitCode}`}`;
    }

    return result.stdout || '任务创建成功。';
  },
};

// ─── Lark Update Task ────────────────────────────────────────────

export const larkUpdateTaskTool: ToolDefinition = {
  name: TOOL_NAMES.LARK_UPDATE_TASK,
  description:
    '更新飞书任务状态或内容。修改任务的完成状态、描述、截止日期等字段。',
  inputSchema: {
    type: 'object',
    properties: {
      task_id: { type: 'string', description: '任务 ID' },
      status: { type: 'string', description: '新状态：completed（完成）或 pending（待处理）（可选）' },
      description: { type: 'string', description: '新描述（可选）' },
      due_date: { type: 'string', description: '新截止日期，格式 YYYY-MM-DD（可选）' },
    },
    required: ['task_id'],
  },
  execute: async (input) => {
    const taskId = input.task_id as string;
    const status = input.status as string | undefined;
    const description = input.description as string | undefined;
    const dueDate = input.due_date as string | undefined;

    const args = ['task', '+update', taskId];
    if (status) {
      args.push('--status', status);
    }
    if (description) {
      args.push('--description', description);
    }
    if (dueDate) {
      args.push('--due-date', dueDate);
    }

    const result = await runLarkCli(args);

    if (!result.ok) {
      return `更新任务失败：${result.stderr || `exit code ${result.exitCode}`}`;
    }

    return result.stdout || '任务更新成功。';
  },
};

// ─── Lark List Meetings ──────────────────────────────────────────

export const larkListMeetingsTool: ToolDefinition = {
  name: TOOL_NAMES.LARK_LIST_MEETINGS,
  description:
    '查询飞书视频会议历史记录。按时间范围和关键词搜索已结束的会议。用于回顾会议内容、整理会议纪要。',
  inputSchema: {
    type: 'object',
    properties: {
      start_date: { type: 'string', description: '开始日期，格式 YYYY-MM-DD' },
      end_date: { type: 'string', description: '结束日期，格式 YYYY-MM-DD（可选）' },
      keyword: { type: 'string', description: '会议主题关键词（可选）' },
      max_results: { type: 'number', description: '最大返回条数（默认 10，最多 20）' },
    },
    required: ['start_date'],
  },
  execute: async (input) => {
    const startDate = input.start_date as string;
    const endDate = input.end_date as string | undefined;
    const keyword = input.keyword as string | undefined;
    const maxResults = Math.min(Math.max(1, Number(input.max_results) || 10), 20);

    const args = ['vc', '+list', '--start', startDate];
    if (endDate) {
      args.push('--end', endDate);
    }
    if (keyword) {
      args.push('--keyword', keyword);
    }
    args.push('--page-size', String(maxResults));

    const result = await runLarkCli(args);

    if (!result.ok) {
      return `会议查询失败：${result.stderr || `exit code ${result.exitCode}`}`;
    }

    return result.stdout || `未找到 ${startDate} 之后的会议记录。`;
  },
  isConcurrencySafe: true,
};

// ─── Lark Get Meeting Minutes ────────────────────────────────────

export const larkGetMeetingMinutesTool: ToolDefinition = {
  name: TOOL_NAMES.LARK_GET_MEETING_MINUTES,
  description:
    '获取飞书妙记的会议纪要。包括 AI 总结、待办事项和章节。用于整理会议纪要、提取行动项。',
  inputSchema: {
    type: 'object',
    properties: {
      meeting_id: { type: 'string', description: '会议 ID（妙记 token 或飞书会议 ID）' },
    },
    required: ['meeting_id'],
  },
  execute: async (input) => {
    const meetingId = input.meeting_id as string;

    const result = await runLarkCli(['minutes', '+get', meetingId]);

    if (!result.ok) {
      return `获取会议纪要失败：${result.stderr || `exit code ${result.exitCode}`}`;
    }

    return result.stdout || '无法获取会议纪要。';
  },
  isConcurrencySafe: true,
};

// ─── Lark Get Meeting Transcript ─────────────────────────────────

export const larkGetMeetingTranscriptTool: ToolDefinition = {
  name: TOOL_NAMES.LARK_GET_MEETING_TRANSCRIPT,
  description:
    '获取飞书妙记的会议逐字稿/文字稿全文。用于详细回顾会议讨论内容。',
  inputSchema: {
    type: 'object',
    properties: {
      meeting_id: { type: 'string', description: '会议 ID（妙记 token 或飞书会议 ID）' },
    },
    required: ['meeting_id'],
  },
  execute: async (input) => {
    const meetingId = input.meeting_id as string;

    const result = await runLarkCli(['minutes', '+get', meetingId, '--transcript']);

    if (!result.ok) {
      return `获取会议逐字稿失败：${result.stderr || `exit code ${result.exitCode}`}`;
    }

    return result.stdout || '无法获取会议逐字稿。';
  },
  isConcurrencySafe: true,
};

// ─── Lark Search Sheets ──────────────────────────────────────────

export const larkSearchSheetsTool: ToolDefinition = {
  name: TOOL_NAMES.LARK_SEARCH_SHEETS,
  description:
    '读取飞书电子表格内容。按范围读取表格单元格数据。用于查找表格中的数据、报表信息等。',
  inputSchema: {
    type: 'object',
    properties: {
      spreadsheet_token: { type: 'string', description: '电子表格 token' },
      sheet_id: { type: 'string', description: '工作表 ID（可选）' },
      range: { type: 'string', description: '单元格范围，如 A1:D100（可选）' },
    },
    required: ['spreadsheet_token'],
  },
  execute: async (input) => {
    const spreadsheetToken = input.spreadsheet_token as string;
    const sheetId = input.sheet_id as string | undefined;
    const range = input.range as string | undefined;

    const args = ['sheets', '+read', spreadsheetToken];
    if (sheetId) {
      args.push('--sheet-id', sheetId);
    }
    if (range) {
      args.push('--range', range);
    }

    const result = await runLarkCli(args);

    if (!result.ok) {
      return `电子表格读取失败：${result.stderr || `exit code ${result.exitCode}`}`;
    }

    return result.stdout || '表格内容为空。';
  },
  isConcurrencySafe: true,
};

// ─── Knowledge Index Local ──────────────────────────────────────

export const knowledgeIndexLocalTool: ToolDefinition = {
  name: TOOL_NAMES.KNOWLEDGE_INDEX_LOCAL,
  description:
    '索引本地目录中的文档（Markdown、PDF、Word、Excel），生成知识库索引供后续检索。索引文件存储在本地。',
  inputSchema: {
    type: 'object',
    properties: {
      directory_path: { type: 'string', description: '要索引的本地目录路径' },
      file_pattern: { type: 'string', description: '文件匹配模式，如 *.md,*.pdf（可选，默认索引所有支持格式）' },
      recursive: { type: 'boolean', description: '是否递归索引子目录（默认 true）' },
    },
    required: ['directory_path'],
  },
  execute: async (input) => {
    const dirPath = input.directory_path as string;
    const filePattern = input.file_pattern as string | undefined;
    const recursive = input.recursive !== false;

    const args = ['doc', '+index-local', dirPath];
    if (filePattern) {
      args.push('--pattern', filePattern);
    }
    if (recursive) {
      args.push('--recursive');
    }

    const result = await runLarkCli(args);

    if (!result.ok) {
      return `本地文件索引失败：${result.stderr || `exit code ${result.exitCode}`}`;
    }

    return result.stdout || '索引完成。';
  },
};

// ─── Knowledge Search ───────────────────────────────────────────

export const knowledgeSearchTool: ToolDefinition = {
  name: TOOL_NAMES.KNOWLEDGE_SEARCH,
  description:
    '搜索本地知识库索引。检索已索引的飞书文档和本地文件内容。返回相关片段和来源信息。',
  inputSchema: {
    type: 'object',
    properties: {
      query: { type: 'string', description: '搜索查询' },
      max_results: { type: 'number', description: '最大返回条数（默认 5，最多 15）' },
      source_filter: { type: 'string', description: '来源过滤：lark（仅飞书）、local（仅本地文件）、all（默认全部）' },
    },
    required: ['query'],
  },
  execute: async (input) => {
    const query = input.query as string;
    const maxResults = Math.min(Math.max(1, Number(input.max_results) || 5), 15);
    const sourceFilter = (input.source_filter as string) || 'all';

    const args = ['doc', '+search-knowledge', query, '--page-size', String(maxResults), '--source', sourceFilter];

    const result = await runLarkCli(args);

    if (!result.ok) {
      return `知识库搜索失败：${result.stderr || `exit code ${result.exitCode}`}`;
    }

    return result.stdout || `未找到与 "${query}" 相关的本地知识库内容。`;
  },
  isConcurrencySafe: true,
};

// ─── All Lark Tools ──────────────────────────────────────────────

export const allLarkTools: ToolDefinition[] = [
  larkSearchDocsTool,
  larkGetDocContentTool,
  larkSearchWikiTool,
  larkListWikiNodesTool,
  larkSearchBaseRecordsTool,
  larkSearchSheetsTool,
  larkGetCalendarEventsTool,
  larkGetFreebusyTool,
  larkGetMyTasksTool,
  larkCreateTaskTool,
  larkUpdateTaskTool,
  larkListMeetingsTool,
  larkGetMeetingMinutesTool,
  larkGetMeetingTranscriptTool,
  knowledgeIndexLocalTool,
  knowledgeSearchTool,
];
