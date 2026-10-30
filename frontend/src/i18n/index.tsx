/**
 * Tiny i18n: the English text is the key (gettext style), Arabic comes from ar.json.
 *   const t = useT();  t('Search')  t('Every {n} frames', { n: 5 })
 * Missing translations fall back to English, so nothing ever renders blank.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import ar from './ar.json';

export type Lang = 'en' | 'ar';
type Vars = Record<string, string | number>;
type T = (text: string, vars?: Vars) => string;

const DICTS: Record<Lang, Record<string, string>> = { en: {}, ar: ar as Record<string, string> };
const KEY = 'vq-lang';

function fill(text: string, vars?: Vars): string {
  return vars ? text.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m)) : text;
}

interface I18n {
  lang: Lang;
  dir: 'ltr' | 'rtl';
  setLang: (l: Lang) => void;
  t: T;
}

const Ctx = createContext<I18n>({ lang: 'en', dir: 'ltr', setLang: () => undefined, t: fill });

function initialLang(): Lang {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === 'ar' || saved === 'en') return saved;
  } catch {
    /* storage unavailable */
  }
  return navigator.language?.startsWith('ar') ? 'ar' : 'en';
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang);
  const dir = lang === 'ar' ? 'rtl' : 'ltr';

  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = dir;
    try {
      localStorage.setItem(KEY, lang);
    } catch {
      /* storage unavailable */
    }
  }, [lang, dir]);

  const t = useCallback<T>((text, vars) => fill(DICTS[lang][text] ?? text, vars), [lang]);
  const value = useMemo(() => ({ lang, dir: dir as 'ltr' | 'rtl', setLang: setLangState, t }), [lang, dir, t]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const useI18n = () => useContext(Ctx);
export const useT = () => useContext(Ctx).t;
