import { beforeEach, describe, expect, it, vi } from 'vitest';

import { llmCall } from '@/core/llm/llmCall';
import { useSettingsStore } from '@/stores/settingsStore';

import { parseFileSearchWithAi } from './aiSearch';

vi.mock('@/core/llm/llmCall', () => ({
  llmCall: vi.fn(),
}));

describe('parseFileSearchWithAi', () => {
  beforeEach(() => {
    vi.mocked(llmCall).mockReset();
    const providers = useSettingsStore.getState().providers.map((provider) => ({
      ...provider,
      enabled: provider.id === 'qiniu',
      apiKey: provider.id === 'qiniu' ? 'test-key' : '',
    }));
    useSettingsStore.setState({
      providers,
      activeModel: { providerId: 'qiniu', modelId: 'deepseek/deepseek-v3.2-251201' },
    });
  });

  it('sanitizes AI understanding and falls back to local values for invalid fields', async () => {
    vi.mocked(llmCall).mockResolvedValue({
      text: JSON.stringify({
        keywords: ['合同', '  pdf  ', ''],
        fileType: 'not-a-type',
        extension: '.PDF',
        dateFrom: '2026-05-01',
        dateTo: 'bad-date',
        sortBy: 'size_desc',
        summary: '寻找合同 PDF',
      }),
      toolCalls: [],
    });

    const result = await parseFileSearchWithAi('最近修改的 pdf 合同');

    expect(result.usedFallback).toBe(false);
    expect(result.query).toMatchObject({
      query: '合同',
      keywords: ['合同'],
      fileType: 'document',
      extension: 'pdf',
      sortBy: 'size_desc',
      dateFrom: '2026-05-01',
    });
    expect(result.query.dateTo).toBeUndefined();
    expect(result.understanding).toMatchObject({
      summary: '寻找合同 PDF',
      keywords: ['合同'],
      extension: 'pdf',
      dateFrom: '2026-05-01',
    });
  });

  it('cleans over-merged AI keywords with local parsing rules', async () => {
    vi.mocked(llmCall).mockResolvedValue({
      text: JSON.stringify({
        keywords: ['五月裳羽剪'],
        fileType: 'video',
        summary: '搜索五月裳羽剪的视频',
      }),
      toolCalls: [],
    });

    const result = await parseFileSearchWithAi('五月裳羽剪的视频');

    expect(result.usedFallback).toBe(false);
    expect(result.query).toMatchObject({
      query: '裳羽',
      keywords: ['裳羽'],
      hardTerms: ['裳羽'],
      softTerms: [],
      fileType: 'video',
      dateFrom: '2026-05-01',
      dateTo: '2026-05-31',
    });
    expect(result.understanding.keywords).toEqual(['裳羽']);
    expect(result.intent).toMatchObject({
      hardTerms: ['裳羽'],
      softTerms: [],
      source: 'ai',
    });
  });

  it('moves unknown AI terms to soft terms when entity validation rejects them', async () => {
    vi.mocked(llmCall).mockResolvedValue({
      text: JSON.stringify({
        keywords: ['不存在的项目', '裳羽'],
        fileType: 'video',
        summary: '搜索裳羽的视频',
      }),
      toolCalls: [],
    });

    const result = await parseFileSearchWithAi('裳羽的视频', {
      getEntityCandidates: async (query) => (query === '裳羽' ? ['裳羽'] : []),
    });

    expect(result.query).toMatchObject({
      hardTerms: ['裳羽'],
      softTerms: ['不存在的项目'],
      fileType: 'video',
    });
    expect(result.understanding.conditions).toEqual(expect.arrayContaining([
      expect.objectContaining({ type: 'term', value: '裳羽', strength: 'hard' }),
      expect.objectContaining({ type: 'term', value: '不存在的项目', strength: 'soft' }),
    ]));
  });

  it('returns local rule understanding when the model call fails', async () => {
    vi.mocked(llmCall).mockRejectedValue(new Error('offline'));

    const result = await parseFileSearchWithAi('这个月拍的刀叉素材');

    expect(result.usedFallback).toBe(true);
    expect(result.query).toMatchObject({
      query: '刀叉',
      keywords: ['刀叉'],
      dateFrom: expect.stringMatching(/^\d{4}-\d{2}-01$/),
    });
    expect(result.understanding.keywords).toEqual(['刀叉']);
  });
});
