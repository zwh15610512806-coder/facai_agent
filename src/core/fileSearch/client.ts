import { invoke } from '@tauri-apps/api/core';

import type {
  FileSearchFileDetail,
  FileSearchIndexStatus,
  FileSearchPreview,
  FileSearchQuery,
  FileSearchQueryResponse,
  FileSearchSourceConfig,
} from '@/types/fileSearch';

export async function queryFileSearch(query: FileSearchQuery): Promise<FileSearchQueryResponse> {
  return await invoke<FileSearchQueryResponse>('file_search_query', { query });
}

export async function getFileSearchFile(id: number): Promise<FileSearchFileDetail> {
  return await invoke<FileSearchFileDetail>('file_search_get_file', { id });
}

export async function previewFileSearchFile(id: number): Promise<FileSearchPreview> {
  return await invoke<FileSearchPreview>('file_search_preview', { id });
}

export async function openFileSearchFile(id: number): Promise<void> {
  await invoke<void>('file_search_open_file', { id });
}

export async function startFileSearchIndex(sources: FileSearchSourceConfig[], full = true): Promise<FileSearchIndexStatus> {
  return await invoke<FileSearchIndexStatus>('file_search_start_index', { sources, full });
}

export async function getFileSearchIndexStatus(): Promise<FileSearchIndexStatus> {
  return await invoke<FileSearchIndexStatus>('file_search_index_status');
}

export async function suggestFileSearch(query: string): Promise<string[]> {
  return await invoke<string[]>('file_search_suggest', { query });
}

export async function getFileSearchEntityCandidates(query: string): Promise<string[]> {
  return await invoke<string[]>('file_search_entity_candidates', { query });
}
