import { useState, useCallback } from 'react';
import { BookOpen, Plus, Trash2, RefreshCw, FolderOpen, Globe, Database, Search, X } from 'lucide-react';
import { useI18n } from '@/i18n';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';

interface KnowledgeSource {
  id: string;
  type: 'feishu-wiki' | 'feishu-doc' | 'local-dir' | 'database';
  label: string;
  detail: string;
  entryCount: number;
  lastIndexed: string | null;
  status: 'ok' | 'error' | 'indexing';
}

// Local state — not persisted (demo data, real impl uses knowledgeStore)
const DEFAULT_SOURCES: KnowledgeSource[] = [];

export default function KnowledgeSection() {
  const { t } = useI18n();
  const [sources, setSources] = useState<KnowledgeSource[]>(DEFAULT_SOURCES);
  const [showAdd, setShowAdd] = useState(false);
  const [addType, setAddType] = useState<'local-dir' | 'feishu-wiki' | 'feishu-doc'>('local-dir');
  const [inputValue, setInputValue] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [indexingId, setIndexingId] = useState<string | null>(null);

  const totalEntries = sources.reduce((sum, s) => sum + s.entryCount, 0);

  const handleAdd = useCallback(() => {
    if (!inputValue.trim()) return;

    const id = Date.now().toString(36);
    const labels: Record<string, string> = {
      'local-dir': t.knowledge.localFiles,
      'feishu-wiki': t.knowledge.feishuWiki,
      'feishu-doc': t.knowledge.feishuDocs,
    };

    const newSource: KnowledgeSource = {
      id,
      type: addType,
      label: labels[addType],
      detail: inputValue.trim(),
      entryCount: 0,
      lastIndexed: null,
      status: 'ok',
    };

    setSources(prev => [...prev, newSource]);
    setInputValue('');
    setShowAdd(false);
  }, [inputValue, addType, t]);

  const handleRemove = useCallback((id: string) => {
    setSources(prev => prev.filter(s => s.id !== id));
  }, []);

  const handleIndex = useCallback(async (id: string) => {
    setIndexingId(id);
    setSources(prev => prev.map(s => s.id === id ? { ...s, status: 'indexing' as const } : s));

    // Simulate indexing — real impl calls knowledgeStore / lark-cli
    await new Promise(resolve => setTimeout(resolve, 2000));

    setSources(prev => prev.map(s =>
      s.id === id
        ? { ...s, status: 'ok' as const, entryCount: Math.floor(Math.random() * 50) + 5, lastIndexed: new Date().toISOString() }
        : s
    ));
    setIndexingId(null);
  }, []);

  const handleClearAll = useCallback(() => {
    if (window.confirm(t.knowledge.clearAllConfirm)) {
      setSources([]);
    }
  }, [t]);

  const getTypeIcon = (type: KnowledgeSource['type']) => {
    switch (type) {
      case 'local-dir': return <FolderOpen className="h-4 w-4" />;
      case 'feishu-wiki': return <Globe className="h-4 w-4" />;
      case 'feishu-doc': return <BookOpen className="h-4 w-4" />;
      case 'database': return <Database className="h-4 w-4" />;
    }
  };

  const filteredSources = searchQuery
    ? sources.filter(s =>
        s.label.toLowerCase().includes(searchQuery.toLowerCase()) ||
        s.detail.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : sources;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-[var(--abu-text-primary)]">{t.knowledge.title}</h3>
          <p className="text-sm text-[var(--abu-text-tertiary)] mt-1">{t.knowledge.description}</p>
        </div>
        <span className="text-sm text-[var(--abu-text-secondary)] bg-[var(--abu-bg-active)] px-3 py-1 rounded-full">
          {t.knowledge.entryCount.replace('{count}', String(totalEntries))}
        </span>
      </div>

      {/* Search & Actions */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[var(--abu-text-muted)]" />
          <Input
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            placeholder={t.knowledge.searchPlaceholder}
            className="pl-9 pr-8"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 rounded hover:bg-[var(--abu-bg-active)]"
            >
              <X className="h-3.5 w-3.5 text-[var(--abu-text-muted)]" />
            </button>
          )}
        </div>
        <button
          onClick={() => setShowAdd(!showAdd)}
          className={cn(
            'flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors',
            showAdd
              ? 'bg-[var(--abu-bg-active)] text-[var(--abu-text-primary)]'
              : 'bg-[var(--abu-clay)] text-white hover:bg-[var(--abu-clay-hover)]'
          )}
        >
          <Plus className="h-4 w-4" />
          {t.knowledge.addSource}
        </button>
        {sources.length > 0 && (
          <button
            onClick={handleClearAll}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium text-red-500 hover:bg-red-50 transition-colors"
          >
            <Trash2 className="h-4 w-4" />
            {t.knowledge.clearAll}
          </button>
        )}
      </div>

      {/* Add source panel */}
      {showAdd && (
        <div className="rounded-xl border border-[var(--abu-border)] bg-[var(--abu-bg-card)] p-4 space-y-3">
          <div className="flex gap-2">
            {(['local-dir', 'feishu-wiki', 'feishu-doc'] as const).map(type => (
              <button
                key={type}
                onClick={() => setAddType(type)}
                className={cn(
                  'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
                  addType === type
                    ? 'bg-[var(--abu-clay)] text-white'
                    : 'bg-[var(--abu-bg-active)] text-[var(--abu-text-secondary)] hover:bg-[var(--abu-bg-hover)]'
                )}
              >
                {getTypeIcon(type)}
                {type === 'local-dir' && t.knowledge.localFiles}
                {type === 'feishu-wiki' && t.knowledge.feishuWiki}
                {type === 'feishu-doc' && t.knowledge.feishuDocs}
              </button>
            ))}
          </div>
          <div className="flex gap-2">
            <Input
              value={inputValue}
              onChange={e => setInputValue(e.target.value)}
              placeholder={
                addType === 'local-dir' ? t.knowledge.dirPathPlaceholder :
                addType === 'feishu-wiki' ? t.knowledge.spaceIdPlaceholder :
                t.knowledge.docTokenPlaceholder
              }
              className="flex-1"
              onKeyDown={e => e.key === 'Enter' && handleAdd()}
            />
            <button
              onClick={handleAdd}
              disabled={!inputValue.trim()}
              className="px-4 py-2 rounded-lg bg-[var(--abu-clay)] text-white text-sm font-medium hover:bg-[var(--abu-clay-hover)] disabled:opacity-50 transition-colors"
            >
              {t.knowledge.addSource}
            </button>
          </div>
        </div>
      )}

      {/* Source list */}
      {filteredSources.length === 0 ? (
        <div className="text-center py-12 text-[var(--abu-text-muted)]">
          <BookOpen className="h-10 w-10 mx-auto mb-3 opacity-40" />
          <p className="text-sm">{t.knowledge.noSources}</p>
        </div>
      ) : (
        <div className="space-y-2">
          {filteredSources.map(source => (
            <div
              key={source.id}
              className="flex items-center gap-3 px-4 py-3 rounded-xl border border-[var(--abu-border)] bg-[var(--abu-bg-card)]"
            >
              <div className={cn(
                'w-8 h-8 rounded-lg flex items-center justify-center shrink-0',
                source.type === 'local-dir' ? 'bg-amber-100 text-amber-700' :
                source.type === 'feishu-wiki' ? 'bg-blue-100 text-blue-700' :
                'bg-green-100 text-green-700'
              )}>
                {getTypeIcon(source.type)}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-[var(--abu-text-primary)]">{source.label}</span>
                  <span className={cn(
                    'w-1.5 h-1.5 rounded-full',
                    source.status === 'ok' ? 'bg-green-500' :
                    source.status === 'indexing' ? 'bg-amber-400 animate-pulse' :
                    'bg-red-500'
                  )} />
                </div>
                <p className="text-xs text-[var(--abu-text-tertiary)] truncate">{source.detail}</p>
                <div className="flex items-center gap-3 mt-1">
                  <span className="text-xs text-[var(--abu-text-muted)]">
                    {source.entryCount > 0
                      ? t.knowledge.entryCount.replace('{count}', String(source.entryCount))
                      : t.knowledge.indexNow}
                  </span>
                  {source.lastIndexed && (
                    <span className="text-xs text-[var(--abu-text-muted)]">
                      {t.knowledge.lastIndexed}: {new Date(source.lastIndexed).toLocaleDateString('zh-CN')}
                    </span>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => handleIndex(source.id)}
                  disabled={indexingId === source.id}
                  className="p-1.5 rounded-lg hover:bg-[var(--abu-bg-active)] text-[var(--abu-text-secondary)] disabled:opacity-50 transition-colors"
                  title={t.knowledge.reindex}
                >
                  <RefreshCw className={cn('h-4 w-4', indexingId === source.id && 'animate-spin')} />
                </button>
                <button
                  onClick={() => handleRemove(source.id)}
                  className="p-1.5 rounded-lg hover:bg-red-50 text-[var(--abu-text-muted)] hover:text-red-500 transition-colors"
                  title={t.knowledge.removeSource}
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
