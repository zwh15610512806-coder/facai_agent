export type FileSearchFileType =
  | 'all'
  | 'document'
  | 'image'
  | 'video'
  | 'audio'
  | 'archive'
  | 'folder'
  | 'other';

export type FileSearchSortBy = 'modified_desc' | 'modified_asc' | 'name_asc' | 'size_desc';
export type FileSearchIntentSource = 'ai' | 'local' | 'fallback';
export type FileSearchConditionType = 'term' | 'fileType' | 'extension' | 'dateRange' | 'folder';
export type FileSearchConditionStrength = 'hard' | 'soft';

export interface FileSearchTerm {
  value: string;
  strength: FileSearchConditionStrength;
  source: FileSearchIntentSource;
}

export interface FileSearchCondition {
  id: string;
  type: FileSearchConditionType;
  value: string;
  label: string;
  removable: boolean;
  strength?: FileSearchConditionStrength;
}

export interface FileSearchIntent {
  hardTerms: string[];
  softTerms: string[];
  fileType?: FileSearchFileType;
  extension?: string;
  folder?: string;
  dateFrom?: string;
  dateTo?: string;
  sortBy?: FileSearchSortBy;
  summary: string;
  source: FileSearchIntentSource;
  conditions: FileSearchCondition[];
}

export interface FileSearchSourceConfig {
  id: string;
  name: string;
  path: string;
  enabled: boolean;
  frozen?: boolean;
}

export interface FileSearchConfig {
  sources: FileSearchSourceConfig[];
  pageSize: number;
}

export interface FileSearchQuery {
  query?: string;
  keywords?: string[];
  hardTerms?: string[];
  softTerms?: string[];
  fileType?: FileSearchFileType;
  extension?: string;
  folder?: string;
  dateFrom?: string;
  dateTo?: string;
  sortBy?: FileSearchSortBy;
  limit?: number;
  offset?: number;
}

export interface FileSearchAiUnderstanding {
  summary: string;
  keywords: string[];
  hardTerms?: string[];
  softTerms?: string[];
  fileType?: FileSearchFileType;
  extension?: string;
  dateFrom?: string;
  dateTo?: string;
  conditions?: FileSearchCondition[];
}

export interface FileSearchResult {
  id: number;
  filePath: string;
  fileName: string;
  parentFolder: string;
  fileExtension: string;
  fileSize: number;
  fileModified: number;
  fileType: FileSearchFileType;
  indexedAt: number;
}

export interface FileSearchQueryResponse {
  items: FileSearchResult[];
  total: number;
}

export interface FileSearchFileDetail extends FileSearchResult {
  exists: boolean;
}

export type FileSearchPreviewKind =
  | 'text'
  | 'image'
  | 'video'
  | 'audio'
  | 'pdf'
  | 'external'
  | 'missing'
  | 'unreachable';

export interface FileSearchPreview {
  id: number;
  kind: FileSearchPreviewKind;
  filePath: string;
  assetPath?: string;
  fileName: string;
  content?: string;
  mimeType?: string;
}

export interface FileSearchIndexStatus {
  phase: 'idle' | 'scanning' | 'indexing' | 'done' | 'error';
  running: boolean;
  current: number;
  total: number;
  percent: number;
  message: string;
  startedAt?: number;
  finishedAt?: number;
  totalFiles: number;
  lastError?: string;
}
