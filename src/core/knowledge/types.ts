/**
 * Knowledge Base Types — local knowledge indexing and retrieval system.
 *
 * Knowledge entries are chunked text snippets from various sources:
 * Feishu Docs, Wiki, Base, local files, and databases.
 *
 * Storage: ~/.abu/knowledge/
 *   index.json           — top-level index
 *   entries/<id>.json    — individual chunk entries
 */

export type KnowledgeSourceType =
  | 'lark-doc'
  | 'lark-wiki'
  | 'lark-base'
  | 'lark-sheets'
  | 'local-file'
  | 'db-query';

export interface KnowledgeEntry {
  /** Unique entry ID */
  id: string;
  /** Source type */
  sourceType: KnowledgeSourceType;
  /** Human-readable source URL or path */
  sourceUrl: string;
  /** Document title */
  title: string;
  /** Chunk text content (max 4KB per chunk) */
  content: string;
  /** Chunk index within the document */
  chunkIndex: number;
  /** Total chunks in this document */
  totalChunks: number;
  /** ISO 8601 timestamp of source document last update */
  sourceUpdatedAt: string;
  /** ISO 8601 timestamp when this entry was indexed */
  indexedAt: string;
  /** Optional metadata */
  metadata?: Record<string, string>;
}

export interface KnowledgeIndexEntry {
  id: string;
  sourceType: KnowledgeSourceType;
  title: string;
  sourceUrl: string;
  indexedAt: string;
  /** Keywords extracted for fast matching (comma-separated) */
  keywords: string;
}

export interface KnowledgeIndex {
  version: 1;
  updatedAt: string;
  entries: KnowledgeIndexEntry[];
}

export interface SearchResult {
  entry: KnowledgeEntry;
  score: number;
  matchReason: string;
}

/** Constraints */
export const MAX_KNOWLEDGE_ENTRIES = 5000;
export const MAX_CHUNK_BYTES = 4_000;
export const MAX_SEARCH_RESULTS = 15;
export const MAX_PER_TURN_INJECTION = 20_000;
export const KNOWLEDGE_DIR = 'knowledge';
export const INDEX_FILENAME = 'index.json';
export const ENTRIES_DIR = 'entries';
