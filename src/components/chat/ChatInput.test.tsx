import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { DREAMINA_AGENT_NAME } from '@/core/agent/registry';
import { setLanguage } from '@/i18n';
import { useChatStore } from '@/stores/chatStore';
import { useDiscoveryStore } from '@/stores/discoveryStore';
import { useSettingsStore } from '@/stores/settingsStore';

import ChatInput from './ChatInput';

vi.mock('@/hooks/useFileDragDrop', () => ({
  useFileDragDrop: () => ({ isDragging: false }),
}));

vi.mock('@/components/chat/ModelSelector', () => ({
  CapabilityBadge: () => null,
  ModelSelector: () => null,
}));

vi.mock('@/components/chat/AgentSelector', () => ({
  default: ({ selectedName }: { selectedName: string | null }) => (
    <div data-testid="agent-selector">{selectedName ?? 'none'}</div>
  ),
}));

vi.mock('@/components/chat/SkillSelector', () => ({
  default: () => null,
}));

vi.mock('@/components/common/FolderSelector', () => ({
  default: () => null,
}));

vi.mock('@/components/common/PermissionDialog', () => ({
  default: () => null,
}));

vi.mock('@/components/chat/PromoteToProjectHint', () => ({
  default: () => null,
}));

describe('ChatInput', () => {
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
      agentStatus: 'idle',
      currentTool: null,
      currentUsage: null,
      pendingInput: null,
      inputResetVersion: 0,
      pendingAgentSurface: null,
      pendingAgentName: null,
      thinkingStartTime: null,
      activeAgentNames: [],
    });
    useDiscoveryStore.setState({
      skills: [],
      agents: [
        {
          name: DREAMINA_AGENT_NAME,
          description: 'Dreamina agent',
        },
      ],
      isLoading: false,
    });
    useSettingsStore.setState({
      disabledAgents: [],
      disabledSkills: [],
    });
  });

  it('clears a consumed pending agent draft when starting a fresh task from the welcome screen', async () => {
    const { container } = render(<ChatInput variant="welcome" onSend={vi.fn()} />);
    const textarea = container.querySelector('textarea');
    expect(textarea).not.toBeNull();

    act(() => {
      useChatStore.getState().setPendingInput(`@${DREAMINA_AGENT_NAME} 帮我生成图片`);
    });

    expect(await screen.findByText(`@${DREAMINA_AGENT_NAME}`)).toBeInTheDocument();
    await waitFor(() => expect(textarea).toHaveValue('帮我生成图片'));

    act(() => {
      useChatStore.getState().startNewConversation();
    });

    await waitFor(() => {
      expect(screen.queryByText(`@${DREAMINA_AGENT_NAME}`)).not.toBeInTheDocument();
      expect(textarea).toHaveValue('');
    });
  });

  it('adds selected image generation controls to creation messages', async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();

    setLanguage('en-US');
    render(<ChatInput variant="welcome" presentation="creation" creationMode="image" onSend={onSend} />);

    expect(screen.getByRole('button', { name: 'Add reference image' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Image 4\.7/ })).toBeInTheDocument();
    expect(screen.queryByTestId('agent-selector')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /1:1/ }));
    await user.click(screen.getByRole('button', { name: 'Aspect ratio 16:9' }));
    await user.click(screen.getByRole('button', { name: /Ultra 4K/ }));
    await user.type(screen.getByRole('textbox'), 'Generate a product hero image');
    await user.click(screen.getByRole('button', { name: 'Start' }));

    expect(onSend).toHaveBeenCalledWith(
      'Generate a product hero image\nGeneration parameters: model Image 4.7; aspect ratio 16:9; resolution Ultra 4K ✦; count 1',
      undefined,
      null,
    );
  });

  it('does not show image generation controls for video creation', () => {
    setLanguage('en-US');

    render(<ChatInput variant="welcome" presentation="creation" creationMode="video" onSend={vi.fn()} />);

    expect(screen.queryByRole('button', { name: 'Add reference image' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Image 4\.7/ })).not.toBeInTheDocument();
  });

  it('renders the image model selector as a constrained scrollable popover', async () => {
    const user = userEvent.setup();
    setLanguage('en-US');

    render(<ChatInput variant="welcome" presentation="creation" creationMode="image" onSend={vi.fn()} />);

    await user.click(screen.getByRole('button', { name: /Image 4\.7/ }));

    const modelPanel = screen.getByRole('dialog', { name: 'Choose model' });
    expect(modelPanel).toHaveClass('absolute');
    expect(modelPanel).toHaveClass('overflow-y-auto');
    expect(modelPanel.className).toContain('max-h-');
  });
});
