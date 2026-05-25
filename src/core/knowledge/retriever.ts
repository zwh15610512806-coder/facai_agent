/**
 * Knowledge Retriever — keyword-based search over the local knowledge index.
 *
 * Mirrors memdir/relevance.ts scoring: name + description match, no LLM needed.
 * For company knowledge bases with hundreds/thousands of entries, keyword search
 * is fast and effective. Embedding-based search can be layered on later.
 */

import type { KnowledgeIndexEntry, SearchResult } from './types';
import { MAX_SEARCH_RESULTS, MAX_PER_TURN_INJECTION } from './types';
import { knowledgeStore } from './store';

interface ScoredEntry {
  indexEntry: KnowledgeIndexEntry;
  score: number;
}

/**
 * Tokenize query: lowercase, split, drop tokens < 2 chars.
 */
function tokenize(query: string): string[] {
  return query
    .toLowerCase()
    .split(/\s+/)
    .filter(t => t.length >= 2);
}

/**
 * Score a knowledge index entry against query tokens.
 *
 * Weights:
 *   - title match:        +3 per token
 *   - keyword match:      +2 per token
 *   - recency boost:      +1 / (1 + ageDays)
 */
function scoreEntry(tokens: readonly string[], entry: KnowledgeIndexEntry): number {
  if (tokens.length === 0) return 0;

  const title = entry.title.toLowerCase();
  const keywords = entry.keywords.toLowerCase();

  let score = 0;
  for (const token of tokens) {
    if (title.includes(token)) score += 3;
    if (keywords.includes(token)) score += 2;
  }

  if (score > 0) {
    const indexedAt = new Date(entry.indexedAt).getTime();
    const ageDays = (Date.now() - indexedAt) / 86_400_000;
    score += 1 / (1 + Math.max(0, ageDays));
  }

  return score;
}

/**
 * Search the knowledge store for entries matching the query.
 * Returns top-scoring entries, capped at MAX_SEARCH_RESULTS.
 */
export async function searchKnowledge(query: string, maxResults = 5): Promise<SearchResult[]> {
  await knowledgeStore.init();
  const entries = knowledgeStore.getEntries();

  if (entries.length === 0) return [];

  const tokens = tokenize(query);
  if (tokens.length === 0) return [];

  const scored: ScoredEntry[] = entries
    .map(indexEntry => ({ indexEntry, score: scoreEntry(tokens, indexEntry) }))
    .filter(s => s.score > 0)
    .sort((a, b) => b.score - a.score);

  const top = scored.slice(0, Math.min(maxResults, MAX_SEARCH_RESULTS));

  const results: SearchResult[] = [];
  for (const { indexEntry, score } of top) {
    const entry = await knowledgeStore.getEntry(indexEntry.id);
    if (!entry) continue;
    results.push({
      entry,
      score: Math.round(score * 100) / 100,
      matchReason: score > 3 ? '标题 + 关键词匹配' : '关键词匹配',
    });
  }

  return results;
}

/**
 * Find and format relevant knowledge for injection into the agent's system prompt.
 * Returns a string suitable for inclusion in the system message, or empty if nothing found.
 */
export async function getRelevantKnowledgeSection(query: string): Promise<string> {
  const results = await searchKnowledge(query, 5);

  if (results.length === 0) return '';

  const blocks: string[] = [];
  let totalBytes = 0;

  for (const { entry, score } of results) {
    if (totalBytes >= MAX_PER_TURN_INJECTION) break;

    const truncated =
      entry.content.length > 2000
        ? entry.content.slice(0, 2000) + '\n\n[内容已截断]'
        : entry.content;

    if (totalBytes + truncated.length > MAX_PER_TURN_INJECTION) break;

    blocks.push(
      `<knowledge id="${entry.id}" source="${entry.sourceType}" title="${entry.title}" score="${score}">\n${truncated}\n</knowledge>`
    );
    totalBytes += truncated.length;
  }

  if (blocks.length === 0) return '';

  return (
    '\n## 相关知识库内容\n' +
    '以下是从公司知识库中检索到的相关内容，优先参考这些信息回答用户问题。\n\n' +
    blocks.join('\n\n')
  );
}
