import { useCallback, useEffect, useMemo, useState } from 'react';
import { convertFileSrc } from '@tauri-apps/api/core';
import {
  Archive,
  ArrowLeft,
  ExternalLink,
  File,
  FileText,
  Folder,
  HardDrive,
  Image,
  Loader2,
  Music,
  RefreshCw,
  Search,
  SearchX,
  Sparkles,
  Video,
  X,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Select } from '@/components/ui/select';
import { useI18n } from '@/i18n';
import { cn } from '@/lib/utils';
import { useSettingsStore } from '@/stores/settingsStore';
import type {
  FileSearchAiUnderstanding,
  FileSearchCondition,
  FileSearchFileType,
  FileSearchIndexStatus,
  FileSearchIntent,
  FileSearchPreview,
  FileSearchQuery,
  FileSearchResult,
  FileSearchSortBy,
} from '@/types/fileSearch';
import {
  getFileSearchIndexStatus,
  getFileSearchEntityCandidates,
  openFileSearchFile,
  previewFileSearchFile,
  queryFileSearch,
  startFileSearchIndex,
} from '@/core/fileSearch/client';
import { parseFileSearchWithAi } from '@/core/fileSearch/aiSearch';
import { buildIntentFromQuery, queryFromIntent, understandingFromIntent } from '@/core/fileSearch/queryParser';

type SearchMode = 'keyword' | 'ai';

interface FileSearchNavigationSnapshot {
  query: string;
  mode: SearchMode;
  fileType: FileSearchFileType;
  extension: string;
  folder: string;
  sortBy: FileSearchSortBy;
  items: FileSearchResult[];
  total: number;
  selectedId: number | null;
  aiFallback: boolean;
  aiUnderstanding: FileSearchAiUnderstanding | null;
  activeIntent: FileSearchIntent | null;
}

const EMPTY_STATUS: FileSearchIndexStatus = {
  phase: 'idle',
  running: false,
  current: 0,
  total: 0,
  percent: 0,
  message: '',
  totalFiles: 0,
};

export default function FileSearchView() {
  const { t, format } = useI18n();
  const fileSearchConfig = useSettingsStore((s) => s.fileSearchConfig);
  const [query, setQuery] = useState('');
  const [mode, setMode] = useState<SearchMode>('ai');
  const [fileType, setFileType] = useState<FileSearchFileType>('all');
  const [extension, setExtension] = useState('');
  const [folder, setFolder] = useState('');
  const [sortBy, setSortBy] = useState<FileSearchSortBy>('modified_desc');
  const [items, setItems] = useState<FileSearchResult[]>([]);
  const [total, setTotal] = useState(0);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [preview, setPreview] = useState<FileSearchPreview | null>(null);
  const [status, setStatus] = useState<FileSearchIndexStatus>(EMPTY_STATUS);
  const [loading, setLoading] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [aiFallback, setAiFallback] = useState(false);
  const [aiUnderstanding, setAiUnderstanding] = useState<FileSearchAiUnderstanding | null>(null);
  const [activeIntent, setActiveIntent] = useState<FileSearchIntent | null>(null);
  const [navigationStack, setNavigationStack] = useState<FileSearchNavigationSnapshot[]>([]);

  const enabledSources = useMemo(
    () => fileSearchConfig.sources.filter((source) => source.enabled),
    [fileSearchConfig.sources],
  );

  const typeOptions = useMemo(() => [
    { value: 'all', label: t.fileSearch.allTypes },
    { value: 'document', label: t.fileSearch.documents },
    { value: 'image', label: t.fileSearch.images },
    { value: 'video', label: t.fileSearch.videos },
    { value: 'audio', label: t.fileSearch.audio },
    { value: 'archive', label: t.fileSearch.archives },
    { value: 'folder', label: t.fileSearch.folders },
    { value: 'other', label: t.fileSearch.other },
  ], [t]);

  const sortOptions = useMemo(() => [
    { value: 'modified_desc', label: t.fileSearch.sortLatest },
    { value: 'modified_asc', label: t.fileSearch.sortOldest },
    { value: 'name_asc', label: t.fileSearch.sortName },
    { value: 'size_desc', label: t.fileSearch.sortSize },
  ], [t]);

  const applyResponse = useCallback((response: { items: FileSearchResult[]; total: number }) => {
    setItems(response.items);
    setTotal(response.total);
    const first = response.items[0] ?? null;
    setSelectedId(first?.id ?? null);
  }, []);

  const runSearch = useCallback(async () => {
    setLoading(true);
    setError(null);
    setAiFallback(false);
    setAiUnderstanding(null);
    setActiveIntent(null);
    try {
      let parsed: Partial<FileSearchQuery> = {};
      if (query.trim()) {
        if (mode === 'ai') {
          const result = await parseFileSearchWithAi(query.trim(), {
            getEntityCandidates: getFileSearchEntityCandidates,
          });
          parsed = result.query;
          setActiveIntent(result.intent);
          setAiUnderstanding(result.understanding);
          setAiFallback(result.usedFallback);
        } else {
          parsed = { query: query.trim() };
        }
      }

      const request: FileSearchQuery = {
        ...parsed,
        query: parsed.query ?? query.trim(),
        hardTerms: parsed.hardTerms ?? parsed.keywords,
        softTerms: parsed.softTerms ?? [],
        fileType: fileType === 'all' ? parsed.fileType ?? 'all' : fileType,
        extension: extension.trim() || parsed.extension,
        folder: folder.trim() || parsed.folder,
        sortBy,
        limit: fileSearchConfig.pageSize,
        offset: 0,
      };
      const response = await queryFileSearch(request);
      setNavigationStack([]);
      applyResponse(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [applyResponse, extension, fileSearchConfig.pageSize, fileType, folder, mode, query, sortBy]);

  const runIntentSearch = useCallback(async (intent: FileSearchIntent) => {
    setLoading(true);
    setError(null);
    try {
      const parsed = queryFromIntent(intent);
      const request: FileSearchQuery = {
        ...parsed,
        query: parsed.query ?? query.trim(),
        hardTerms: parsed.hardTerms ?? [],
        softTerms: parsed.softTerms ?? [],
        fileType: fileType === 'all' ? parsed.fileType ?? 'all' : fileType,
        extension: extension.trim() || parsed.extension,
        folder: folder.trim() || parsed.folder,
        sortBy,
        limit: fileSearchConfig.pageSize,
        offset: 0,
      };
      const response = await queryFileSearch(request);
      setNavigationStack([]);
      applyResponse(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [applyResponse, extension, fileSearchConfig.pageSize, fileType, folder, query, sortBy]);

  const handleRemoveCondition = useCallback((condition: FileSearchCondition) => {
    if (!activeIntent) return;
    const next = removeIntentCondition(activeIntent, condition);
    setActiveIntent(next);
    setAiUnderstanding(understandingFromIntent(next));
    void runIntentSearch(next);
  }, [activeIntent, runIntentSearch]);

  const handleResultClick = useCallback(async (item: FileSearchResult) => {
    if (item.fileType !== 'folder') {
      setSelectedId(item.id);
      return;
    }

    const folderPrefix = ensureTrailingPathSeparator(item.filePath);
    const snapshot: FileSearchNavigationSnapshot = {
      query,
      mode,
      fileType,
      extension,
      folder,
      sortBy,
      items,
      total,
      selectedId,
      aiFallback,
      aiUnderstanding,
      activeIntent,
    };
    setNavigationStack((stack) => [...stack, snapshot]);
    setLoading(true);
    setError(null);
    setQuery('');
    setFileType('all');
    setExtension('');
    setFolder(folderPrefix);
    setAiFallback(false);
    setAiUnderstanding(null);
    setActiveIntent(null);
    try {
      const response = await queryFileSearch({
        query: '',
        fileType: 'all',
        folder: folderPrefix,
        sortBy,
        limit: fileSearchConfig.pageSize,
        offset: 0,
      });
      applyResponse(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [
    activeIntent,
    aiFallback,
    aiUnderstanding,
    applyResponse,
    extension,
    fileSearchConfig.pageSize,
    fileType,
    folder,
    items,
    mode,
    query,
    selectedId,
    sortBy,
    total,
  ]);

  const handleBackToResults = useCallback(() => {
    const snapshot = navigationStack[navigationStack.length - 1];
    if (!snapshot) return;
    setNavigationStack(navigationStack.slice(0, -1));
    setQuery(snapshot.query);
    setMode(snapshot.mode);
    setFileType(snapshot.fileType);
    setExtension(snapshot.extension);
    setFolder(snapshot.folder);
    setSortBy(snapshot.sortBy);
    setItems(snapshot.items);
    setTotal(snapshot.total);
    setSelectedId(snapshot.selectedId);
    setAiFallback(snapshot.aiFallback);
    setAiUnderstanding(snapshot.aiUnderstanding);
    setActiveIntent(snapshot.activeIntent);
    setError(null);
  }, [navigationStack]);

  const refreshStatus = useCallback(async () => {
    try {
      setStatus(await getFileSearchIndexStatus());
    } catch (err) {
      console.warn('[fileSearch] status refresh failed:', err);
    }
  }, []);

  useEffect(() => {
    void refreshStatus();
    setLoading(true);
    queryFileSearch({
      fileType: 'all',
      sortBy: 'modified_desc',
      limit: fileSearchConfig.pageSize,
      offset: 0,
    })
      .then(applyResponse)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, [applyResponse, fileSearchConfig.pageSize, refreshStatus]);

  useEffect(() => {
    if (!status.running) return;
    const timer = setInterval(() => {
      void refreshStatus();
    }, 2000);
    return () => clearInterval(timer);
  }, [refreshStatus, status.running]);

  useEffect(() => {
    if (selectedId === null) {
      setPreview(null);
      return;
    }
    setPreviewLoading(true);
    previewFileSearchFile(selectedId)
      .then(setPreview)
      .catch((err) => {
        setError(err instanceof Error ? err.message : String(err));
        setPreview(null);
      })
      .finally(() => setPreviewLoading(false));
  }, [selectedId]);

  const handleStartIndex = async () => {
    setError(null);
    try {
      const next = await startFileSearchIndex(enabledSources, true);
      setStatus(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleOpenSelected = async () => {
    if (selectedId === null) return;
    try {
      await openFileSearchFile(selectedId);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const selected = items.find((item) => item.id === selectedId) ?? null;

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden bg-[var(--abu-bg-muted)]">
      <header className="shrink-0 border-b border-[var(--abu-border)] bg-[var(--abu-bg-base)] px-6 py-5">
        <div className="flex items-start justify-between gap-5">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <HardDrive className="h-5 w-5 text-[var(--abu-clay)]" strokeWidth={1.8} />
              <h1 className="text-lg font-semibold text-[var(--abu-text-primary)]">{t.fileSearch.title}</h1>
            </div>
            <p className="mt-1 text-sm text-[var(--abu-text-tertiary)]">{t.fileSearch.description}</p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <span className="whitespace-nowrap text-xs text-[var(--abu-text-tertiary)]">
              {format(t.fileSearch.sourceCount, { count: enabledSources.length })}
            </span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleStartIndex}
              disabled={status.running || enabledSources.length === 0}
              className="border-[var(--abu-border)] bg-[var(--abu-bg-base)] text-[var(--abu-text-secondary)] hover:bg-[var(--abu-bg-hover)]"
            >
              {status.running ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              {status.running ? t.fileSearch.indexing : t.fileSearch.reindex}
            </Button>
          </div>
        </div>
        <div className="mt-4 flex min-w-0 items-center gap-3">
          <div className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-[var(--abu-bg-muted)]">
            <div
              className="h-full rounded-full bg-[var(--abu-clay)] transition-all"
              style={{ width: `${Math.max(0, Math.min(100, status.percent))}%` }}
            />
          </div>
          <span className="w-40 shrink-0 truncate text-right text-xs text-[var(--abu-text-tertiary)]">
            {statusLabel(status, t.fileSearch)}
          </span>
        </div>
      </header>

      <div className="grid min-h-0 flex-1 overflow-hidden grid-cols-[minmax(520px,1fr)_minmax(300px,0.58fr)] bg-[var(--abu-bg-muted)]">
        <section className="flex min-h-0 min-w-0 flex-col overflow-hidden border-r border-[var(--abu-border)] bg-[var(--abu-bg-muted)]">
          <div className="shrink-0 space-y-3 border-b border-[var(--abu-border)] bg-[var(--abu-bg-base)] px-5 py-4">
            <div className="flex items-center gap-2">
              <div className="relative min-w-0 flex-1">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--abu-text-muted)]" />
                <Input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') void runSearch();
                  }}
                  placeholder={t.fileSearch.searchPlaceholder}
                  className="pl-9"
                />
              </div>
              <Button
                type="button"
                variant={mode === 'ai' ? 'secondary' : 'outline'}
                size="icon"
                onClick={() => setMode(mode === 'ai' ? 'keyword' : 'ai')}
                title={mode === 'ai' ? t.fileSearch.keywordSearch : t.fileSearch.aiSearch}
                className="h-9 w-9 shrink-0 border-[var(--abu-border)]"
              >
                <Sparkles className={cn('h-4 w-4', mode === 'ai' && 'text-[var(--abu-clay)]')} />
              </Button>
              <Button
                type="button"
                variant="default"
                size="sm"
                onClick={() => void runSearch()}
                disabled={loading}
                className="h-9 shrink-0 bg-[var(--abu-clay)] px-3 text-white hover:bg-[var(--abu-clay-hover)]"
              >
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
                {mode === 'ai' ? t.fileSearch.aiSearch : t.fileSearch.search}
              </Button>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <Select
                value={fileType}
                onChange={(value) => setFileType(value as FileSearchFileType)}
                options={typeOptions}
                className="min-w-0"
              />
              <Select
                value={sortBy}
                onChange={(value) => setSortBy(value as FileSearchSortBy)}
                options={sortOptions}
                className="min-w-0"
              />
              <Input
                value={extension}
                onChange={(event) => setExtension(event.target.value)}
                placeholder={t.fileSearch.extensionPlaceholder}
                className="min-w-0"
              />
              <Input
                value={folder}
                onChange={(event) => setFolder(event.target.value)}
                placeholder={t.fileSearch.folderPlaceholder}
                className="min-w-0"
              />
            </div>

            <div className="flex min-h-5 items-center gap-2 text-xs">
              {navigationStack.length > 0 && (
                <Button
                  type="button"
                  variant="ghost"
                  size="xs"
                  onClick={handleBackToResults}
                  disabled={loading}
                  className="h-6 shrink-0 px-2 text-xs text-[var(--abu-text-secondary)] hover:bg-[var(--abu-bg-hover)]"
                >
                  <ArrowLeft className="h-3.5 w-3.5" />
                  {t.fileSearch.backToResults}
                </Button>
              )}
              <span className="shrink-0 text-[var(--abu-text-tertiary)]">
                {format(t.fileSearch.resultCount, { count: total })}
              </span>
              {aiFallback && <span className="shrink-0 text-amber-600">{t.fileSearch.aiFallback}</span>}
              {error && <span className="min-w-0 flex-1 truncate text-right text-red-500">{error}</span>}
            </div>
            {mode === 'ai' && aiUnderstanding && (
              <AiUnderstandingBar understanding={aiUnderstanding} onRemoveCondition={handleRemoveCondition} />
            )}
          </div>

          <ScrollArea className="min-h-0 flex-1 bg-[var(--abu-bg-muted)]">
            <div className="px-4 py-3 pb-6">
              {loading ? (
                <div className="flex h-44 items-center justify-center text-[var(--abu-text-tertiary)]">
                  <Loader2 className="h-5 w-5 animate-spin" />
                </div>
              ) : items.length === 0 ? (
                <div className="flex h-44 flex-col items-center justify-center gap-3 text-center text-sm text-[var(--abu-text-tertiary)]">
                  <SearchX className="h-7 w-7 text-[var(--abu-text-muted)]" strokeWidth={1.6} />
                  <span>
                    {mode === 'ai' && aiUnderstanding?.conditions?.length
                      ? t.fileSearch.preciseNoResults
                      : t.fileSearch.noResults}
                  </span>
                  {mode === 'ai' && aiUnderstanding?.conditions?.length ? (
                    <span className="max-w-sm text-xs leading-5">{t.fileSearch.removeConditionHint}</span>
                  ) : null}
                </div>
              ) : (
                <div className="space-y-2">
                  {items.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => void handleResultClick(item)}
                      className={cn(
                        'flex w-full items-start gap-3 rounded-lg border px-3 py-2.5 text-left shadow-[0_1px_0_rgba(0,0,0,0.02)] transition-colors',
                        selectedId === item.id
                          ? 'border-[var(--abu-clay)] bg-[var(--abu-clay-bg)] text-[var(--abu-text-primary)]'
                          : 'border-transparent bg-[var(--abu-bg-base)] text-[var(--abu-text-secondary)] hover:border-[var(--abu-border)] hover:bg-[var(--abu-bg-hover)]',
                      )}
                    >
                      <FileTypeIcon type={item.fileType} />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-medium">
                          {highlightFileName(item.fileName, mode === 'ai' ? aiUnderstanding?.keywords ?? [] : [])}
                        </span>
                        <span className="mt-0.5 block truncate text-xs text-[var(--abu-text-tertiary)]">{item.parentFolder || item.filePath}</span>
                      </span>
                      <span className="shrink-0 text-right text-[11px] text-[var(--abu-text-tertiary)]">
                        {formatSize(item.fileSize)}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </ScrollArea>
        </section>

        <section className="flex min-h-0 min-w-0 flex-col overflow-hidden bg-[var(--abu-bg-muted)]">
          <div className="flex min-h-[56px] shrink-0 items-center justify-between gap-3 border-b border-[var(--abu-border)] bg-[var(--abu-bg-base)] px-4 py-2.5">
            <div className="min-w-0">
              <h2 className="truncate text-sm font-semibold text-[var(--abu-text-primary)]">
                {selected?.fileName ?? t.fileSearch.selectResult}
              </h2>
              {selected && (
                <p className="mt-0.5 truncate text-xs text-[var(--abu-text-tertiary)]">{selected.filePath}</p>
              )}
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void handleOpenSelected()}
              disabled={selectedId === null}
              className="shrink-0 border-[var(--abu-border)] bg-[var(--abu-bg-base)] text-[var(--abu-text-secondary)] hover:bg-[var(--abu-bg-hover)]"
            >
              <ExternalLink className="h-4 w-4" />
              {t.fileSearch.open}
            </Button>
          </div>

          <ScrollArea className="min-h-0 flex-1 bg-[var(--abu-bg-muted)]">
            <div className="p-4 pb-6">
              {selected ? (
                <div className="space-y-4">
                  <dl className="grid grid-cols-[76px_minmax(0,1fr)] gap-x-3 gap-y-2 rounded-lg border border-[var(--abu-border)] bg-[var(--abu-bg-base)] p-3 text-sm shadow-[0_1px_0_rgba(0,0,0,0.02)]">
                    <dt className="text-[var(--abu-text-tertiary)]">{t.fileSearch.fileSize}</dt>
                    <dd className="text-[var(--abu-text-primary)]">{formatSize(selected.fileSize)}</dd>
                    <dt className="text-[var(--abu-text-tertiary)]">{t.fileSearch.modifiedAt}</dt>
                    <dd className="text-[var(--abu-text-primary)]">{formatDate(selected.fileModified)}</dd>
                    <dt className="text-[var(--abu-text-tertiary)]">{t.fileSearch.indexedAt}</dt>
                    <dd className="text-[var(--abu-text-primary)]">{formatDate(selected.indexedAt)}</dd>
                    <dt className="text-[var(--abu-text-tertiary)]">{t.fileSearch.path}</dt>
                    <dd className="break-all text-[var(--abu-text-primary)]">{selected.filePath}</dd>
                  </dl>
                  <div className="space-y-3">
                    <h3 className="text-sm font-medium text-[var(--abu-text-primary)]">{t.fileSearch.preview}</h3>
                    <div className="min-h-[180px] overflow-hidden rounded-lg border border-[var(--abu-border)] bg-[var(--abu-bg-base)] shadow-[0_1px_0_rgba(0,0,0,0.02)]">
                      {previewLoading ? (
                        <div className="flex h-48 items-center justify-center text-[var(--abu-text-tertiary)]">
                          <Loader2 className="h-5 w-5 animate-spin" />
                        </div>
                      ) : (
                        <PreviewPane preview={preview} onOpen={handleOpenSelected} />
                      )}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="flex h-44 items-center justify-center">
                  <div className="flex flex-col items-center gap-2 text-center text-xs text-[var(--abu-text-tertiary)]">
                    <FileText className="h-6 w-6 text-[var(--abu-text-muted)]" strokeWidth={1.5} />
                    <span>{t.fileSearch.selectResult}</span>
                  </div>
                </div>
              )}
            </div>
          </ScrollArea>
        </section>
      </div>
    </div>
  );
}

function AiUnderstandingBar({
  understanding,
  onRemoveCondition,
}: {
  understanding: FileSearchAiUnderstanding;
  onRemoveCondition: (condition: FileSearchCondition) => void;
}) {
  const { t, format } = useI18n();
  const fallbackTags: FileSearchCondition[] = understanding.keywords.map((keyword) => ({
    id: `kw:${keyword}`,
    type: 'term',
    value: keyword,
    label: keyword,
    strength: 'hard',
    removable: true,
  }));
  if (understanding.fileType) {
    fallbackTags.push({
      id: 'type',
      type: 'fileType',
      value: understanding.fileType,
      label: `${t.fileSearch.typeLabel}: ${fileTypeLabel(understanding.fileType, t.fileSearch)}`,
      removable: true,
    });
  }
  if (understanding.extension) {
    fallbackTags.push({
      id: 'ext',
      type: 'extension',
      value: understanding.extension,
      label: `${t.fileSearch.extensionLabel}: .${understanding.extension}`,
      removable: true,
    });
  }
  if (understanding.dateFrom || understanding.dateTo) {
    fallbackTags.push({
      id: 'date',
      type: 'dateRange',
      value: `${understanding.dateFrom ?? '-'}:${understanding.dateTo ?? '-'}`,
      label: `${t.fileSearch.dateRangeLabel}: ${format(t.fileSearch.dateRangeValue, {
        from: understanding.dateFrom ?? '-',
        to: understanding.dateTo ?? '-',
      })}`,
      removable: true,
    });
  }
  const tags: FileSearchCondition[] = understanding.conditions?.length ? understanding.conditions : fallbackTags;

  return (
    <div className="rounded-lg border border-[var(--abu-border)] bg-[var(--abu-bg-muted)] px-3 py-2">
      <div className="flex items-center gap-2 text-xs text-[var(--abu-text-secondary)]">
        <Sparkles className="h-3.5 w-3.5 shrink-0 text-[var(--abu-clay)]" />
        <span className="min-w-0 truncate">{understanding.summary}</span>
      </div>
      {tags.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {tags.map((tag) => (
            <button
              key={tag.id}
              type="button"
              onClick={() => onRemoveCondition(tag)}
              aria-label={format(t.fileSearch.removeCondition, { label: conditionDisplayLabel(tag, t.fileSearch, format) })}
              className="inline-flex items-center gap-1 rounded-md border border-[var(--abu-border)] bg-[var(--abu-bg-base)] px-2 py-0.5 text-[11px] text-[var(--abu-text-tertiary)] hover:border-[var(--abu-clay)] hover:text-[var(--abu-clay)]"
            >
              {conditionDisplayLabel(tag, t.fileSearch, format)}
              <X className="h-3 w-3" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function PreviewPane({
  preview,
  onOpen,
}: {
  preview: FileSearchPreview | null;
  onOpen: () => void | Promise<void>;
}) {
  const { t } = useI18n();
  const [assetFailed, setAssetFailed] = useState(false);

  useEffect(() => {
    setAssetFailed(false);
  }, [preview?.id, preview?.filePath]);

  if (!preview) {
    return (
      <div className="flex h-48 items-center justify-center p-4 text-sm text-[var(--abu-text-tertiary)]">
        {t.fileSearch.previewUnsupported}
      </div>
    );
  }
  if (preview.kind === 'missing') {
    return (
      <div className="flex h-48 items-center justify-center p-4 text-sm text-red-500">
        {t.fileSearch.previewMissing}
      </div>
    );
  }
  if (preview.kind === 'unreachable') {
    return <PreviewUnreachable onOpen={onOpen} />;
  }
  if (preview.kind === 'text') {
    return (
      <pre className="max-h-[280px] overflow-auto whitespace-pre-wrap p-4 text-xs leading-5 text-[var(--abu-text-primary)]">
        {preview.content}
      </pre>
    );
  }
  const src = convertFileSrc(preview.assetPath ?? preview.filePath);
  if (assetFailed) {
    return <PreviewLoadFailed onOpen={onOpen} />;
  }
  if (preview.kind === 'image') {
    return (
      <img
        src={src}
        alt={preview.fileName}
        onError={() => setAssetFailed(true)}
        className="max-h-[280px] w-full object-contain"
      />
    );
  }
  if (preview.kind === 'video') {
    return (
      <video
        src={src}
        controls
        preload="metadata"
        onError={() => setAssetFailed(true)}
        className="max-h-[260px] w-full bg-black"
      />
    );
  }
  if (preview.kind === 'audio') {
    return (
      <div className="p-4">
        <audio src={src} controls onError={() => setAssetFailed(true)} className="w-full" />
      </div>
    );
  }
  if (preview.kind === 'pdf') {
    return (
      <iframe
        src={src}
        title={preview.fileName}
        onError={() => setAssetFailed(true)}
        className="h-[280px] w-full border-0"
      />
    );
  }
  return (
    <div className="flex h-48 items-center justify-center p-4 text-sm text-[var(--abu-text-tertiary)]">
      {t.fileSearch.previewUnsupported}
    </div>
  );
}

function PreviewUnreachable({ onOpen }: { onOpen: () => void | Promise<void> }) {
  const { t } = useI18n();
  return (
    <div role="alert" className="flex h-48 flex-col items-center justify-center gap-3 p-4 text-center">
      <Folder className="h-7 w-7 text-[var(--abu-text-muted)]" strokeWidth={1.5} />
      <p className="max-w-[260px] text-sm leading-6 text-red-500">{t.fileSearch.previewUnreachable}</p>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => void onOpen()}
        className="border-[var(--abu-border)] bg-[var(--abu-bg-base)] text-[var(--abu-text-secondary)] hover:bg-[var(--abu-bg-hover)]"
      >
        <ExternalLink className="h-4 w-4" />
        {t.fileSearch.connectNetworkDrive}
      </Button>
    </div>
  );
}

function PreviewLoadFailed({ onOpen }: { onOpen: () => void | Promise<void> }) {
  const { t } = useI18n();
  return (
    <div role="alert" className="flex h-48 flex-col items-center justify-center gap-3 p-4 text-center">
      <FileText className="h-7 w-7 text-[var(--abu-text-muted)]" strokeWidth={1.5} />
      <p className="text-sm text-[var(--abu-text-tertiary)]">{t.fileSearch.previewLoadFailed}</p>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => void onOpen()}
        className="border-[var(--abu-border)] bg-[var(--abu-bg-base)] text-[var(--abu-text-secondary)] hover:bg-[var(--abu-bg-hover)]"
      >
        <ExternalLink className="h-4 w-4" />
        {t.fileSearch.openWithSystem}
      </Button>
    </div>
  );
}

function removeIntentCondition(intent: FileSearchIntent, condition: FileSearchCondition): FileSearchIntent {
  const query = queryFromIntent(intent);
  let hardTerms = intent.hardTerms;
  let softTerms = intent.softTerms;

  if (condition.type === 'term') {
    if (condition.strength === 'soft') {
      softTerms = softTerms.filter((term) => term !== condition.value);
    } else {
      hardTerms = hardTerms.filter((term) => term !== condition.value);
    }
  }
  if (condition.type === 'fileType') query.fileType = undefined;
  if (condition.type === 'extension') query.extension = undefined;
  if (condition.type === 'folder') query.folder = undefined;
  if (condition.type === 'dateRange') {
    query.dateFrom = undefined;
    query.dateTo = undefined;
  }

  return buildIntentFromQuery(query, hardTerms, softTerms, intent.source, intent.summary, intent.summary);
}

function conditionDisplayLabel(
  condition: FileSearchCondition,
  labels: {
    typeLabel: string;
    extensionLabel: string;
    dateRangeLabel: string;
    dateRangeValue: string;
    documents: string;
    images: string;
    videos: string;
    audio: string;
    archives: string;
    folders: string;
    other: string;
    allTypes: string;
  },
  format: (template: string, values: Record<string, string | number>) => string,
): string {
  if (condition.type === 'fileType') {
    return `${labels.typeLabel}: ${fileTypeLabel(condition.value as FileSearchFileType, labels)}`;
  }
  if (condition.type === 'extension') return `${labels.extensionLabel}: .${condition.value}`;
  if (condition.type === 'dateRange') {
    const [from = '-', to = '-'] = condition.value.split(':');
    return `${labels.dateRangeLabel}: ${format(labels.dateRangeValue, { from, to })}`;
  }
  return condition.label;
}

function highlightFileName(fileName: string, keywords: string[]) {
  const terms = keywords.map((keyword) => keyword.trim()).filter((keyword) => keyword.length > 0);
  if (terms.length === 0) return fileName;
  const pattern = new RegExp(`(${terms.map(escapeRegExp).join('|')})`, 'gi');
  return fileName.split(pattern).map((part, index) => {
    const matched = terms.some((term) => term.toLowerCase() === part.toLowerCase());
    if (!matched) return part;
    return (
      <mark key={`${part}-${index}`} className="rounded bg-[var(--abu-clay-bg)] px-0.5 text-[var(--abu-clay)]">
        {part}
      </mark>
    );
  });
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function ensureTrailingPathSeparator(path: string): string {
  if (path.endsWith('\\') || path.endsWith('/')) return path;
  return `${path}${path.includes('\\') ? '\\' : '/'}`;
}

function FileTypeIcon({ type }: { type: FileSearchFileType }) {
  const className = 'mt-0.5 h-4 w-4 shrink-0 text-[var(--abu-text-tertiary)]';
  if (type === 'folder') return <Folder className={className} />;
  if (type === 'document') return <FileText className={className} />;
  if (type === 'image') return <Image className={className} />;
  if (type === 'video') return <Video className={className} />;
  if (type === 'audio') return <Music className={className} />;
  if (type === 'archive') return <Archive className={className} />;
  return <File className={className} />;
}

function fileTypeLabel(type: FileSearchFileType, labels: {
  allTypes: string;
  documents: string;
  images: string;
  videos: string;
  audio: string;
  archives: string;
  folders: string;
  other: string;
}): string {
  if (type === 'document') return labels.documents;
  if (type === 'image') return labels.images;
  if (type === 'video') return labels.videos;
  if (type === 'audio') return labels.audio;
  if (type === 'archive') return labels.archives;
  if (type === 'folder') return labels.folders;
  if (type === 'other') return labels.other;
  return labels.allTypes;
}

function formatSize(bytes: number): string {
  if (bytes <= 0) return '-';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value >= 10 || unit === 0 ? value.toFixed(0) : value.toFixed(1)} ${units[unit]}`;
}

function formatDate(timestamp: number): string {
  if (!timestamp) return '-';
  return new Date(timestamp * 1000).toLocaleString();
}

function statusLabel(status: FileSearchIndexStatus, labels: {
  indexIdle: string;
  indexDone: string;
  indexError: string;
  indexing: string;
}): string {
  if (status.lastError) return status.lastError;
  if (status.running) return status.message || labels.indexing;
  if (status.phase === 'done') return labels.indexDone;
  if (status.phase === 'error') return labels.indexError;
  return status.message || labels.indexIdle;
}
