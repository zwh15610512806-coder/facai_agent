import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { parse as parseYaml } from 'yaml';
import { describe, expect, it } from 'vitest';

type ExpectedSkill = {
  dir: string;
  name: string;
  supportFiles?: string[];
};

const EXPECTED_IMPORTED_SKILLS: ExpectedSkill[] = [
  { dir: 'nano-banana-pro', name: 'nano-banana-pro' },
  { dir: 'android-native-dev', name: 'android-native-dev' },
  { dir: 'darwin-skill', name: 'darwin-skill' },
  { dir: 'facai-video-script', name: 'facai-video-script' },
  { dir: 'github', name: 'github' },
  { dir: 'gog', name: 'gog' },
  { dir: 'gpt-image-2', name: 'gpt-image-2' },
  { dir: 'kb-retriever', name: 'kb-retriever' },
  { dir: 'obsidian', name: 'obsidian' },
  { dir: 'qq-email', name: 'qq-email' },
  { dir: 'skills-security-check', name: 'skills-security-check' },
  { dir: 'superpower', name: 'superpower' },
  { dir: 'web-access', name: 'web-access' },
  { dir: 'web-deploy-github', name: 'web-deploy-github' },
  { dir: 'web-design-engineer', name: 'web-design-engineer' },
  { dir: 'wechat-publisher', name: 'wechat-publisher' },
  { dir: 'frontend-dev', name: 'frontend-dev' },
  { dir: 'humanizer', name: 'humanizer' },
  { dir: 'browser-use', name: 'browser-use' },
  { dir: 'baidu-drive', name: 'baidu-drive' },
  { dir: 'resume-assistant', name: 'resume-assistant' },
  { dir: 'meituan-coupon-workbuddy', name: 'meituan-coupon-workbuddy' },
  { dir: 'ima-skills', name: 'ima-skills' },
  { dir: 'tencent-news', name: 'tencent-news' },
  { dir: 'english-intensive-reader', name: 'english-intensive-reader' },
  {
    dir: 'lark-unified',
    name: 'lark-unified',
    supportFiles: ['scripts/lark_setup.py', 'references/lark-shared.md'],
  },
];

function readFrontmatter(filePath: string): Record<string, unknown> {
  const raw = readFileSync(filePath, 'utf8');
  const match = raw.match(/^---\s*\n([\s\S]*?)\n---\s*\n/);
  if (!match) {
    throw new Error(`Missing frontmatter in ${filePath}`);
  }
  return parseYaml(match[1]) as Record<string, unknown>;
}

describe('bundled builtin skills', () => {
  it('includes the imported WorkBuddy skill packages and required resources', () => {
    for (const expectedSkill of EXPECTED_IMPORTED_SKILLS) {
      const skillDir = path.resolve(process.cwd(), 'builtin-skills', expectedSkill.dir);
      const skillFile = path.join(skillDir, 'SKILL.md');

      expect(existsSync(skillDir), `Missing skill dir: ${expectedSkill.dir}`).toBe(true);
      expect(existsSync(skillFile), `Missing SKILL.md for: ${expectedSkill.dir}`).toBe(true);

      const frontmatter = readFrontmatter(skillFile);
      expect(frontmatter.name, `Unexpected skill name for: ${expectedSkill.dir}`).toBe(expectedSkill.name);

      for (const supportFile of expectedSkill.supportFiles ?? []) {
        expect(
          existsSync(path.join(skillDir, supportFile)),
          `Missing support file "${supportFile}" for: ${expectedSkill.dir}`,
        ).toBe(true);
      }
    }
  });
});
