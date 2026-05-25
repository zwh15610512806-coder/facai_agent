/**
 * Local File Scanner — scans directories for indexable documents.
 *
 * Supported formats: .md, .txt, .json (text-based)
 * Binary formats (PDF, DOCX, XLSX) are parsed via parser.ts using
 * Tauri shell commands calling Python scripts or external tools.
 */

import { readDir, exists } from '@tauri-apps/plugin-fs';

const SUPPORTED_EXTENSIONS = new Set([
  '.md', '.txt', '.json', '.csv',
  '.pdf', '.docx', '.xlsx', '.pptx',
]);

export interface ScannedFile {
  path: string;
  name: string;
  ext: string;
  size: number;
}

/**
 * Recursively scan a directory for supported files.
 */
export async function scanDirectory(
  dirPath: string,
  recursive = true,
  pattern?: string,
): Promise<ScannedFile[]> {
  const results: ScannedFile[] = [];

  try {
    if (!(await exists(dirPath))) {
      return results;
    }

    const entries = await readDir(dirPath);

    for (const entry of entries) {
      if (entry.name.startsWith('.')) continue;

      const fullPath = entry.name.includes(':') ? entry.name : `${dirPath.replace(/\/+$/, '')}/${entry.name}`;

      const dirEntry = entry as unknown as { isDirectory: boolean; name: string };
      if (dirEntry.isDirectory) {
        if (recursive) {
          const fullPath = entry.name.includes(':') ? entry.name : `${dirPath.replace(/\/+$/, '')}/${entry.name}`;
          const children = await scanDirectory(fullPath, recursive, pattern);
          results.push(...children);
        }
        continue;
      }

      const ext = entry.name.toLowerCase().match(/\.[a-z0-9]+$/)?.[0] || '';
      if (!SUPPORTED_EXTENSIONS.has(ext)) continue;

      if (pattern) {
        const glob = pattern.replace(/\*/g, '.*');
        if (!new RegExp(glob, 'i').test(entry.name)) continue;
      }

      results.push({
        path: fullPath,
        name: entry.name,
        ext,
        size: 0,
      });
    }
  } catch {
    // Directory read error — return whatever we've collected
  }

  return results;
}
