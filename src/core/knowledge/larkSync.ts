/**
 * Lark Sync — synchronize Feishu knowledge resources into the local index.
 *
 * Uses lark-cli to fetch content from:
 *   - Wiki spaces (doc tree + individual pages)
 *   - Docs (individual documents)
 *   - Base tables (structured records)
 *
 * Sync is triggered manually via knowledge tools or on a schedule.
 */

import { runLarkCli } from '../lark/executor';
import { knowledgeStore } from './store';
import { chunkText } from './parser';
import type { KnowledgeEntry, KnowledgeSourceType } from './types';

interface LarkDocResult {
  token: string;
  title: string;
  content: string;
  updatedAt: string;
}

/**
 * Sync a Feishu Wiki space into the knowledge store.
 * Fetches the document tree and indexes each page.
 */
export async function syncWikiSpace(spaceId: string): Promise<{ indexed: number; errors: string[] }> {
  const errors: string[] = [];
  let indexed = 0;

  // Remove old entries for this space
  const sourceUrl = `lark-wiki:${spaceId}`;
  await knowledgeStore.removeEntriesBySource(sourceUrl);

  // Fetch the document tree
  const listResult = await runLarkCli(['wiki', '+list', spaceId]);
  if (!listResult.ok) {
    return { indexed: 0, errors: [`Failed to list wiki space ${spaceId}: ${listResult.stderr}`] };
  }

  // Parse doc list — lark-cli outputs structured text or JSON
  const docTokens = extractTokens(listResult.stdout);
  if (docTokens.length === 0) {
    return { indexed: 0, errors: [`No documents found in wiki space ${spaceId}`] };
  }

  // Fetch and index each document
  for (const token of docTokens) {
    try {
      const doc = await fetchDocContent(token);
      if (!doc) {
        errors.push(`Failed to fetch doc ${token}`);
        continue;
      }

      const chunks = chunkText(doc.content);
      const entries: Omit<KnowledgeEntry, 'id' | 'indexedAt'>[] = chunks.map((chunk, i) => ({
        sourceType: 'lark-wiki' as KnowledgeSourceType,
        sourceUrl,
        title: doc.title,
        content: chunk,
        chunkIndex: i,
        totalChunks: chunks.length,
        sourceUpdatedAt: doc.updatedAt,
        metadata: { spaceId, docToken: token },
      }));

      await knowledgeStore.addEntries(entries);
      indexed += entries.length;
    } catch (err) {
      errors.push(`Error indexing doc ${token}: ${err instanceof Error ? err.message : String(err)}`);
    }
  }

  return { indexed, errors };
}

/**
 * Sync a single Feishu document into the knowledge store.
 */
export async function syncDoc(docToken: string): Promise<{ indexed: number; error?: string }> {
  const sourceUrl = `lark-doc:${docToken}`;
  await knowledgeStore.removeEntriesBySource(sourceUrl);

  try {
    const doc = await fetchDocContent(docToken);
    if (!doc) {
      return { indexed: 0, error: `Failed to fetch doc ${docToken}` };
    }

    const chunks = chunkText(doc.content);
    const entries: Omit<KnowledgeEntry, 'id' | 'indexedAt'>[] = chunks.map((chunk, i) => ({
      sourceType: 'lark-doc' as KnowledgeSourceType,
      sourceUrl,
      title: doc.title,
      content: chunk,
      chunkIndex: i,
      totalChunks: chunks.length,
      sourceUpdatedAt: doc.updatedAt,
      metadata: { docToken },
    }));

    const ids = await knowledgeStore.addEntries(entries);
    return { indexed: ids.length };
  } catch (err) {
    return { indexed: 0, error: err instanceof Error ? err.message : String(err) };
  }
}

/**
 * Fetch document content via lark-cli.
 */
async function fetchDocContent(docToken: string): Promise<LarkDocResult | null> {
  const result = await runLarkCli(['doc', '+fetch', docToken, '--api-version', 'v2']);

  if (!result.ok || !result.stdout) return null;

  // Try to parse as JSON first (structured lark-cli output),
  // otherwise treat as raw markdown
  try {
    const parsed = JSON.parse(result.stdout);
    return {
      token: docToken,
      title: parsed.title || docToken,
      content: parsed.content || result.stdout,
      updatedAt: parsed.updated_at || new Date().toISOString(),
    };
  } catch {
    // Raw markdown — extract title from first heading
    const titleMatch = result.stdout.match(/^#\s+(.+)/m);
    return {
      token: docToken,
      title: titleMatch ? titleMatch[1].trim() : docToken,
      content: result.stdout,
      updatedAt: new Date().toISOString(),
    };
  }
}

/**
 * Extract document tokens from lark-cli wiki list output.
 * Handles both JSON array and line-based token listings.
 */
function extractTokens(stdout: string): string[] {
  try {
    const parsed = JSON.parse(stdout);
    if (Array.isArray(parsed)) {
      return parsed.map((item: { token?: string; node_token?: string }) =>
        item.token || item.node_token || ''
      ).filter(Boolean);
    }
  } catch {
    // Not JSON — try to extract tokens from text
  }

  // Extract tokens from text patterns like "token=xxx" or "doc_token: xxx"
  const tokens = new Set<string>();
  const tokenPatterns = [
    /token[=:]\s*([a-zA-Z0-9_-]+)/gi,
    /node_token[=:]\s*([a-zA-Z0-9_-]+)/gi,
    /\/([a-zA-Z0-9_-]{8,})\b/gi,
  ];

  for (const pattern of tokenPatterns) {
    for (const match of stdout.matchAll(pattern)) {
      tokens.add(match[1]);
    }
  }

  return [...tokens];
}
