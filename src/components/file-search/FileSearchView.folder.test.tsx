import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  getFileSearchIndexStatus,
  openFileSearchFile,
  previewFileSearchFile,
  queryFileSearch,
  startFileSearchIndex,
} from '@/core/fileSearch/client';
import { parseFileSearchWithAi } from '@/core/fileSearch/aiSearch';
import { useSettingsStore } from '@/stores/settingsStore';
import type { FileSearchResult } from '@/types/fileSearch';

import FileSearchView from './FileSearchView';

vi.mock('@/core/fileSearch/client', () => ({
  queryFileSearch: vi.fn(),
  getFileSearchIndexStatus: vi.fn(),
  previewFileSearchFile: vi.fn(),
  openFileSearchFile: vi.fn(),
  getFileSearchEntityCandidates: vi.fn(),
  startFileSearchIndex: vi.fn(),
}));

vi.mock('@/core/fileSearch/aiSearch', () => ({
  parseFileSearchWithAi: vi.fn(),
}));

const folderResult: FileSearchResult = {
  id: 10,
  filePath: 'C:\\Share\\Assets',
  fileName: 'Assets',
  parentFolder: 'Share',
  fileExtension: '',
  fileSize: 0,
  fileModified: 1_779_780_000,
  fileType: 'folder',
  indexedAt: 1_779_800_000,
};

const childResult: FileSearchResult = {
  id: 11,
  filePath: 'C:\\Share\\Assets\\clip.mp4',
  fileName: 'clip.mp4',
  parentFolder: 'Share,Assets',
  fileExtension: 'mp4',
  fileSize: 1024,
  fileModified: 1_779_790_000,
  fileType: 'video',
  indexedAt: 1_779_800_000,
};

describe('FileSearchView folder browsing', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(queryFileSearch)
      .mockResolvedValueOnce({ items: [folderResult], total: 1 })
      .mockResolvedValueOnce({ items: [childResult], total: 1 });
    vi.mocked(getFileSearchIndexStatus).mockResolvedValue({
      phase: 'idle',
      running: false,
      current: 0,
      total: 0,
      percent: 0,
      message: '',
      totalFiles: 1,
    });
    vi.mocked(previewFileSearchFile).mockResolvedValue({
      id: 10,
      kind: 'external',
      filePath: folderResult.filePath,
      fileName: folderResult.fileName,
    });
    vi.mocked(openFileSearchFile).mockResolvedValue(undefined);
    vi.mocked(startFileSearchIndex).mockResolvedValue({
      phase: 'idle',
      running: false,
      current: 0,
      total: 0,
      percent: 0,
      message: '',
      totalFiles: 1,
    });
    vi.mocked(parseFileSearchWithAi).mockResolvedValue({
      usedFallback: true,
      query: {},
      intent: {
        hardTerms: [],
        softTerms: [],
        summary: 'Local parsing',
        source: 'fallback',
        conditions: [],
      },
      understanding: {
        summary: 'Local parsing',
        keywords: [],
      },
    });
    useSettingsStore.setState({
      fileSearchConfig: {
        pageSize: 20,
        sources: [{ id: 'share', name: 'Share', path: 'C:/Share', enabled: true }],
      },
    });
  });

  afterEach(() => {
    cleanup();
  });

  it('opens folder results by querying files inside the folder', async () => {
    const user = userEvent.setup();
    render(<FileSearchView />);

    const folderButton = await screen.findByRole('button', { name: /Assets Share -/i });
    await user.click(folderButton);

    await waitFor(() => {
      expect(queryFileSearch).toHaveBeenLastCalledWith(expect.objectContaining({
        fileType: 'all',
        folder: 'C:\\Share\\Assets\\',
        query: '',
        limit: 20,
        offset: 0,
      }));
    });
    expect(await screen.findByRole('button', { name: /clip\.mp4/i })).toBeInTheDocument();
  });

  it('returns to the previous search results after opening a folder', async () => {
    const user = userEvent.setup();
    render(<FileSearchView />);

    const folderButton = await screen.findByRole('button', { name: /Assets Share -/i });
    await user.click(folderButton);

    expect(await screen.findByRole('button', { name: /clip\.mp4/i })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Back to results|返回结果/i }));

    expect(screen.getByRole('button', { name: /Assets Share -/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /clip\.mp4/i })).not.toBeInTheDocument();
    expect(queryFileSearch).toHaveBeenCalledTimes(2);
  });
});
