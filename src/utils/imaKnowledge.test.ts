import { openUrl } from '@tauri-apps/plugin-opener';
import { describe, expect, it, vi } from 'vitest';

import { IMA_WEB_URL, openImaKnowledgeBase } from './imaKnowledge';

describe('openImaKnowledgeBase', () => {
  it('opens the IMA web app for knowledge uploads', async () => {
    await openImaKnowledgeBase();

    expect(IMA_WEB_URL).toBe('https://ima.qq.com');
    expect(vi.mocked(openUrl)).toHaveBeenCalledWith('https://ima.qq.com');
  });
});
