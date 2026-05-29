import { BookOpen, ExternalLink, Sparkles } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { useI18n } from '@/i18n';
import { useChatStore } from '@/stores/chatStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { openImaKnowledgeBase } from '@/utils/imaKnowledge';

export default function KnowledgeSection() {
  const { t } = useI18n();
  const setPendingInput = useChatStore((s) => s.setPendingInput);
  const closeKnowledge = useSettingsStore((s) => s.closeKnowledge);

  const handleUseImaSkill = () => {
    setPendingInput(t.knowledge.imaSkillPrompt);
    closeKnowledge();
  };

  const handleOpenIma = () => {
    void openImaKnowledgeBase().catch((err) => {
      console.error('[KnowledgeSection] Failed to open IMA knowledge base:', err);
    });
  };

  return (
    <div className="flex h-full min-h-0 flex-col bg-[var(--abu-bg-muted)] px-6 py-6">
      <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col justify-center">
        <div className="space-y-5">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-[var(--abu-clay-bg)] text-[var(--abu-clay)]">
              <BookOpen className="h-5 w-5" strokeWidth={1.8} />
            </div>
            <div className="min-w-0">
              <h3 className="text-lg font-semibold text-[var(--abu-text-primary)]">{t.knowledge.title}</h3>
              <p className="mt-1 text-sm text-[var(--abu-text-tertiary)]">{t.knowledge.imaDescription}</p>
            </div>
          </div>

          <div className="rounded-lg border border-[var(--abu-border)] bg-[var(--abu-bg-base)] p-4">
            <p className="text-sm leading-6 text-[var(--abu-text-secondary)]">{t.knowledge.imaExternalHint}</p>
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <Button
                type="button"
                variant="default"
                size="sm"
                onClick={handleUseImaSkill}
                className="bg-[var(--abu-clay)] text-white hover:bg-[var(--abu-clay-hover)]"
              >
                <Sparkles className="h-4 w-4" />
                {t.knowledge.useImaSkill}
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleOpenIma}
                className="border-[var(--abu-border)] bg-[var(--abu-bg-base)] text-[var(--abu-text-secondary)] hover:bg-[var(--abu-bg-hover)]"
              >
                <ExternalLink className="h-4 w-4" />
                {t.knowledge.openIma}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
