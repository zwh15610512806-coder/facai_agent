import type { FileSearchFileType, FileSearchIntent, FileSearchQuery, FileSearchSortBy } from '@/types/fileSearch';

const EXTENSION_TYPES: Record<string, FileSearchFileType> = {
  pdf: 'document',
  doc: 'document',
  docx: 'document',
  xls: 'document',
  xlsx: 'document',
  ppt: 'document',
  pptx: 'document',
  txt: 'document',
  csv: 'document',
  jpg: 'image',
  jpeg: 'image',
  png: 'image',
  gif: 'image',
  webp: 'image',
  svg: 'image',
  mp4: 'video',
  mov: 'video',
  avi: 'video',
  mkv: 'video',
  mp3: 'audio',
  wav: 'audio',
  flac: 'audio',
  zip: 'archive',
  rar: 'archive',
  '7z': 'archive',
};

const PRODUCT_TERMS = [
  '巧克力慕斯',
  '巧克力蛋糕',
  '红丝绒蛋糕',
  '翻糖蛋糕',
  '生日蛋糕',
  '盒装刀叉',
  '刀叉勺',
  '刀叉',
  '纸杯蛋糕',
  '提拉米苏',
  '曲奇饼干',
  '戚风蛋糕',
  '海绵蛋糕',
  '千层蛋糕',
  '慕斯蛋糕',
  '芝士蛋糕',
  '奶油蛋糕',
  '抹茶蛋糕',
  '菠萝包',
  '软欧包',
  '马卡龙',
  '慕斯杯',
  '蛋黄酥',
  '牛轧糖',
  '雪花酥',
  '三明治',
  '冰淇淋',
  '雪媚娘',
  '甜甜圈',
  '月饼',
  '蛋挞',
  '可颂',
  '法棍',
  '吐司',
  '汉堡',
  '披萨',
  '泡芙',
  '布丁',
  '果冻',
  '大福',
];

const KNOWN_PERSON_NAMES = ['裳羽', '星遥', '子矜'];

const NOISE_WORDS = [
  '帮我',
  '找一下',
  '看一下',
  '给我',
  '搜索',
  '查找',
  '寻找',
  '文件',
  '资料',
  '素材',
  '东西',
  '内容',
  '文档',
  '图片',
  '照片',
  '视频',
  '音频',
  '压缩包',
  '这个',
  '那个',
  '什么',
  '最近',
  '最新',
  '修改',
  '修改的',
  '拍摄',
  '拍的',
  '拍',
  '剪辑',
  '剪的',
  '剪',
  '制作',
  '做的',
  '做',
  '发',
  '给',
  '传',
  '要',
  '有',
  '的',
  '了',
];

const TYPE_HINTS: Array<{ type: FileSearchFileType; patterns: RegExp[] }> = [
  { type: 'document', patterns: [/文档/g, /报表/g, /报告/g, /表格/g, /幻灯片/g] },
  { type: 'image', patterns: [/图片/g, /照片/g, /图像/g, /截图/g, /海报/g, /素材图/g] },
  { type: 'video', patterns: [/视频/g, /影片/g, /录像/g] },
  { type: 'audio', patterns: [/音频/g, /录音/g, /音乐/g] },
  { type: 'archive', patterns: [/压缩包/g, /压缩/g, /归档/g] },
  { type: 'folder', patterns: [/文件夹/g, /目录/g] },
];

const SORT_HINTS: Array<{ sortBy: FileSearchSortBy; patterns: RegExp[] }> = [
  { sortBy: 'modified_desc', patterns: [/最近/g, /最新/g, /刚修改/g, /修改的/g] },
  { sortBy: 'modified_asc', patterns: [/最早/g, /最旧/g] },
  { sortBy: 'size_desc', patterns: [/最大/g, /大文件/g] },
  { sortBy: 'name_asc', patterns: [/按名称/g, /文件名/g] },
];

type DateRange = { from: string; to: string };

const CHINESE_MONTHS: Record<string, number> = {
  一: 1,
  二: 2,
  三: 3,
  四: 4,
  五: 5,
  六: 6,
  七: 7,
  八: 8,
  九: 9,
  十: 10,
  十一: 11,
  十二: 12,
};

export function parseFileSearchPrompt(prompt: string): Partial<FileSearchQuery> {
  let rest = prompt.trim();
  const result: Partial<FileSearchQuery> = {};

  for (const { sortBy, patterns } of SORT_HINTS) {
    if (patterns.some((pattern) => pattern.test(rest))) {
      result.sortBy = sortBy;
      rest = removePatterns(rest, patterns);
      break;
    }
  }

  const dateRange = extractDateRange(rest);
  if (dateRange) {
    result.dateFrom = dateRange.range.from;
    result.dateTo = dateRange.range.to;
    rest = removePatterns(rest, [dateRange.pattern]);
  }

  const extMatch = /(?:\.|\b)(pdf|docx?|xlsx?|pptx?|txt|csv|jpe?g|png|gif|webp|svg|mp4|mov|avi|mkv|mp3|wav|flac|zip|rar|7z)\b/i.exec(rest);
  if (extMatch?.[1]) {
    const extension = extMatch[1].toLowerCase();
    result.extension = extension;
    result.fileType = EXTENSION_TYPES[extension] ?? 'other';
    rest = rest.replace(extMatch[0], ' ');
  }

  if (!result.fileType) {
    for (const { type, patterns } of TYPE_HINTS) {
      if (patterns.some((pattern) => pattern.test(rest))) {
        result.fileType = type;
        rest = removePatterns(rest, patterns);
        break;
      }
    }
  } else {
    for (const { patterns } of TYPE_HINTS) {
      rest = removePatterns(rest, patterns);
    }
  }

  const keywords = extractKeywords(rest);
  if (keywords.length > 0) {
    result.keywords = keywords;
    result.query = keywords.join(' ');
  }

  return result;
}

export function parseFileSearchIntent(prompt: string): FileSearchIntent {
  const query = parseFileSearchPrompt(prompt);
  const hardTerms = query.keywords ?? (query.query ? [query.query] : []);
  return buildIntentFromQuery(query, hardTerms, [], 'local', prompt);
}

export function buildIntentFromQuery(
  query: Partial<FileSearchQuery>,
  hardTerms: string[],
  softTerms: string[],
  source: FileSearchIntent['source'],
  rawPrompt: string,
  summary?: string,
): FileSearchIntent {
  const next: FileSearchIntent = {
    hardTerms: dedupe(hardTerms.map((term) => term.trim()).filter(Boolean)),
    softTerms: dedupe(softTerms.map((term) => term.trim()).filter(Boolean)),
    fileType: query.fileType === 'all' ? undefined : query.fileType,
    extension: query.extension,
    folder: query.folder,
    dateFrom: query.dateFrom,
    dateTo: query.dateTo,
    sortBy: query.sortBy,
    summary: summary?.trim() || buildIntentSummary(rawPrompt, hardTerms, query),
    source,
    conditions: [],
  };
  next.conditions = buildConditions(next);
  return next;
}

export function queryFromIntent(intent: FileSearchIntent): Partial<FileSearchQuery> {
  return {
    query: intent.hardTerms.join(' ') || intent.softTerms.join(' ') || undefined,
    keywords: intent.hardTerms.length > 0 ? intent.hardTerms : undefined,
    hardTerms: intent.hardTerms,
    softTerms: intent.softTerms,
    fileType: intent.fileType,
    extension: intent.extension,
    folder: intent.folder,
    dateFrom: intent.dateFrom,
    dateTo: intent.dateTo,
    sortBy: intent.sortBy,
  };
}

export function understandingFromIntent(intent: FileSearchIntent) {
  return {
    summary: intent.summary,
    keywords: intent.hardTerms,
    hardTerms: intent.hardTerms,
    softTerms: intent.softTerms,
    fileType: intent.fileType,
    extension: intent.extension,
    dateFrom: intent.dateFrom,
    dateTo: intent.dateTo,
    conditions: intent.conditions,
  };
}

function extractDateRange(value: string): { pattern: RegExp; range: DateRange } | null {
  const today = new Date();
  const explicitMonth = /(1[0-2]|[1-9]|十一|十二|十|一|二|三|四|五|六|七|八|九)月份?/g.exec(value);
  if (explicitMonth?.[1]) {
    const month = parseMonthToken(explicitMonth[1]);
    if (month) {
      return {
        pattern: new RegExp(escapeRegExp(explicitMonth[0]), 'g'),
        range: monthRange(today.getFullYear(), month),
      };
    }
  }

  const rules: Array<{ pattern: RegExp; range: () => DateRange }> = [
    { pattern: /今天/g, range: () => sameDay(today) },
    { pattern: /昨天/g, range: () => sameDay(addDays(today, -1)) },
    { pattern: /本周/g, range: () => ({ from: formatDate(addDays(today, -mondayOffset(today))), to: formatDate(today) }) },
    {
      pattern: /上周/g,
      range: () => {
        const thisMonday = addDays(today, -mondayOffset(today));
        return { from: formatDate(addDays(thisMonday, -7)), to: formatDate(addDays(thisMonday, -1)) };
      },
    },
    { pattern: /本月|这个月/g, range: () => ({ from: formatDate(new Date(today.getFullYear(), today.getMonth(), 1)), to: formatDate(today) }) },
    {
      pattern: /上个月|上月/g,
      range: () => {
        const start = new Date(today.getFullYear(), today.getMonth() - 1, 1);
        const end = new Date(today.getFullYear(), today.getMonth(), 0);
        return { from: formatDate(start), to: formatDate(end) };
      },
    },
  ];

  for (const rule of rules) {
    if (rule.pattern.test(value)) {
      return { pattern: rule.pattern, range: rule.range() };
    }
  }
  return null;
}

function parseMonthToken(value: string): number | null {
  const numeric = Number.parseInt(value, 10);
  if (Number.isInteger(numeric) && numeric >= 1 && numeric <= 12) return numeric;
  return CHINESE_MONTHS[value] ?? null;
}

function monthRange(year: number, month: number): DateRange {
  const start = new Date(year, month - 1, 1);
  const end = new Date(year, month, 0);
  return { from: formatDate(start), to: formatDate(end) };
}

function extractKeywords(value: string): string[] {
  let rest = normalizeText(value);
  const hits: Array<{ index: number; value: string }> = [];

  for (const term of [...PRODUCT_TERMS, ...KNOWN_PERSON_NAMES].sort((a, b) => b.length - a.length)) {
    let index = rest.indexOf(term);
    while (index !== -1) {
      hits.push({ index, value: term });
      rest = `${rest.slice(0, index)}${' '.repeat(term.length)}${rest.slice(index + term.length)}`;
      index = rest.indexOf(term);
    }
  }

  for (const word of NOISE_WORDS.sort((a, b) => b.length - a.length)) {
    rest = rest.replaceAll(word, ' ');
  }

  const extraHits = Array.from(rest.matchAll(/\S+/g))
    .map((match) => ({ index: match.index ?? 0, value: match[0].trim() }))
    .filter((hit) => hit.value.length >= 2);

  return dedupe([
    ...[...hits, ...extraHits].sort((a, b) => a.index - b.index).map((hit) => hit.value),
  ]);
}

function normalizeText(value: string): string {
  return value
    .replace(/[，。！？、；：,.!?;:()[\]{}"'`~@#$%^&*_+=|\\/<>-]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function removePatterns(value: string, patterns: RegExp[]): string {
  return patterns.reduce((next, pattern) => next.replace(pattern, ' '), value);
}

function buildConditions(intent: FileSearchIntent): FileSearchIntent['conditions'] {
  const conditions: FileSearchIntent['conditions'] = [];
  for (const term of intent.hardTerms) {
    conditions.push({
      id: `term:hard:${term}`,
      type: 'term',
      value: term,
      label: term,
      strength: 'hard',
      removable: true,
    });
  }
  for (const term of intent.softTerms) {
    conditions.push({
      id: `term:soft:${term}`,
      type: 'term',
      value: term,
      label: term,
      strength: 'soft',
      removable: true,
    });
  }
  if (intent.fileType) {
    conditions.push({
      id: `fileType:${intent.fileType}`,
      type: 'fileType',
      value: intent.fileType,
      label: intent.fileType,
      removable: true,
    });
  }
  if (intent.extension) {
    conditions.push({
      id: `extension:${intent.extension}`,
      type: 'extension',
      value: intent.extension,
      label: `.${intent.extension}`,
      removable: true,
    });
  }
  if (intent.folder) {
    conditions.push({
      id: `folder:${intent.folder}`,
      type: 'folder',
      value: intent.folder,
      label: intent.folder,
      removable: true,
    });
  }
  if (intent.dateFrom || intent.dateTo) {
    const from = intent.dateFrom ?? '-';
    const to = intent.dateTo ?? '-';
    conditions.push({
      id: `date:${from}:${to}`,
      type: 'dateRange',
      value: `${from}:${to}`,
      label: `${from} 至 ${to}`,
      removable: true,
    });
  }
  return conditions;
}

function buildIntentSummary(rawPrompt: string, hardTerms: string[], query: Partial<FileSearchQuery>): string {
  const parts = [
    ...hardTerms,
    query.fileType && query.fileType !== 'all' ? query.fileType : '',
    query.extension ? `.${query.extension}` : '',
    query.dateFrom || query.dateTo ? `${query.dateFrom ?? '-'} 至 ${query.dateTo ?? '-'}` : '',
  ].filter(Boolean);
  return parts.length > 0 ? `已识别精准条件：${parts.join('、')}` : `搜索：${rawPrompt}`;
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function dedupe(values: string[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const value of values) {
    const key = value.toLowerCase();
    if (!key || seen.has(key)) continue;
    seen.add(key);
    result.push(value);
  }
  return result;
}

function sameDay(date: Date): DateRange {
  const value = formatDate(date);
  return { from: value, to: value };
}

function mondayOffset(date: Date): number {
  const day = date.getDay();
  return day === 0 ? 6 : day - 1;
}

function addDays(date: Date, days: number): Date {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

function formatDate(date: Date): string {
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, '0');
  const day = `${date.getDate()}`.padStart(2, '0');
  return `${year}-${month}-${day}`;
}
