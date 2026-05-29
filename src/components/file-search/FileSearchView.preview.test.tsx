import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { convertFileSrc } from '@tauri-apps/api/core';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  getFileSearchIndexStatus,
  openFileSearchFile,
  previewFileSearchFile,
  queryFileSearch,
  startFileSearchIndex,
} from '@/core/fileSearch/client';
import { parseFileSearchWithAi } from '@/core/fileSearch/aiSearch';
import { initLanguage } from '@/i18n';
import { useSettingsStore } from '@/stores/settingsStore';

import FileSearchView from './FileSearchView';

vi.mock('@/core/fileSearch/client', () => ({
  queryFileSearch: vi.fn(),
  getFileSearchIndexStatus: vi.fn(),
  previewFileSearchFile: vi.fn(),
  openFileSearchFile: vi.fn(),
  startFileSearchIndex: vi.fn(),
}));

vi.mock('@/core/fileSearch/aiSearch', () => ({
  parseFileSearchWithAi: vi.fn(),
}));

describe('FileSearchView preview', () => {
  beforeEach(() => {
    initLanguage('en-US');
    vi.mocked(convertFileSrc).mockClear();
    vi.mocked(getFileSearchIndexStatus).mockResolvedValue({
      phase: 'idle',
      running: false,
      current: 0,
      total: 0,
      percent: 0,
      message: '',
      totalFiles: 0,
    });
    vi.mocked(openFileSearchFile).mockResolvedValue(undefined);
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
    initLanguage('system');
  });

  it('shows an open action when an asset preview fails to load', async () => {
    const filePath = '\\\\192.168.0.118\\share\\video.mp4';
    vi.mocked(queryFileSearch).mockResolvedValue({
      items: [{
        id: 42,
        filePath,
        fileName: 'video.mp4',
        parentFolder: '\\\\192.168.0.118\\share',
        fileExtension: 'mp4',
        fileSize: 32 * 1024 * 1024,
        fileModified: 1_779_780_000,
        fileType: 'video',
        indexedAt: 1_779_800_000,
      }],
      total: 1,
    });
    vi.mocked(previewFileSearchFile).mockResolvedValue({
      id: 42,
      kind: 'video',
      filePath,
      fileName: 'video.mp4',
      mimeType: 'video/mp4',
    });

    const { container } = render(<FileSearchView />);

    await waitFor(() => {
      expect(container.querySelector('video')).toBeInTheDocument();
    });
    fireEvent.error(container.querySelector('video') as HTMLVideoElement);

    expect(await screen.findByText(/Preview failed to load/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /Open with system app/i }));
    expect(openFileSearchFile).toHaveBeenCalledWith(42);
  });

  it('uses prepared local asset paths when available', async () => {
    const filePath = '\\\\192.168.0.118\\share\\video.mp4';
    const assetPath = 'C:\\Users\\test\\AppData\\Local\\com.caibao.app.dev\\file-search-preview\\42.mp4';
    vi.mocked(queryFileSearch).mockResolvedValue({
      items: [{
        id: 42,
        filePath,
        fileName: 'video.mp4',
        parentFolder: '\\\\192.168.0.118\\share',
        fileExtension: 'mp4',
        fileSize: 32 * 1024 * 1024,
        fileModified: 1_779_780_000,
        fileType: 'video',
        indexedAt: 1_779_800_000,
      }],
      total: 1,
    });
    vi.mocked(previewFileSearchFile).mockResolvedValue({
      id: 42,
      kind: 'video',
      filePath,
      assetPath,
      fileName: 'video.mp4',
      mimeType: 'video/mp4',
    });

    const { container } = render(<FileSearchView />);

    await waitFor(() => {
      expect(container.querySelector('video')).toBeInTheDocument();
    });
    expect(convertFileSrc).toHaveBeenCalledWith(assetPath);
  });

  it('offers to connect the netdisk when a network file is unreachable', async () => {
    const filePath = '\\\\192.168.0.118\\share\\video.mp4';
    vi.mocked(queryFileSearch).mockResolvedValue({
      items: [{
        id: 42,
        filePath,
        fileName: 'video.mp4',
        parentFolder: '\\\\192.168.0.118\\share',
        fileExtension: 'mp4',
        fileSize: 32 * 1024 * 1024,
        fileModified: 1_779_780_000,
        fileType: 'video',
        indexedAt: 1_779_800_000,
      }],
      total: 1,
    });
    vi.mocked(previewFileSearchFile).mockResolvedValue({
      id: 42,
      kind: 'unreachable',
      filePath,
      fileName: 'video.mp4',
      mimeType: 'video/mp4',
    });

    render(<FileSearchView />);

    expect(await screen.findByText(/cannot read the netdisk file/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /Connect netdisk/i }));
    expect(openFileSearchFile).toHaveBeenCalledWith(42);
  });
});
