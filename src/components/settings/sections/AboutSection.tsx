import { openUrl } from '@tauri-apps/plugin-opener';
import abuAvatar from '@/assets/facai-logo.png';
import { APP_VERSION } from '@/utils/version';
import { useI18n } from '@/i18n';

export default function AboutSection() {
  const { t } = useI18n();

  const handleOpenLink = async (url: string) => {
    try {
      await openUrl(url);
    } catch (e) {
      console.error('Failed to open link:', e);
    }
  };

  return (
    <div className="space-y-6">
      {/* Logo & name */}
      <div className="flex flex-col items-center text-center space-y-3">
        <img src={abuAvatar} alt="采宝" className="w-20 h-20 rounded-2xl" />
        <div>
          <h4 className="text-2xl font-bold text-[var(--abu-text-primary)]">{t.common.appName}</h4>
          <p className="text-sm text-[var(--abu-text-tertiary)]">{t.common.appSlogan}</p>
        </div>
      </div>

      {/* Version info */}
      <div className="space-y-1">
        <div className="flex justify-between items-center py-3 border-b border-[var(--abu-border)]">
          <span className="text-sm text-[var(--abu-text-tertiary)]">{t.updates.currentVersion}</span>
          <span className="text-sm font-semibold text-[var(--abu-text-primary)]">
            v{APP_VERSION}
          </span>
        </div>
      </div>

      {/* Footer */}
      <div className="text-center space-y-2 pt-4">
        <p className="text-sm text-[var(--abu-text-tertiary)]">
          Made with ❤️ by{' '}
          <button
              onClick={() => handleOpenLink('https://github.com/PM-Shawn/Abu-Cowork')}
              className="text-[var(--abu-clay)] hover:underline font-medium"
            >
              Shawn
            </button>
        </p>
        <p className="text-xs text-[var(--abu-text-muted)]">
          © 2026 {t.common.appName}. All rights reserved.
        </p>
      </div>
    </div>
  );
}
