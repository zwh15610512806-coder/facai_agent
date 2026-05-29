import { useEffect, useMemo, useRef, useState } from 'react';
import { Check, ChevronDown, Search, Sparkles, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useI18n } from '@/i18n';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import type { SkillMetadata } from '@/types';

interface SkillSelectorProps {
  skills: SkillMetadata[];
  selectedName: string | null;
  onSelect: (skill: { name: string; description: string; trigger?: string } | null) => void;
}

export default function SkillSelector({
  skills,
  selectedName,
  onSelect,
}: SkillSelectorProps) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const wrapperRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  const available = useMemo(
    () => skills.filter((s) => s.userInvocable !== false),
    [skills],
  );

  const selected = selectedName
    ? available.find((s) => s.name === selectedName)
    : undefined;

  const filtered = useMemo(() => {
    const lowerQuery = query.trim().toLowerCase();
    if (!lowerQuery) return available;
    return available.filter((skill) => {
      const tags = (skill.tags ?? []).join(' ').toLowerCase();
      return skill.name.toLowerCase().includes(lowerQuery)
        || skill.description.toLowerCase().includes(lowerQuery)
        || tags.includes(lowerQuery);
    });
  }, [available, query]);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: MouseEvent) => {
      if (!wrapperRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('mousedown', onPointerDown);
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('mousedown', onPointerDown);
      window.removeEventListener('keydown', onKey);
    };
  }, [open]);

  useEffect(() => {
    if (!open) {
      setQuery('');
      return;
    }
    requestAnimationFrame(() => searchRef.current?.focus());
  }, [open]);

  const handlePick = (skill: SkillMetadata) => {
    onSelect({
      name: skill.name,
      description: skill.description,
      trigger: skill.trigger,
    });
    setOpen(false);
  };

  const handleClear = () => {
    onSelect(null);
    setOpen(false);
  };

  return (
    <div className="relative" ref={wrapperRef}>
      <Button
        variant="ghost"
        size="xs"
        onClick={() => setOpen((v) => !v)}
        className={cn(
          'btn-ghost h-7 max-w-[170px] gap-1 px-2 text-[12px] font-medium rounded-md transition-colors',
          selected
            ? 'text-[var(--abu-clay)] hover:bg-[var(--abu-clay-bg)]'
            : 'text-[var(--abu-text-tertiary)] hover:text-[var(--abu-text-primary)] hover:bg-[var(--abu-bg-hover)]',
        )}
      >
        {selected ? (
          <span className="truncate">/{selected.name}</span>
        ) : (
          <>
            <Sparkles className="h-3.5 w-3.5" />
            <span>{t.chat.pickSkill}</span>
          </>
        )}
        <ChevronDown className={cn('h-3 w-3 transition-transform', open && 'rotate-180')} />
      </Button>

      {open && (
        <div className="absolute bottom-full left-0 mb-1.5 z-50 min-w-[260px] max-w-[360px] max-h-[320px] overflow-hidden rounded-lg border border-[var(--abu-border)] bg-[var(--abu-bg-base)] shadow-lg">
          <div className="p-2 border-b border-[var(--abu-border)]">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--abu-text-muted)]" />
              <Input
                ref={searchRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={t.chat.pickSkillSearch}
                className="h-8 pl-8 text-[12px]"
              />
            </div>
          </div>

          <div className="max-h-[260px] overflow-y-auto py-1">
            {filtered.length === 0 ? (
              <div className="px-3 py-2 text-[12px] text-[var(--abu-text-muted)]">
                {t.chat.pickSkillEmpty}
              </div>
            ) : (
              <>
                {selected && (
                  <>
                    <Button
                      variant="ghost"
                      size="xs"
                      onClick={handleClear}
                      className="w-full h-auto justify-start gap-2 px-3 py-2 rounded-none text-[12px] text-[var(--abu-text-tertiary)] hover:text-[var(--abu-text-primary)] hover:bg-[var(--abu-bg-hover)]"
                    >
                      <X className="h-3.5 w-3.5" />
                      <span>{t.chat.pickSkillClear}</span>
                    </Button>
                    <div className="my-1 mx-2 border-t border-[var(--abu-border)]" />
                  </>
                )}
                {filtered.map((skill) => {
                  const isActive = selected?.name === skill.name;
                  return (
                    <Button
                      key={skill.name}
                      variant="ghost"
                      size="xs"
                      onClick={() => handlePick(skill)}
                      className={cn(
                        'w-full h-auto justify-start items-start gap-2 px-3 py-2 rounded-none text-left transition-colors',
                        isActive ? 'bg-[var(--abu-clay-bg)]' : 'hover:bg-[var(--abu-bg-hover)]',
                      )}
                    >
                      <span className="mt-0.5 w-4 shrink-0 text-center font-mono text-[12px] text-[var(--abu-text-tertiary)]">/</span>
                      <span className="flex-1 min-w-0">
                        <span className="flex items-center gap-1.5">
                          <span className={cn(
                            'block truncate text-[13px] font-medium',
                            isActive ? 'text-[var(--abu-clay)]' : 'text-[var(--abu-text-primary)]',
                          )}>
                            {skill.name}
                          </span>
                          {isActive && <Check className="h-3 w-3 text-[var(--abu-clay)] shrink-0" />}
                        </span>
                        <span className="block text-[11px] text-[var(--abu-text-tertiary)] mt-0.5 line-clamp-2 leading-snug">
                          {skill.description}
                        </span>
                      </span>
                    </Button>
                  );
                })}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
