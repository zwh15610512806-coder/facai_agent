import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  getFileSearchIndexStatus,
  openFileSearchFile,
  previewFileSearchFile,
  queryFileSearch,
  getFileSearchEntityCandidates,
  startFileSearchIndex,
} from '@/core/fileSearch/client';
import { parseFileSearchWithAi } from '@/core/fileSearch/aiSearch';
import { useSettingsStore } from '@/stores/settingsStore';

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

describe('FileSearchView AI search', () => {
  beforeEach(() => {
    vi.mocked(queryFileSearch).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(getFileSearchIndexStatus).mockResolvedValue({
      phase: 'idle',
      running: false,
      current: 0,
      total: 0,
      percent: 0,
      message: '',
      totalFiles: 0,
    });
    vi.mocked(previewFileSearchFile).mockResolvedValue({
      id: 1,
      kind: 'missing',
      filePath: '',
      fileName: '',
    });
    vi.mocked(openFileSearchFile).mockResolvedValue(undefined);
    vi.mocked(getFileSearchEntityCandidates).mockResolvedValue(['刀叉']);
    vi.mocked(startFileSearchIndex).mockResolvedValue({
      phase: 'idle',
      running: false,
      current: 0,
      total: 0,
      percent: 0,
      message: '',
      totalFiles: 0,
    });
    vi.mocked(parseFileSearchWithAi).mockResolvedValue({
      usedFallback: false,
      query: {
        query: '刀叉',
        keywords: ['刀叉'],
        hardTerms: ['刀叉'],
        softTerms: [],
        dateFrom: '2026-05-01',
        dateTo: '2026-05-26',
      },
      intent: {
        hardTerms: ['刀叉'],
        softTerms: [],
        dateFrom: '2026-05-01',
        dateTo: '2026-05-26',
        summary: '我理解你在找：这个月的刀叉相关文件',
        source: 'ai',
        conditions: [
          { id: 'term:刀叉', type: 'term', value: '刀叉', label: '刀叉', strength: 'hard', removable: true },
          { id: 'date:2026-05-01:2026-05-26', type: 'dateRange', value: '2026-05-01:2026-05-26', label: '2026-05-01 至 2026-05-26', removable: true },
        ],
      },
      understanding: {
        summary: '我理解你在找：这个月的刀叉相关文件',
        keywords: ['刀叉'],
        hardTerms: ['刀叉'],
        softTerms: [],
        dateFrom: '2026-05-01',
        dateTo: '2026-05-26',
        conditions: [
          { id: 'term:刀叉', type: 'term', value: '刀叉', label: '刀叉', strength: 'hard', removable: true },
          { id: 'date:2026-05-01:2026-05-26', type: 'dateRange', value: '2026-05-01:2026-05-26', label: '2026-05-01 至 2026-05-26', removable: true },
        ],
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

  it('uses AI search by default and shows the model understanding', async () => {
    const user = userEvent.setup();
    render(<FileSearchView />);

    const input = screen.getByPlaceholderText(/搜索文件名|Search file/i);
    await user.type(input, '这个月拍的刀叉素材');
    await user.click(screen.getByRole('button', { name: /AI 搜索|AI Search/i }));

    await waitFor(() => {
      expect(parseFileSearchWithAi).toHaveBeenCalledWith('这个月拍的刀叉素材', expect.any(Object));
    });
    expect(queryFileSearch).toHaveBeenLastCalledWith(expect.objectContaining({
      hardTerms: ['刀叉'],
      dateFrom: '2026-05-01',
      dateTo: '2026-05-26',
    }));
    expect(screen.getByText('我理解你在找：这个月的刀叉相关文件')).toBeInTheDocument();
  });

  it('reruns the precise search after removing an AI condition tag', async () => {
    const user = userEvent.setup();
    render(<FileSearchView />);

    const input = screen.getByPlaceholderText(/搜索文件名|Search file/i);
    await user.type(input, '这个月拍的刀叉素材');
    await user.click(screen.getByRole('button', { name: /AI 搜索|AI Search/i }));

    await waitFor(() => {
      expect(queryFileSearch).toHaveBeenLastCalledWith(expect.objectContaining({
        hardTerms: ['刀叉'],
        dateFrom: '2026-05-01',
      }));
    });

    await user.click(screen.getByRole('button', { name: /移除条件：刀叉|Remove condition: 刀叉/i }));

    await waitFor(() => {
      expect(queryFileSearch).toHaveBeenLastCalledWith(expect.objectContaining({
        hardTerms: [],
        dateFrom: '2026-05-01',
        dateTo: '2026-05-26',
      }));
    });
  });
});
