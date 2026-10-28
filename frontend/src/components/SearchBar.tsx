import React, { useEffect, useRef } from 'react';
import { Search, Loader2 } from 'lucide-react';
import { cn } from '../lib/format';

export interface SearchBarProps {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  loading: boolean;
  disabled: boolean;
  useClip: boolean;
  onUseClipChange: (v: boolean) => void;
}

const EXAMPLE_CHIPS = [
  'red car',
  'person with a backpack',
  'dog',
  'white truck',
  'bicycle',
] as const;

export function SearchBar({
  value,
  onChange,
  onSubmit,
  loading,
  disabled,
  useClip,
  onUseClipChange,
}: SearchBarProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        inputRef.current?.focus();
      } else if (e.key === 'Escape') {
        inputRef.current?.blur();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (value.trim() && !loading && !disabled) {
      onSubmit();
    }
  };

  return (
    <form onSubmit={handleSubmit} className="panel p-2">
      <div className="flex items-center gap-2">
        <div className="relative min-w-0 flex-1">
          <Search
            size={16}
            strokeWidth={1.75}
            className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500"
          />
          <input
            ref={inputRef}
            type="text"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            disabled={disabled || loading}
            placeholder={'Describe what you\'re looking for — "red car", "person with a backpack"'}
            className="h-11 w-full border-0 bg-transparent pl-10 pr-16 text-base text-slate-100 placeholder:text-slate-500 focus:outline-none focus:ring-0"
          />
          {!value && (
            <kbd className="kbd pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 select-none">
              Ctrl K
            </kbd>
          )}
        </div>

        <button
          type="button"
          role="switch"
          aria-checked={useClip}
          title="Re-score each detection with CLIP for attribute-heavy queries (colour, clothing). Slightly slower."
          onClick={() => onUseClipChange(!useClip)}
          disabled={disabled || loading}
          className="inline-flex shrink-0 items-center gap-2 select-none rounded-xl px-2.5 py-1.5 text-xs font-medium text-slate-300 transition duration-150 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 disabled:pointer-events-none disabled:opacity-40"
        >
          <span
            className={cn(
              'relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors duration-150',
              useClip ? 'bg-accent' : 'bg-ink-700'
            )}
          >
            <span
              className={cn(
                'inline-block h-3.5 w-3.5 rounded-full bg-white shadow-sm transition-transform duration-150',
                useClip ? 'translate-x-[19px]' : 'translate-x-[3px]'
              )}
            />
          </span>
          <span>CLIP re-rank</span>
        </button>

        <button
          type="submit"
          disabled={disabled || loading || !value.trim()}
          className="btn-primary h-11 shrink-0 px-5"
        >
          {loading ? (
            <>
              <Loader2 size={16} strokeWidth={1.75} className="animate-spin" />
              <span>Searching</span>
            </>
          ) : (
            <>
              <Search size={16} strokeWidth={1.75} />
              <span>Search</span>
            </>
          )}
        </button>
      </div>

      {!loading && (
        <div className="flex flex-wrap items-center gap-1.5 px-2 pb-1 pt-2">
          {EXAMPLE_CHIPS.map((chip) => (
            <button
              key={chip}
              type="button"
              disabled={disabled}
              onClick={() => onChange(chip)}
              className="chip transition duration-150 hover:border-accent/40 hover:text-white disabled:pointer-events-none disabled:opacity-40"
            >
              {chip}
            </button>
          ))}
        </div>
      )}
    </form>
  );
}
