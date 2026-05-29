import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { useSettingsStore } from '@/stores/settingsStore';

import SystemSettingsView from './SystemSettingsModal';

describe('SystemSettingsView', () => {
  beforeEach(() => {
    useSettingsStore.setState({
      activeSystemTab: 'usage',
      viewMode: 'settings',
    });
  });

  it('does not show the feedback settings section', () => {
    render(<SystemSettingsView />);

    expect(screen.queryByRole('button', { name: /反馈|Feedback/i })).not.toBeInTheDocument();
  });
});
