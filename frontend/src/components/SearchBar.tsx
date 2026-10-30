import React, { useEffect, useMemo, useRef, useState } from 'react';
import { CornerDownLeft, Languages, Loader2, Search, Sparkles, Wand2 } from 'lucide-react';
import { useT } from '../i18n';
import { cn } from '../lib/format';
import type { CommandParse, Suggestion } from '../types';

export interface SearchBarProps {
  value: string;
  onChange: (v: string) => void;
  /** Runs a search; pass a query to search for it directly (chip or autocomplete pick). */
  onSubmit: (query?: string) => void;
  loading: boolean;
  disabled: boolean;
  useClip: boolean;
  onUseClipChange: (v: boolean) => void;
  suggestions: Suggestion[] | null; // null = not available (backend busy or failed)
  suggestionsLoading: boolean;
  /** The typed text parsed as an edit command ("make the red car blue"), when it is one. */
  command: CommandParse | null;
  onRunCommand: () => void;
  /** English the models searched for, when the query was Arabic. */
  translatedAs: string | null;
  /** Extra controls next to the search button (image search). */
  extra?: React.ReactNode;
}

const EXAMPLES = ['red car', 'person with a backpack', 'dog', 'white truck', 'bicycle'];
const COLOURS = ['red', 'white', 'black', 'blue', 'gray', 'silver', 'green', 'yellow', 'orange'];
const SWATCH: Record<string, string> = {
  red: '#ef4444', orange: '#f97316', yellow: '#eab308', green: '#22c55e', blue: '#3b82f6', purple: '#8b5cf6',
  pink: '#ec4899', brown: '#92400e', white: '#f1f5f9', gray: '#94a3b8', silver: '#cbd5e1', black: '#0f172a',
};
const MAX_OPTIONS = 7;
// Objects where a colour makes a sensible query; mirrors COLOURABLE in backend/app/suggest.py.
const COLOURABLE = new Set([
  'car', 'bus', 'truck', 'van', 'taxi', 'motorcycle', 'bicycle', 'boat', 'backpack', 'umbrella', 'handbag',
  'suitcase', 'chair', 'couch', 'bottle', 'cup', 'helmet', 'kite', 'sports ball',
]);

interface Option {
  label: string;
  hint: string; // right-hand meta text
  inVideo: boolean;
}

function colourOf(label: string): string | null {
  const first = label.split(' ')[0];
  return SWATCH[first] ? first : null;
}

/** Candidates: what is in the video first, then colour + object combos for those objects, then examples. */
function buildOptions(
  text: string,
  items: Suggestion[] | null,
  t: (text: string, vars?: Record<string, string | number>) => string,
): Option[] {
  const q = text.trim().toLowerCase();
  if (!q) return [];
  const seen = new Set<string>();
  const all: Option[] = [];
  const push = (label: string, hint: string, inVideo: boolean) => {
    if (seen.has(label) || label === q) return;
    seen.add(label);
    all.push({ label, hint, inVideo });
  };
  for (const s of items ?? []) push(s.label, t('in video · {count}', { count: s.count }), true);
  for (const s of items ?? []) {
    if (s.kind === 'object' && COLOURABLE.has(s.label)) for (const c of COLOURS) push(`${c} ${s.label}`, t('suggested'), false);
  }
  for (const e of EXAMPLES) push(e, t('example'), false);

  const words = q.split(/\s+/);
  const score = (o: Option) => {
    const l = o.label;
    if (!words.every((w) => l.includes(w))) return -1;
    let s = o.inVideo ? 100 : 0;
    if (l.startsWith(q)) s += 50;
    else if (l.split(' ').some((w) => w.startsWith(words[words.length - 1]))) s += 20;
    return s;
  };
  return all
    .map((o) => ({ o, s: score(o) }))
    .filter((x) => x.s >= 0)
    .sort((a, b) => b.s - a.s)
    .slice(0, MAX_OPTIONS)
    .map((x) => x.o);
}

function Highlight({ text, query }: { text: string; query: string }) {
  const q = query.trim().toLowerCase();
  const i = q ? text.indexOf(q) : -1;
  if (i < 0) return <>{text}</>;
  return (
    <>
      {text.slice(0, i)}
      <span className="text-white">{text.slice(i, i + q.length)}</span>
      {text.slice(i + q.length)}
    </>
  );
}

export function SearchBar({
  value,
  onChange,
  onSubmit,
  loading,
  disabled,
  useClip,
  onUseClipChange,
  suggestions,
  suggestionsLoading,
  command,
  onRunCommand,
  translatedAs,
  extra,
}: SearchBarProps) {
  const isCommand = !!command?.ok;
  const inputRef = useRef<HTMLInputElement>(null);
  const [focused, setFocused] = useState(false);
  const [active, setActive] = useState(-1);
  const [dismissed, setDismissed] = useState(false);

  const t = useT();
  const options = useMemo(() => buildOptions(value, suggestions, t), [value, suggestions, t]);
  const open = focused && !dismissed && !loading && options.length > 0;

  useEffect(() => setActive(-1), [value]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const pick = (label: string) => {
    onChange(label);
    setDismissed(true);
    if (!loading && !disabled) onSubmit(label);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (open && active >= 0) return pick(options[active].label);
    if (isCommand && !loading && !disabled) {
      setDismissed(true);
      onRunCommand();
      return;
    }
    if (value.trim() && !loading && !disabled) {
      setDismissed(true);
      onSubmit();
    }
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape') {
      if (open) setDismissed(true);
      else inputRef.current?.blur();
    } else if (!open) {
      if (e.key === 'ArrowDown' && options.length) setDismissed(false);
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActive((a) => (a + 1) % options.length);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive((a) => (a <= 0 ? options.length - 1 : a - 1));
    } else if (e.key === 'Tab' && active >= 0) {
      e.preventDefault();
      onChange(options[active].label);
    }
  };

  const chips = suggestions && suggestions.length > 0 ? suggestions : null;

  return (
    <form onSubmit={handleSubmit} className="panel relative z-20 p-2">
      <div className="flex items-center gap-2">
        <div className="relative min-w-0 flex-1">
          <Search
            size={16}
            strokeWidth={1.75}
            className="pointer-events-none absolute start-3.5 top-1/2 -translate-y-1/2 text-slate-500"
          />
          <input
            ref={inputRef}
            type="text"
            value={value}
            onChange={(e) => {
              onChange(e.target.value);
              setDismissed(false);
            }}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            onKeyDown={onKeyDown}
            disabled={disabled || loading}
            placeholder={t('Describe what you\'re looking for — "red car", "person with a backpack"')}
            role="combobox"
            aria-expanded={open}
            aria-controls="vq-search-options"
            aria-autocomplete="list"
            aria-activedescendant={active >= 0 ? `vq-opt-${active}` : undefined}
            className="h-11 w-full border-0 bg-transparent ps-10 pe-16 text-base text-slate-100 placeholder:text-slate-500 focus:outline-none focus:ring-0"
          />
          {!value && (
            <kbd className="kbd pointer-events-none absolute end-3 top-1/2 -translate-y-1/2 select-none">Ctrl K</kbd>
          )}

          {open && (
            <ul
              id="vq-search-options"
              role="listbox"
              className="absolute start-0 top-[calc(100%+10px)] z-30 w-full min-w-[min(380px,calc(100vw-4rem))] overflow-hidden rounded-2xl border border-white/[0.08] bg-ink-900 p-1 shadow-panel animate-fade-up"
            >
              {options.map((o, i) => {
                const colour = colourOf(o.label);
                return (
                  <li
                    key={o.label}
                    id={`vq-opt-${i}`}
                    role="option"
                    aria-selected={i === active}
                    onMouseDown={(e) => {
                      e.preventDefault(); // keep focus so the click lands
                      pick(o.label);
                    }}
                    onMouseEnter={() => setActive(i)}
                    className={cn(
                      'flex cursor-pointer items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-slate-300',
                      i === active && 'bg-white/[0.06] text-slate-100',
                    )}
                  >
                    {colour ? (
                      <span className="h-2.5 w-2.5 shrink-0 rounded-full ring-1 ring-white/20" style={{ background: SWATCH[colour] }} />
                    ) : o.inVideo ? (
                      <Sparkles size={13} strokeWidth={1.75} className="shrink-0 text-signal" />
                    ) : (
                      <Search size={13} strokeWidth={1.75} className="shrink-0 text-slate-500" />
                    )}
                    <span className="flex-1 truncate">
                      <Highlight text={o.label} query={value} />
                    </span>
                    <span className={cn('num text-[11px]', o.inVideo ? 'text-signal-soft' : 'text-slate-500')}>{o.hint}</span>
                    {i === active && <CornerDownLeft size={12} className="text-slate-500" />}
                  </li>
                );
              })}
              <li className="flex gap-3 border-t border-white/[0.06] px-3 pb-1 pt-2 text-[10px] text-slate-500">
                <span><kbd className="kbd">↑↓</kbd> {t('move')}</span>
                <span><kbd className="kbd">Enter</kbd> {t('search')}</span>
                <span><kbd className="kbd">Tab</kbd> {t('fill')}</span>
                <span><kbd className="kbd">Esc</kbd> {t('close')}</span>
              </li>
            </ul>
          )}
        </div>

        <button
          type="button"
          role="switch"
          aria-checked={useClip}
          title={t('Re-score each detection with CLIP for attribute-heavy queries (colour, clothing). Slightly slower.')}
          onClick={() => onUseClipChange(!useClip)}
          disabled={disabled || loading}
          className="inline-flex shrink-0 items-center gap-2 select-none rounded-xl px-2.5 py-1.5 text-xs font-medium text-slate-300 transition duration-150 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 disabled:pointer-events-none disabled:opacity-40"
        >
          <span
            className={cn(
              'relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors duration-150',
              useClip ? 'bg-accent' : 'bg-ink-700',
            )}
          >
            <span
              className={cn(
                'inline-block h-3.5 w-3.5 rounded-full bg-white shadow-sm transition-transform duration-150',
                useClip ? 'translate-x-[19px]' : 'translate-x-[3px]',
              )}
            />
          </span>
          <span>{t('CLIP re-rank')}</span>
        </button>

        {extra}

        <button type="submit" disabled={disabled || loading || !value.trim()} className="btn-primary h-11 shrink-0 px-5">
          {loading ? (
            <>
              <Loader2 size={16} strokeWidth={1.75} className="animate-spin" />
              <span>{t('Working')}</span>
            </>
          ) : isCommand ? (
            <>
              <Wand2 size={16} strokeWidth={1.75} />
              <span>{t('Run')}</span>
            </>
          ) : (
            <>
              <Search size={16} strokeWidth={1.75} />
              <span>{t('Search')}</span>
            </>
          )}
        </button>
      </div>

      {isCommand && command && (
        <div className="mx-2 mt-2 flex flex-wrap items-center gap-2 rounded-lg border border-accent/25 bg-accent/[0.07] px-3 py-1.5 text-xs text-slate-300 animate-fade-up">
          <Wand2 size={13} className="text-accent-soft" />
          <span className="font-medium text-white">{t('Command')}</span>
          <span>
            {command.effect === 'recolor' ? t('recolor') : command.effect} “{command.object_en}”
          </span>
          {command.color && (
            <span className="inline-flex items-center gap-1.5">
              →
              <span className="h-2.5 w-2.5 rounded-full ring-1 ring-white/30" style={{ background: command.color }} />
              {command.color_name}
            </span>
          )}
          <span className="text-slate-500">{t('· press Enter to search and edit the whole video')}</span>
        </div>
      )}
      {!isCommand && translatedAs && (
        <div className="mx-2 mt-2 inline-flex items-center gap-1.5 text-[11px] text-slate-400">
          <Languages size={12} className="text-signal" /> {t('searched as')} <span className="num text-slate-200">{translatedAs}</span>
        </div>
      )}
      {!loading && (
        <div className="flex flex-wrap items-center gap-1.5 px-2 pb-1 pt-2">
          {suggestionsLoading ? (
            <>
              <span className="me-1 flex items-center gap-1.5 text-[11px] text-slate-500">
                <Loader2 size={12} className="animate-spin" /> {t('Scanning the video for objects…')}
              </span>
              {[56, 72, 48, 64].map((w) => (
                <span key={w} className="skeleton h-6 rounded-full" style={{ width: w }} />
              ))}
            </>
          ) : (
            <>
              <span className="label me-1 flex items-center gap-1">
                {chips ? <Sparkles size={11} className="text-signal" /> : null}
                {chips ? t('In this video') : t('Try')}
              </span>
              {(chips ?? EXAMPLES.map((e) => ({ label: e, count: 0, frames: 0, kind: 'object' as const }))).map((s) => {
                const colour = s.kind === 'color' ? colourOf(s.label) : null;
                return (
                  <button
                    key={s.label}
                    type="button"
                    disabled={disabled}
                    onClick={() => pick(s.label)}
                    title={chips ? t('Search for “{label}”', { label: s.label }) : undefined}
                    className="chip transition duration-150 hover:border-accent/40 hover:text-white disabled:pointer-events-none disabled:opacity-40"
                  >
                    {colour && (
                      <span className="h-2 w-2 rounded-full ring-1 ring-white/20" style={{ background: SWATCH[colour] }} />
                    )}
                    {s.label}
                    {chips && <span className="num text-[10px] text-slate-500">{s.count}</span>}
                  </button>
                );
              })}
            </>
          )}
        </div>
      )}
    </form>
  );
}
