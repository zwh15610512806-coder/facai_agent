import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { SkillMetadata } from '@/types';

import SkillSelector from './SkillSelector';

const skills: SkillMetadata[] = [
  {
    name: 'lark-doc',
    description: 'Read and edit Feishu docs',
    userInvocable: true,
  },
  {
    name: 'hidden-helper',
    description: 'Internal helper',
    userInvocable: false,
  },
];

describe('SkillSelector', () => {
  it('selects an installed invocable skill from the toolbar menu', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();

    render(
      <SkillSelector
        skills={skills}
        selectedName={null}
        onSelect={onSelect}
      />,
    );

    await user.click(screen.getByRole('button', { name: /选技能|pick skill/i }));

    expect(screen.getByText('lark-doc')).toBeInTheDocument();
    expect(screen.queryByText('hidden-helper')).not.toBeInTheDocument();

    await user.click(screen.getByText('lark-doc'));

    expect(onSelect).toHaveBeenCalledWith({
      name: 'lark-doc',
      description: 'Read and edit Feishu docs',
      trigger: undefined,
    });
  });
});
