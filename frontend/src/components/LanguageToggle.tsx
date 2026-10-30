import { Languages } from 'lucide-react';
import { useI18n } from '../i18n';

/** EN ↔ عربي switch for the header. */
export function LanguageToggle() {
  const { lang, setLang, t } = useI18n();
  const next = lang === 'ar' ? 'en' : 'ar';
  return (
    <button
      className="btn-ghost h-8 whitespace-nowrap px-2.5 text-xs"
      onClick={() => setLang(next)}
      title={t('Switch language')}
      aria-label={t('Switch language')}
    >
      <Languages size={14} strokeWidth={1.75} />
      <span className={next === 'ar' ? 'font-arabic text-sm leading-none' : 'num'}>{next === 'ar' ? 'عربي' : 'EN'}</span>
    </button>
  );
}
