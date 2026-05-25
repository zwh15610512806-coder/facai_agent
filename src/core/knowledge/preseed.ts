/**
 * Knowledge Pre-seed — loads company knowledge base files into the local index.
 *
 * On first launch (empty store), scans ${RESOURCE_DIR}/company-config/memories/
 * and indexes all .md files as knowledge entries. Subsequent launches skip if
 * entries already exist for these sources.
 */

import { resolveResource } from '@tauri-apps/api/path';
import { readTextFile, readDir, exists } from '@tauri-apps/plugin-fs';
import { knowledgeStore } from './store';
import { chunkText } from './parser';
import type { KnowledgeEntry, KnowledgeSourceType } from './types';

const PRESET_MEMORIES_DIR = 'company-config/memories';

/**
 * Scan and index all preset knowledge files into the knowledge store.
 * Skips files that are already indexed (by source URL match).
 * Called once on app startup.
 */
export async function preseedKnowledge(): Promise<{ indexed: number; skipped: number; errors: string[] }> {
  const errors: string[] = [];
  let indexed = 0;
  let skipped = 0;

  await knowledgeStore.init();

  try {
    const dirPath = await resolveResource(PRESET_MEMORIES_DIR);
    if (!(await exists(dirPath))) {
      return { indexed: 0, skipped: 0, errors: [`Preset directory not found: ${dirPath}`] };
    }

    const entries = await readDir(dirPath);
    const mdFiles = entries.filter(e => e.name?.endsWith('.md'));

    for (const file of mdFiles) {
      const sourceUrl = `preset:${file.name}`;

      // Skip if already indexed
      const existing = knowledgeStore.getEntries().filter(e => e.sourceUrl === sourceUrl);
      if (existing.length > 0) {
        skipped += existing.length;
        continue;
      }

      try {
        const content = await readTextFile(`${dirPath}/${file.name}`);
        if (!content.trim()) continue;

        const title = extractTitle(content, file.name);
        const chunks = chunkText(content, 3000);

        const entries: Omit<KnowledgeEntry, 'id' | 'indexedAt'>[] = chunks.map((chunk, i) => ({
          sourceType: 'local-file' as KnowledgeSourceType,
          sourceUrl,
          title,
          content: chunk,
          chunkIndex: i,
          totalChunks: chunks.length,
          sourceUpdatedAt: new Date().toISOString(),
          metadata: { filename: file.name, preset: 'true' },
        }));

        await knowledgeStore.addEntries(entries);
        indexed += entries.length;
      } catch (err) {
        errors.push(`Failed to index ${file.name}: ${err instanceof Error ? err.message : String(err)}`);
      }
    }
  } catch (err) {
    errors.push(`Preseed scan failed: ${err instanceof Error ? err.message : String(err)}`);
  }

  return { indexed, skipped, errors };
}

/** Extract title from markdown: first H1 heading, or fallback to filename */
function extractTitle(content: string, filename: string): string {
  const match = content.match(/^#\s+(.+)/m);
  if (match) return match[1].trim();
  return filename.replace(/\.md$/, '');
}
