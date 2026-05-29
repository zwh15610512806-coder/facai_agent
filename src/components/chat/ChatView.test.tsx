import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/core/agent/agentLoop', () => ({
  runAgentLoop: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('@/hooks/useAutoScroll', () => ({
  useAutoScroll: () => ({
    containerRef: { current: null },
    isAtBottom: true,
    scrollToBottom: vi.fn(),
    resetToBottom: vi.fn(),
  }),
}));

vi.mock('@/core/agent/permissionBridge', () => ({
  getPendingCommandConfirmation: vi.fn(() => null),
  resolveCommandConfirmation: vi.fn(),
  subscribeToCommandConfirmation: vi.fn(() => () => {}),
  getPendingFilePermission: vi.fn(() => null),
  resolveFilePermission: vi.fn(),
  subscribeToFilePermission: vi.fn(() => () => {}),
  getPendingWorkspaceRequest: vi.fn(() => null),
  resolveWorkspaceRequest: vi.fn(),
  subscribeToWorkspaceRequest: vi.fn(() => () => {}),
}));

const mockSetWorkspace = vi.fn();
const mockClearWorkspace = vi.fn();
vi.mock('@/stores/workspaceStore', () => ({
  useWorkspaceStore: {
    getState: () => ({
      currentPath: null,
      recentPaths: [],
      setWorkspace: mockSetWorkspace,
      clearWorkspace: mockClearWorkspace,
    }),
    subscribe: vi.fn(() => () => {}),
  },
}));

vi.mock('@/components/chat/ChatInput', () => ({
  default: ({ onSend }: { onSend: (message: string) => void }) => (
    <button type="button" onClick={() => onSend('hello')}>
      send new conversation
    </button>
  ),
}));

vi.mock('@/components/chat/MessageGroup', () => ({ default: () => null }));
vi.mock('@/components/chat/ContextWarningBar', () => ({ default: () => null }));
vi.mock('@/components/chat/BackgroundAgents', () => ({ default: () => null }));
vi.mock('@/components/chat/ScenarioGuide', () => ({
  default: ({ visible }: { visible: boolean }) => (
    visible ? <div data-testid="scenario-guide" /> : null
  ),
}));
vi.mock('@/components/chat/IMInfoBar', () => ({ default: () => null }));
vi.mock('@/components/chat/SourceInfoBar', () => ({ default: () => null }));
vi.mock('@/components/chat/ComputerUseStatusBar', () => ({ default: () => null }));
vi.mock('@/components/chat/ConvIdBadge', () => ({ default: () => null }));
vi.mock('@/components/chat/UsageChip', () => ({ default: () => null }));
vi.mock('@/components/common/PermissionDialog', () => ({ default: () => null }));
vi.mock('@/components/common/CommandConfirmDialog', () => ({ default: () => null }));

import { runAgentLoop } from '@/core/agent/agentLoop';
import { DREAMINA_AGENT_NAME } from '@/core/agent/registry';
import { setLanguage } from '@/i18n';
import { useChatStore } from '@/stores/chatStore';
import { useSettingsStore } from '@/stores/settingsStore';

import ChatView from './ChatView';

describe('ChatView', () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    setLanguage('zh-CN');
    vi.mocked(runAgentLoop).mockClear();
    mockSetWorkspace.mockClear();
    mockClearWorkspace.mockClear();

    useChatStore.setState({
      conversations: {},
      conversationIndex: {},
      activeConversationId: null,
      agentStatus: 'idle',
      currentTool: null,
      currentUsage: null,
      pendingInput: null,
      pendingAgentSurface: null,
      pendingAgentName: null,
      thinkingStartTime: null,
    });

    useSettingsStore.setState((state) => ({
      sidebarCollapsed: false,
      viewMode: 'chat',
      providers: state.providers.map((provider) => (
        provider.id === state.activeModel.providerId
          ? { ...provider, enabled: true, apiKey: 'sk-test' }
          : provider
      )),
    }));
  });

  it('keeps the left sidebar visible when starting a new conversation', async () => {
    const user = userEvent.setup();

    render(<ChatView />);

    await user.click(screen.getByRole('button', { name: 'send new conversation' }));

    await waitFor(() => expect(runAgentLoop).toHaveBeenCalled());
    expect(useSettingsStore.getState().sidebarCollapsed).toBe(false);
  });

  it('shows the scenario guide on the default welcome screen', () => {
    render(<ChatView />);

    expect(screen.getByTestId('scenario-guide')).toBeInTheDocument();
  });

  it('uses the default brand header for the Dreamina image entry', () => {
    useChatStore.setState({
      pendingAgentName: DREAMINA_AGENT_NAME,
      pendingAgentSurface: 'dreamina-image',
    });

    render(<ChatView />);

    expect(screen.getByRole('img', { name: 'CaiBao' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '交给采宝就行啦 ✨' })).toBeInTheDocument();
    expect(screen.queryByText('使用即梦进行图片创作。')).not.toBeInTheDocument();
    expect(screen.queryByTestId('scenario-guide')).not.toBeInTheDocument();
    expect(screen.queryByText(/专门调用 dreamina CLI 进行即梦图片、视频与多模态生成/)).not.toBeInTheDocument();
  });

  it('uses the default brand header for the Dreamina video entry', () => {
    useChatStore.setState({
      pendingAgentName: DREAMINA_AGENT_NAME,
      pendingAgentSurface: 'dreamina-video',
    });

    render(<ChatView />);

    expect(screen.getByRole('img', { name: 'CaiBao' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '交给采宝就行啦 ✨' })).toBeInTheDocument();
    expect(screen.queryByText('使用seedance2.0进行视频创作。')).not.toBeInTheDocument();
    expect(screen.queryByTestId('scenario-guide')).not.toBeInTheDocument();
    expect(screen.queryByText(/专门调用 dreamina CLI 进行即梦图片、视频与多模态生成/)).not.toBeInTheDocument();
  });
});
