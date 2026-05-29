import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { openUrl } from '@tauri-apps/plugin-opener';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { initLanguage } from '@/i18n';
import { useChatStore } from '@/stores/chatStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { IMA_WEB_URL } from '@/utils/imaKnowledge';

import KnowledgeSection from './KnowledgeSection';

describe('KnowledgeSection IMA entry', () => {
  beforeEach(() => {
    initLanguage('en-US');
    vi.clearAllMocks();
    useChatStore.setState({
      pendingInput: null,
      pendingAgentSurface: null,
      pendingAgentName: null,
    });
    useSettingsStore.setState({
      viewMode: 'knowledge',
    });
  });

  afterEach(() => {
    cleanup();
    initLanguage('system');
  });

  it('starts the IMA skill from the knowledge section', async () => {
    const user = userEvent.setup();
    render(<KnowledgeSection />);

    await user.click(screen.getByRole('button', { name: /Use IMA skill/i }));

    expect(useSettingsStore.getState().viewMode).toBe('chat');
    expect(useChatStore.getState().pendingInput).toMatch(/^\/ima-skills /);
  });

  it('opens the external IMA knowledge base', async () => {
    const user = userEvent.setup();
    render(<KnowledgeSection />);

    await user.click(screen.getByRole('button', { name: /Open IMA/i }));

    expect(openUrl).toHaveBeenCalledWith(IMA_WEB_URL);
  });
});
