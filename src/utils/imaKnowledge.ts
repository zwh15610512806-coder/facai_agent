import { openUrl } from '@tauri-apps/plugin-opener';

export const IMA_WEB_URL = 'https://ima.qq.com';

export async function openImaKnowledgeBase(): Promise<void> {
  await openUrl(IMA_WEB_URL);
}
