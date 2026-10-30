import { Gauge, Rocket, Target } from 'lucide-react';
import { useT } from '../i18n';
import { cn } from '../lib/format';
import type { VideoMeta } from '../types';

interface FrameStepSliderProps {
  value: number;
  onChange: (v: number) => void;
  meta: VideoMeta;
  disabled?: boolean;
}

const PRESETS = [1, 3, 5, 10, 30];
const MAX = 30;

function speedLabel(
  n: number,
  t: (text: string, vars?: Record<string, string | number>) => string,
): { text: string; className: string } {
  if (n <= 2) return { text: t('Thorough'), className: 'text-slate-300' };
  if (n <= 7) return { text: t('Balanced'), className: 'text-accent-soft' };
  if (n <= 15) return { text: t('Fast'), className: 'text-signal-soft' };
  return { text: t('Rapid'), className: 'text-signal' };
}

export function FrameStepSlider({ value, onChange, meta, disabled }: FrameStepSliderProps) {
  const t = useT();
  const pct = ((value - 1) / (MAX - 1)) * 100;
  const speed = speedLabel(value, t);
  const stats = [
    { label: t('Frames to scan'), value: Math.ceil(meta.frame_count / value).toLocaleString() },
    { label: t('Sample rate'), value: `${(meta.fps / value).toFixed(1)} fps` },
  ];

  return (
    <div className="panel p-4">
      <div className="flex items-center justify-between">
        <span className="label flex items-center gap-2">
          <Gauge size={14} strokeWidth={1.75} />
          {t('Processing density')}
        </span>
        <span className="num text-sm text-slate-200">
          {t('Every {n} frames', { n: value })}
        </span>
      </div>

      <div className={cn('mt-4 space-y-4', disabled && 'pointer-events-none opacity-50')}>
        <div className="grid grid-cols-5 gap-1 rounded-xl bg-ink-850 p-1">
          {PRESETS.map((p) => (
            <button
              key={p}
              onClick={() => onChange(p)}
              className={cn(
                'num rounded-lg border py-1.5 text-xs transition',
                p === value
                  ? 'border-accent/40 bg-accent/20 text-white'
                  : 'border-transparent text-slate-400 hover:bg-white/[0.04] hover:text-slate-200',
              )}
            >
              {p}
            </button>
          ))}
        </div>

        <div dir="ltr">
          <input
            type="range"
            className="range"
            min={1}
            max={MAX}
            step={1}
            value={value}
            onChange={(e) => onChange(Number(e.target.value))}
            aria-label={t('Process one frame every N frames')}
            style={{
              background: `linear-gradient(90deg, #7c5cff 0%, #22d3ee ${pct}%, #222636 ${pct}%)`,
            }}
          />
          <div className="mt-2 flex justify-between text-[11px] text-slate-500">
            <span className="flex items-center gap-1">
              <Target size={12} strokeWidth={1.75} /> {t('Accurate')}
            </span>
            <span className="flex items-center gap-1">
              {t('Fast')} <Rocket size={12} strokeWidth={1.75} />
            </span>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-2">
          {stats.map((s) => (
            <div key={s.label} className="rounded-xl border border-white/[0.06] bg-ink-850 p-2.5">
              <div className="label text-[10px]">{s.label}</div>
              <div className="num mt-1 text-sm">{s.value}</div>
            </div>
          ))}
          <div className="rounded-xl border border-white/[0.06] bg-ink-850 p-2.5">
            <div className="label text-[10px]">{t('Est. speed')}</div>
            <div className={cn('mt-1 text-sm font-medium', speed.className)}>{speed.text}</div>
          </div>
        </div>

        <p className="text-xs leading-relaxed text-slate-500">
          {t('Recoloring still renders every frame — this only sets how often the model re-checks the object.')}
        </p>
      </div>
    </div>
  );
}
