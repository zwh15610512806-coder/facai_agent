import type { FileSearchAiUnderstanding, FileSearchIntent, FileSearchQuery } from '@/types/fileSearch';
import { llmCall } from '@/core/llm/llmCall';
import { providerRequiresApiKey, useSettingsStore } from '@/stores/settingsStore';

import {
  buildIntentFromQuery,
  parseFileSearchIntent,
  parseFileSearchPrompt,
  queryFromIntent,
  understandingFromIntent,
} from './queryParser';

export interface AiFileSearchParseResult {
  query: Partial<FileSearchQuery>;
  intent: FileSearchIntent;
  understanding: FileSearchAiUnderstanding;
  usedFallback: boolean;
}

export interface AiFileSearchParseOptions {
  getEntityCandidates?: (query: string) => Promise<string[]>;
}

export async function parseFileSearchWithAi(prompt: string, options: AiFileSearchParseOptions = {}): Promise<AiFileSearchParseResult> {
  const fallbackIntent = parseFileSearchIntent(prompt);
  const fallback = queryFromIntent(fallbackIntent);
  const fallbackResult = buildParseResult(fallbackIntent, true);
  const settings = useSettingsStore.getState();
  const hasKey = !providerRequiresApiKey(settings) || settings.providers.some((p) => p.enabled && p.apiKey.trim().length > 0);
  if (!hasKey) {
    return fallbackResult;
  }

  try {
    const result = await llmCall({
      system: buildSystemPrompt(),
      messages: [{ role: 'user', content: prompt }],
      maxTokens: 500,
    });
    const parsed = JSON.parse(extractJsonObject(result.text)) as Record<string, unknown>;
    const intent = await sanitizeAiIntent(parsed, fallback, prompt, options);
    return {
      query: queryFromIntent(intent),
      intent,
      understanding: understandingFromIntent(intent),
      usedFallback: false,
    };
  } catch (err) {
    console.warn('[fileSearch] AI parse failed, falling back to local parser:', err);
    return fallbackResult;
  }
}

function buildSystemPrompt(): string {
  const today = formatDate(new Date());
  return [
    '你是网盘文件检索意图解析器，只输出 JSON，不要输出 Markdown。',
    `今天是 ${today}。`,
    '字段只允许 keywords、fileType、extension、dateFrom、dateTo、sortBy、summary。',
    'keywords 是核心实体词数组，例如产品名、品牌、人名、项目名。去掉“找、搜索、的、素材、资料、文件、图片、视频”等泛词。',
    '保持实体完整，不要把“刀叉勺、翻糖蛋糕、品牌手册”拆成单字。',
    'fileType 可选 all/document/image/video/audio/archive/folder/other，无法确定就省略。',
    'extension 只输出不带点的小写扩展名，例如 pdf、xlsx、mp4。',
    'dateFrom/dateTo 使用 YYYY-MM-DD，只有用户明确提到今天、昨天、本周、上周、本月、这个月、上月等时间时才输出。',
    'sortBy 可选 modified_desc/modified_asc/name_asc/size_desc。',
    'summary 用一句中文说明你理解的搜索意图。',
  ].join('\n');
}

function extractJsonObject(text: string): string {
  const trimmed = text.trim();
  if (trimmed.startsWith('{') && trimmed.endsWith('}')) return trimmed;
  const match = /\{[\s\S]*\}/.exec(trimmed);
  if (!match) throw new Error('No JSON object in model response');
  return match[0];
}

async function sanitizeAiIntent(
  value: Record<string, unknown>,
  fallback: Partial<FileSearchQuery>,
  rawPrompt: string,
  options: AiFileSearchParseOptions,
): Promise<FileSearchIntent> {
  const next: Partial<FileSearchQuery> = {};
  const keywords = sanitizeKeywords(value.keywords, fallback);
  if (keywords.length > 0) {
    next.query = keywords.join(' ');
  } else if (typeof value.query === 'string' && value.query.trim()) {
    next.query = value.query.trim();
  } else {
    copyKeywords(next, fallback);
  }

  if (isFileType(value.fileType)) {
    next.fileType = value.fileType;
  } else if (fallback.fileType) {
    next.fileType = fallback.fileType;
  }

  if (typeof value.extension === 'string') {
    const extension = value.extension.replace(/^\./, '').trim().toLowerCase();
    if (extension) next.extension = extension;
  } else if (fallback.extension) {
    next.extension = fallback.extension;
  }

  if (typeof value.folder === 'string') next.folder = value.folder.trim();
  if (isDateString(value.dateFrom)) {
    next.dateFrom = value.dateFrom;
  } else if (fallback.dateFrom) {
    next.dateFrom = fallback.dateFrom;
  }
  if (isDateString(value.dateTo)) {
    next.dateTo = value.dateTo;
  } else if (fallback.dateTo) {
    next.dateTo = fallback.dateTo;
  }
  if (isSortBy(value.sortBy)) {
    next.sortBy = value.sortBy;
  } else if (fallback.sortBy) {
    next.sortBy = fallback.sortBy;
  }

  const candidateTerms = keywords.length > 0
    ? keywords
    : next.query
      ? sanitizeKeywords([next.query], fallback)
      : fallback.hardTerms ?? fallback.keywords ?? [];
  const { hardTerms, softTerms } = await validateEntityTerms(candidateTerms, options);
  const summary = typeof value.summary === 'string' ? value.summary : undefined;
  return buildIntentFromQuery(Object.keys(next).length > 0 ? next : fallback, hardTerms, softTerms, 'ai', rawPrompt, summary);
}

function copyKeywords(target: Partial<FileSearchQuery>, fallback: Partial<FileSearchQuery>): void {
  if (fallback.keywords?.length) {
    target.keywords = fallback.keywords;
    target.query = fallback.query ?? fallback.keywords.join(' ');
  } else if (fallback.query) {
    target.query = fallback.query;
  }
}

function sanitizeKeywords(value: unknown, fallback: Partial<FileSearchQuery>): string[] {
  const fallbackKeywords = fallback.keywords ?? [];
  if (!Array.isArray(value)) return [];
  const result: string[] = [];
  const seen = new Set<string>();
  for (const item of value) {
    if (typeof item !== 'string') continue;
    const keyword = item.trim();
    if (!keyword) continue;
    for (const next of expandAiKeyword(keyword, fallbackKeywords)) {
      const key = next.toLowerCase();
      if (!next || seen.has(key)) continue;
      seen.add(key);
      result.push(next);
    }
  }
  if (result.length === 0) {
    for (const keyword of fallbackKeywords) {
      const key = keyword.toLowerCase();
      if (!keyword || seen.has(key)) continue;
      seen.add(key);
      result.push(keyword);
    }
  }
  return result;
}

async function validateEntityTerms(
  terms: string[],
  options: AiFileSearchParseOptions,
): Promise<{ hardTerms: string[]; softTerms: string[] }> {
  const hardTerms: string[] = [];
  const softTerms: string[] = [];
  const seen = new Set<string>();
  for (const term of terms) {
    const value = term.trim();
    const key = value.toLowerCase();
    if (!value || seen.has(key)) continue;
    seen.add(key);
    if (!options.getEntityCandidates) {
      hardTerms.push(value);
      continue;
    }
    const candidates = await options.getEntityCandidates(value);
    if (candidates.some((candidate) => candidate.toLowerCase() === key)) {
      hardTerms.push(value);
    } else {
      softTerms.push(value);
    }
  }
  return { hardTerms, softTerms };
}

function buildParseResult(intent: FileSearchIntent, usedFallback: boolean): AiFileSearchParseResult {
  return {
    query: queryFromIntent(intent),
    intent,
    understanding: understandingFromIntent(intent),
    usedFallback,
  };
}

function expandAiKeyword(value: string, fallbackKeywords: string[]): string[] {
  const parsed = parseFileSearchPrompt(value);
  if (parsed.keywords?.length) {
    const hasFallbackOverlap = parsed.keywords.some((keyword) =>
      fallbackKeywords.some((fallback) => fallback.toLowerCase() === keyword.toLowerCase()),
    );
    if (fallbackKeywords.length > 0 && !hasFallbackOverlap) {
      return [value];
    }
    return parsed.keywords;
  }
  if (parsed.fileType || parsed.extension || parsed.dateFrom || parsed.dateTo || parsed.sortBy) return [];
  return [value];
}

function isFileType(value: unknown): value is FileSearchQuery['fileType'] {
  return typeof value === 'string' && ['all', 'document', 'image', 'video', 'audio', 'archive', 'folder', 'other'].includes(value);
}

function isSortBy(value: unknown): value is FileSearchQuery['sortBy'] {
  return typeof value === 'string' && ['modified_desc', 'modified_asc', 'name_asc', 'size_desc'].includes(value);
}

function isDateString(value: unknown): value is string {
  return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value);
}

function formatDate(date: Date): string {
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, '0');
  const day = `${date.getDate()}`.padStart(2, '0');
  return `${year}-${month}-${day}`;
}
