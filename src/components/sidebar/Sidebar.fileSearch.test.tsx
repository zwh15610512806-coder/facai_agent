import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { openUrl } from '@tauri-apps/plugin-opener';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { DREAMINA_AGENT_NAME } from '@/core/agent/registry';
import { setLanguage } from '@/i18n';
import { useChatStore } from '@/stores/chatStore';
import { useSettingsStore } from '@/stores/settingsStore';

import Sidebar from './Sidebar';

vi.mock('@/components/sidebar/ProjectsSection', () => ({ default: () => null }));
vi.mock('@/components/common/GuideModal', () => ({ default: () => null }));
vi.mock('@/components/common/ProfileEditModal', () => ({ default: () => null }));
vi.mock('@/components/share/ShareExportDialog', () => ({ default: () => null }));

describe('Sidebar file search entry', () => {
  afterEach(() => {
    cleanup();
    setLanguage('system');
  });

  beforeEach(() => {
    setLanguage('zh-CN');
    useChatStore.setState({
      conversations: {},
      conversationIndex: {},
      activeConversationId: null,
      pendingInput: null,
      pendingAgentSurface: null,
      pendingAgentName: null,
    });
    useSettingsStore.setState({
      viewMode: 'chat',
      guideShown: true,
      updateInfo: null,
    });
    vi.clearAllMocks();
  });

  it('opens a knowledge-base welcome chat without opening IMA externally', async () => {
    const user = userEvent.setup();

    render(<Sidebar />);

    await user.click(screen.getByRole('button', { name: /Knowledge Base|知识库/i }));

    expect(useSettingsStore.getState().viewMode).toBe('chat');
    expect(useChatStore.getState().activeConversationId).toBeNull();
    expect(useChatStore.getState().pendingAgentSurface).toBe('knowledge');
    expect(useChatStore.getState().pendingInput).toMatch(/^\/ima-skills /);
    expect(openUrl).not.toHaveBeenCalled();
  });

  it('opens the file search primary view', async () => {
    const user = userEvent.setup();

    render(<Sidebar />);

    await user.click(screen.getByRole('button', { name: /File Search|网盘检索/i }));

    expect(useSettingsStore.getState().viewMode).toBe('fileSearch');
  });

  it('starts Dreamina image and video creation entries directly below new task', async () => {
    const user = userEvent.setup();

    render(<Sidebar />);

    const navButtons = within(screen.getByRole('navigation', { name: 'Main navigation' })).getAllByRole('button');
    expect(navButtons[0]).toHaveTextContent('新建任务');
    expect(navButtons[1]).toHaveTextContent('图像生成');
    expect(navButtons[2]).toHaveTextContent('视频生成');

    await user.click(navButtons[1]);

    expect(useSettingsStore.getState().viewMode).toBe('chat');
    expect(useChatStore.getState().activeConversationId).toBeNull();
    expect(useChatStore.getState().pendingAgentName).toBe(DREAMINA_AGENT_NAME);
    expect(useChatStore.getState().pendingAgentSurface).toBe('dreamina-image');
    expect(useChatStore.getState().pendingInput).toBe(`@${DREAMINA_AGENT_NAME} 帮我用即梦生成图片素材。检查 dreamina CLI 图片生成相关帮助和账号点数。`);

    await user.click(navButtons[2]);

    expect(useSettingsStore.getState().viewMode).toBe('chat');
    expect(useChatStore.getState().activeConversationId).toBeNull();
    expect(useChatStore.getState().pendingAgentName).toBe(DREAMINA_AGENT_NAME);
    expect(useChatStore.getState().pendingAgentSurface).toBe('dreamina-video');
    expect(useChatStore.getState().pendingInput).toBe(`@${DREAMINA_AGENT_NAME} 帮我用seedance生成视频素材。检查 dreamina CLI 图片生成相关帮助和账号点数。`);
  });
});
