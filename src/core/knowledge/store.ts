/**
 * Knowledge Store — singleton for managing the local knowledge index.
 *
 * Storage layout:
 *   ~/.abu/knowledge/
 *     index.json           — top-level index (KnowledgeIndex)
 *     entries/<id>.json    — individual chunk entries
 *
 * Mirrors the memdir pattern: JSON-based, file-per-entry, in-memory index cached.
 */

import { homeDir } from '@tauri-apps/api/path';
import { joinPath } from '../../utils/pathUtils';
import type {
  KnowledgeEntry,
  KnowledgeIndex,
  KnowledgeIndexEntry,
} from './types';
import {
  KNOWLEDGE_DIR,
  INDEX_FILENAME,
  ENTRIES_DIR,
  MAX_KNOWLEDGE_ENTRIES,
} from './types';
import { readTextFile, writeTextFile, exists, mkdir, remove } from '@tauri-apps/plugin-fs';

let cachedHome: string | null = null;
async function getHome(): Promise<string> {
  if (!cachedHome) cachedHome = await homeDir();
  return cachedHome;
}

async function getKnowledgeDir(): Promise<string> {
  return joinPath(await getHome(), '.abu', KNOWLEDGE_DIR);
}

async function getEntriesDir(): Promise<string> {
  return joinPath(await getKnowledgeDir(), ENTRIES_DIR);
}

async function getIndexPath(): Promise<string> {
  return joinPath(await getKnowledgeDir(), INDEX_FILENAME);
}

async function getEntryPath(id: string): Promise<string> {
  return joinPath(await getEntriesDir(), `${id}.json`);
}

function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).substring(2, 10);
}

// ─── In-memory cache ─────────────────────────────────────────────

class KnowledgeStore {
  private index: KnowledgeIndex | null = null;
  private initialized = false;

  async init(): Promise<void> {
    if (this.initialized) return;

    const dirPath = await getKnowledgeDir();
    const entriesPath = await getEntriesDir();

    try {
      if (!(await exists(dirPath))) {
        await mkdir(dirPath, { recursive: true });
      }
      if (!(await exists(entriesPath))) {
        await mkdir(entriesPath, { recursive: true });
      }
    } catch {
      // Directory creation failure is non-fatal; read ops will surface errors
    }

    await this.loadIndex();
    this.initialized = true;
  }

  // ── Index management ──────────────────────────────────────────

  private async loadIndex(): Promise<void> {
    try {
      const indexPath = await getIndexPath();
      if (await exists(indexPath)) {
        const raw = await readTextFile(indexPath);
        this.index = JSON.parse(raw) as KnowledgeIndex;
      }
    } catch {
      // Index doesn't exist or is corrupt — start fresh
    }

    if (!this.index) {
      this.index = {
        version: 1,
        updatedAt: new Date().toISOString(),
        entries: [],
      };
    }
  }

  private async saveIndex(): Promise<void> {
    if (!this.index) return;
    this.index.updatedAt = new Date().toISOString();
    const indexPath = await getIndexPath();
    await writeTextFile(indexPath, JSON.stringify(this.index, null, 2));
  }

  getIndex(): KnowledgeIndex | null {
    return this.index;
  }

  getEntries(): KnowledgeIndexEntry[] {
    return this.index?.entries ?? [];
  }

  // ── Entry CRUD ─────────────────────────────────────────────────

  async addEntry(entry: Omit<KnowledgeEntry, 'id' | 'indexedAt'>): Promise<string> {
    await this.init();
    if (!this.index) throw new Error('Knowledge store not initialized');

    if (this.index.entries.length >= MAX_KNOWLEDGE_ENTRIES) {
      throw new Error(`Knowledge store full (max ${MAX_KNOWLEDGE_ENTRIES} entries)`);
    }

    const id = generateId();
    const fullEntry: KnowledgeEntry = {
      ...entry,
      id,
      indexedAt: new Date().toISOString(),
    };

    // Write entry file
    const entryPath = await getEntryPath(id);
    await writeTextFile(entryPath, JSON.stringify(fullEntry, null, 2));

    // Update index
    const indexEntry: KnowledgeIndexEntry = {
      id,
      sourceType: entry.sourceType,
      title: entry.title,
      sourceUrl: entry.sourceUrl,
      indexedAt: fullEntry.indexedAt,
      keywords: extractKeywords(entry.title + ' ' + entry.content),
    };
    this.index.entries.push(indexEntry);
    await this.saveIndex();

    return id;
  }

  async addEntries(entries: Omit<KnowledgeEntry, 'id' | 'indexedAt'>[]): Promise<string[]> {
    const ids: string[] = [];
    for (const entry of entries) {
      const id = await this.addEntry(entry);
      ids.push(id);
    }
    return ids;
  }

  async getEntry(id: string): Promise<KnowledgeEntry | null> {
    await this.init();
    try {
      const entryPath = await getEntryPath(id);
      if (!(await exists(entryPath))) return null;
      const raw = await readTextFile(entryPath);
      return JSON.parse(raw) as KnowledgeEntry;
    } catch {
      return null;
    }
  }

  async removeEntry(id: string): Promise<void> {
    await this.init();
    if (!this.index) return;

    try {
      const entryPath = await getEntryPath(id);
      if (await exists(entryPath)) {
        await remove(entryPath);
      }
    } catch {
      // Best-effort removal
    }

    this.index.entries = this.index.entries.filter(e => e.id !== id);
    await this.saveIndex();
  }

  async removeEntriesBySource(sourceUrl: string): Promise<number> {
    await this.init();
    if (!this.index) return 0;

    const toRemove = this.index.entries.filter(e => e.sourceUrl === sourceUrl);
    for (const entry of toRemove) {
      try {
        const entryPath = await getEntryPath(entry.id);
        if (await exists(entryPath)) {
          await remove(entryPath);
        }
      } catch {
        // Best-effort
      }
    }

    this.index.entries = this.index.entries.filter(e => e.sourceUrl !== sourceUrl);
    await this.saveIndex();
    return toRemove.length;
  }

  async getEntryCount(): Promise<number> {
    await this.init();
    return this.index?.entries.length ?? 0;
  }

  async clear(): Promise<void> {
    await this.init();
    if (!this.index) return;

    for (const entry of this.index.entries) {
      try {
        const entryPath = await getEntryPath(entry.id);
        if (await exists(entryPath)) {
          await remove(entryPath);
        }
      } catch {
        // Best-effort
      }
    }

    this.index.entries = [];
    await this.saveIndex();
  }
}

// ─── Keyword extraction ──────────────────────────────────────────

function extractKeywords(text: string): string {
  // Simple extract: CJK bigrams + Latin words
  const words = new Set<string>();

  // Extract Latin words
  const latinWords = text.toLowerCase().match(/[a-z]{2,}/g);
  if (latinWords) {
    for (const w of latinWords) {
      words.add(w);
    }
  }

  // Extract CJK bigrams
  const cjkChars = text.match(/[一-鿿]/g);
  if (cjkChars) {
    for (let i = 0; i < cjkChars.length - 1; i++) {
      words.add(cjkChars[i] + cjkChars[i + 1]);
    }
    // Also include individual significant chars
    for (const c of cjkChars) {
      words.add(c);
    }
  }

  return [...words].slice(0, 100).join(',');
}

/** Singleton */
export const knowledgeStore = new KnowledgeStore();
