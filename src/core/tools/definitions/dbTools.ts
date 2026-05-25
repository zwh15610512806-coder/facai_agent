import type { ToolDefinition } from '../../../types';
import { TOOL_NAMES } from '../toolNames';
import { runLarkCli } from '../../lark/executor';

/**
 * Database query tool — execute SQL against configured internal databases.
 * Uses lark-cli db plugin or direct SQL connection depending on configuration.
 */
export const dbQueryTool: ToolDefinition = {
  name: TOOL_NAMES.DB_QUERY,
  description:
    '查询内部数据库。执行 SQL 查询并返回结果。用于从公司内部数据库获取结构化数据，如项目信息、员工数据、业务指标等。仅支持 SELECT 查询，不支持 INSERT/UPDATE/DELETE 等写操作。',
  inputSchema: {
    type: 'object',
    properties: {
      query: { type: 'string', description: 'SQL SELECT 查询语句' },
      database: { type: 'string', description: '数据库名称（可选，不指定则查询默认数据库）' },
      max_rows: { type: 'number', description: '最大返回行数（默认 50，最多 200）' },
    },
    required: ['query'],
  },
  execute: async (input) => {
    const query = (input.query as string).trim();
    const database = input.database as string | undefined;
    const maxRows = Math.min(Math.max(1, Number(input.max_rows) || 50), 200);

    // Safety: only allow SELECT queries
    const normalized = query.toUpperCase();
    if (
      !normalized.startsWith('SELECT') &&
      !normalized.startsWith('WITH') &&
      !normalized.startsWith('SHOW') &&
      !normalized.startsWith('DESCRIBE') &&
      !normalized.startsWith('EXPLAIN')
    ) {
      return '错误：仅支持 SELECT/SHOW/DESCRIBE/EXPLAIN 查询，不支持修改数据的操作。';
    }

    // Block dangerous patterns
    if (
      normalized.includes('INTO OUTFILE') ||
      normalized.includes('INTO DUMPFILE') ||
      normalized.includes('LOAD_FILE')
    ) {
      return '错误：查询包含不允许的操作。';
    }

    const args = ['db', '+query', query, '--max-rows', String(maxRows)];
    if (database) {
      args.push('--database', database);
    }

    const result = await runLarkCli(args, { timeout: 60 });

    if (!result.ok) {
      return `数据库查询失败：${result.stderr || `exit code ${result.exitCode}`}`;
    }

    return result.stdout || '查询结果为空。';
  },
};
