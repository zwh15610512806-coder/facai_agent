/**
 * Document Parser — extracts text content from various file formats.
 *
 * Plain text formats (.md, .txt, .json, .csv) are read directly via Tauri FS.
 * Binary formats (.pdf, .docx, .xlsx) require external tools via
 * run_shell_command (Python scripts or command-line converters).
 */

import { readTextFile } from '@tauri-apps/plugin-fs';

export interface ParsedContent {
  text: string;
  error?: string;
}

/**
 * Parse a file based on its extension. Returns extracted text content.
 */
export async function parseFile(filePath: string, ext: string): Promise<ParsedContent> {
  switch (ext) {
    case '.md':
    case '.txt':
    case '.json':
    case '.csv':
      return parsePlainText(filePath);

    case '.pdf':
      return parseWithCommand(filePath, 'pdf');

    case '.docx':
      return parseWithCommand(filePath, 'docx');

    case '.xlsx':
      return parseWithCommand(filePath, 'xlsx');

    case '.pptx':
      return parseWithCommand(filePath, 'pptx');

    default:
      return { text: '', error: `Unsupported format: ${ext}` };
  }
}

async function parsePlainText(filePath: string): Promise<ParsedContent> {
  try {
    const content = await readTextFile(filePath);
    return { text: content };
  } catch (err) {
    return { text: '', error: `Failed to read file: ${err instanceof Error ? err.message : String(err)}` };
  }
}

/**
 * Parse binary format using external tools via Tauri shell.
 * Placeholder — actual implementation depends on available tools (python, pandoc, etc.).
 * For now, returns an error message prompting the user to install conversion tools.
 */
async function parseWithCommand(filePath: string, _format: string): Promise<ParsedContent> {
  // Binary parsing will be implemented via the knowledge_index_local tool's
  // lark-cli integration, which handles PDF/DOCX/XLSX conversion.
  // This module provides the framework; actual execution goes through
  // lark-cli or Python scripts managed by the knowledge tools.
  return {
    text: '',
    error: `Binary format parsing will be handled by lark-cli integration. File: ${filePath}`,
  };
}

/**
 * Chunk text content into manageable pieces for indexing.
 * Splits on paragraph boundaries; each chunk ≤ 4000 chars.
 */
export function chunkText(text: string, maxChunkSize = 4000): string[] {
  if (text.length <= maxChunkSize) return [text];

  const chunks: string[] = [];
  const paragraphs = text.split(/\n\s*\n/);

  let current = '';
  for (const para of paragraphs) {
    if (current.length + para.length + 2 > maxChunkSize && current.length > 0) {
      chunks.push(current.trim());
      current = para;
    } else {
      current += (current ? '\n\n' : '') + para;
    }
  }
  if (current.trim()) {
    chunks.push(current.trim());
  }

  return chunks.length > 0 ? chunks : [text.slice(0, maxChunkSize)];
}
