import { describe, expect, it } from 'vitest';

import { DREAMINA_AGENT_NAME, agentRegistry } from './registry';

describe('Dreamina builtin agent', () => {
  it('registers a command-capable AIGC creation agent', async () => {
    await agentRegistry.discoverAgents();

    const agent = agentRegistry.getAgent(DREAMINA_AGENT_NAME);

    expect(agent).toBeDefined();
    expect(DREAMINA_AGENT_NAME).not.toMatch(/\s/);
    expect(agent?.displayNames?.['zh-CN']).toBe('即梦 AIGC 创作');
    expect(agent?.tools).toContain('run_command');
    expect(agent?.systemPrompt).toContain('dreamina -h');
    expect(agent?.systemPrompt).toContain('$env:USERPROFILE\\bin\\dreamina.exe');
    expect(agent?.systemPrompt).toContain('dreamina <subcommand> -h');
    expect(agent?.systemPrompt).toContain('user_credit');
    expect(agent?.systemPrompt).toContain('可能消耗点数');
  });
});
