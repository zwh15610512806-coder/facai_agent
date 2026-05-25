import { invoke } from '@tauri-apps/api/core';
import type { CommandOutput } from '../tools/helpers/toolHelpers';

const DEFAULT_TIMEOUT_SEC = 30;
const LARK_CLI = 'lark-cli';

interface LarkCliResult {
  ok: boolean;
  stdout: string;
  stderr: string;
  exitCode: number;
}

/**
 * Execute a lark-cli command via Tauri shell and return parsed output.
 * Central point for all Feishu API calls — handles token, auth, and error mapping.
 */
export async function runLarkCli(
  args: string[],
  options?: { timeout?: number; cwd?: string },
): Promise<LarkCliResult> {
  const command = [LARK_CLI, ...args].join(' ');
  const timeout = options?.timeout ?? DEFAULT_TIMEOUT_SEC;

  try {
    const output = await invoke<CommandOutput>('run_shell_command', {
      command,
      cwd: options?.cwd || null,
      background: false,
      timeout: Math.min(Math.max(1, timeout), 120),
      sandboxEnabled: false,
      networkIsolation: false,
      extraWritablePaths: [],
    });

    return {
      ok: output.code === 0,
      stdout: output.stdout.trim(),
      stderr: output.stderr.trim(),
      exitCode: output.code,
    };
  } catch (err) {
    return {
      ok: false,
      stdout: '',
      stderr: err instanceof Error ? err.message : String(err),
      exitCode: -1,
    };
  }
}

/**
 * Run lark-cli and parse JSON stdout. Returns null on failure.
 */
export async function runLarkCliJson<T>(
  args: string[],
  options?: { timeout?: number },
): Promise<{ ok: true; data: T } | { ok: false; error: string }> {
  const result = await runLarkCli(args, options);

  if (!result.ok) {
    return {
      ok: false,
      error: result.stderr || result.stdout || `lark-cli exited with code ${result.exitCode}`,
    };
  }

  try {
    return { ok: true, data: JSON.parse(result.stdout) as T };
  } catch {
    return { ok: true, data: result.stdout as unknown as T };
  }
}

/**
 * Check if lark-cli is available and authenticated.
 */
export async function checkLarkCliReady(): Promise<{ ready: boolean; message: string }> {
  const result = await runLarkCli(['--version']);
  if (!result.ok) {
    return { ready: false, message: 'lark-cli 未安装或不可用，请先安装 lark-cli。' };
  }
  return { ready: true, message: result.stdout };
}
