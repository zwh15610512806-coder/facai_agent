import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { parseFileSearchIntent, parseFileSearchPrompt } from './queryParser';

describe('parseFileSearchPrompt', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-05-26T10:00:00+08:00'));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('extracts document type, extension, sort order, and remaining keywords', () => {
    const result = parseFileSearchPrompt('最近修改的 pdf 合同');

    expect(result).toMatchObject({
      query: '合同',
      keywords: ['合同'],
      fileType: 'document',
      extension: 'pdf',
      sortBy: 'modified_desc',
    });
  });

  it('extracts product keywords and this-month date range from natural language', () => {
    expect(parseFileSearchPrompt('这个月拍的刀叉素材')).toMatchObject({
      query: '刀叉',
      keywords: ['刀叉'],
      dateFrom: '2026-05-01',
      dateTo: '2026-05-26',
    });
  });

  it('keeps person and product names as separate keywords', () => {
    expect(parseFileSearchPrompt('裳羽剪的刀叉')).toMatchObject({
      query: '裳羽 刀叉',
      keywords: ['裳羽', '刀叉'],
    });
  });

  it('treats explicit month words as date ranges instead of keywords', () => {
    expect(parseFileSearchPrompt('五月裳羽剪的视频')).toMatchObject({
      query: '裳羽',
      keywords: ['裳羽'],
      fileType: 'video',
      dateFrom: '2026-05-01',
      dateTo: '2026-05-31',
    });
  });

  it('builds precise intent from natural language with hard entity terms only', () => {
    expect(parseFileSearchIntent('五月裳羽剪的视频')).toMatchObject({
      hardTerms: ['裳羽'],
      softTerms: [],
      fileType: 'video',
      dateFrom: '2026-05-01',
      dateTo: '2026-05-31',
      source: 'local',
    });
  });

  it('keeps product and person entities as hard terms in intent', () => {
    expect(parseFileSearchIntent('调味果酱裳羽5月视频')).toMatchObject({
      hardTerms: ['调味果酱', '裳羽'],
      softTerms: [],
      fileType: 'video',
      dateFrom: '2026-05-01',
      dateTo: '2026-05-31',
    });
  });

  it('extracts last-week date range and image type', () => {
    expect(parseFileSearchPrompt('上周图片')).toMatchObject({
      fileType: 'image',
      dateFrom: '2026-05-18',
      dateTo: '2026-05-24',
    });
  });

  it('keeps plain search text when no structured hint is present', () => {
    expect(parseFileSearchPrompt('品牌手册')).toMatchObject({
      query: '品牌手册',
      keywords: ['品牌手册'],
    });
  });
});
