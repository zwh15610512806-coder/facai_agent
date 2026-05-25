/**
 * Knowledge Module — public API barrel.
 *
 * Usage:
 *   import { knowledgeStore, searchKnowledge, scanDirectory } from '@/core/knowledge';
 */

export { knowledgeStore } from './store';
export { searchKnowledge, getRelevantKnowledgeSection } from './retriever';
export { scanDirectory } from './scanner';
export { parseFile, chunkText } from './parser';
export { syncWikiSpace, syncDoc } from './larkSync';
export type { KnowledgeEntry, KnowledgeSourceType, SearchResult } from './types';
