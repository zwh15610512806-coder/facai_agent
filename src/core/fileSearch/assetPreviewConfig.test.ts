import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

describe('file search asset preview config', () => {
  it('enables Tauri asset protocol for file previews', () => {
    const configPath = resolve(process.cwd(), 'src-tauri/tauri.conf.json');
    const config = JSON.parse(readFileSync(configPath, 'utf8')) as {
      app?: {
        security?: {
          csp?: string;
          assetProtocol?: {
            enable?: boolean;
            scope?: string[];
          };
        };
      };
    };

    const security = config.app?.security;
    expect(security?.assetProtocol?.enable).toBe(true);
    expect(security?.assetProtocol?.scope).toContain('**');
    expect(security?.csp).toContain('img-src');
    expect(security?.csp).toContain('media-src');
    expect(security?.csp).toContain('frame-src');
    expect(security?.csp).toContain('asset:');
    expect(security?.csp).toContain('http://asset.localhost');
  });
});
