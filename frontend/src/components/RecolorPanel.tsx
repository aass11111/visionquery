import {
  CheckCircle2,
  Download,
  Droplets,
  Eye,
  Grid3x3,
  Layers,
  Loader2,
  MousePointerClick,
  Palette,
  Play,
  Wand2,
} from 'lucide-react';

const EFFECTS: { id: Effect; label: string; icon: typeof Palette }[] = [
  { id: 'recolor', label: 'Recolor', icon: Palette },
  { id: 'blur', label: 'Blur', icon: Droplets },
  { id: 'pixelate', label: 'Pixelate', icon: Grid3x3 },
];
import { HexColorInput, HexColorPicker } from 'react-colorful';
import { useT } from '../i18n';
import { cn, formatPercent, formatTime } from '../lib/format';
import type { Effect, Selection, VideoMeta } from '../types';
import { BeforeAfter } from './BeforeAfter';

interface RecolorPanelProps {
  meta: VideoMeta;
  selection: Selection | null;
  effect: Effect;
  onEffectChange: (e: Effect) => void;
  onAddToBatch: () => void;
  batchCount: number;
  color: string;
  onColorChange: (hex: string) => void;
  strength: number;
  onStrengthChange: (v: number) => void;
  previewUrl: string | null;
  previewLoading: boolean;
  onPreview: () => void;
  onApply: () => void;
  applying: boolean;
  applyProgress: number | null;
  outputUrl: string | null;
  onViewResult: () => void;
}

const SWATCHES = ['#ef4444', '#f97316', '#eab308', '#22c55e', '#06b6d4', '#3b82f6', '#8b5cf6', '#ec4899'];

/** CSS background that zooms a full-frame thumbnail onto one box (padded 10%), as a square crop. */
function cropStyle(sel: Selection, meta: VideoMeta): React.CSSProperties {
  const [x1, y1, x2, y2] = sel.detection.box;
  const side = Math.max(x2 - x1, y2 - y1) * 1.2;
  const cx = (x1 + x2) / 2;
  const cy = (y1 + y2) / 2;
  const left = cx - side / 2;
  const top = cy - side / 2;
  const scale = 100 / side; // % of the tile per source pixel
  return {
    backgroundImage: `url(${sel.hit.thumbnail_url})`,
    backgroundSize: `${meta.width * scale}% ${meta.height * scale}%`,
    backgroundPosition: `${(-left * scale * 72) / 100}px ${(-top * scale * 72) / 100}px`,
    backgroundRepeat: 'no-repeat',
  };
}

export function RecolorPanel(p: RecolorPanelProps) {
  const t = useT();
  const { meta, selection: sel } = p;
  const pct = p.strength * 100;

  return (
    <div className="panel flex flex-col">
      <div className="panel-header">
        <span className="label flex items-center gap-2">
          <Palette size={14} strokeWidth={1.75} />
          {t('Edit object')}
        </span>
      </div>

      {!sel ? (
        <div className="flex flex-col items-center gap-2 px-6 py-12 text-center">
          <MousePointerClick size={28} strokeWidth={1.5} className="text-slate-600" />
          <div className="text-sm font-medium text-slate-300">{t('No object selected')}</div>
          <div className="text-xs text-slate-500">{t('Pick a result card or click a box in the player.')}</div>
        </div>
      ) : (
        <div className="space-y-5 p-4">
          <div className="flex items-center gap-3 rounded-xl border border-white/[0.06] bg-ink-850 p-2.5">
            <div dir="ltr" className="h-[72px] w-[72px] shrink-0 rounded-lg bg-black" style={cropStyle(sel, meta)} />
            <div className="min-w-0 space-y-1">
              <div className="truncate font-medium capitalize">{sel.detection.label}</div>
              <div className="num text-xs text-slate-400">
                {t('frame #{n}', { n: sel.hit.frame_index })} · {formatTime(sel.hit.time)}
              </div>
              <span className="chip num py-0.5 text-[11px]">{formatPercent(sel.detection.score)} {t('match')}</span>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-1 rounded-xl bg-ink-850 p-1" role="radiogroup" aria-label={t('Effect')}>
            {EFFECTS.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                role="radio"
                aria-checked={p.effect === id}
                onClick={() => p.onEffectChange(id)}
                className={cn(
                  'flex items-center justify-center gap-1.5 rounded-lg border py-1.5 text-xs transition',
                  p.effect === id
                    ? 'border-accent/40 bg-accent/20 text-white'
                    : 'border-transparent text-slate-400 hover:bg-white/[0.04] hover:text-slate-200',
                )}
              >
                <Icon size={13} strokeWidth={1.75} /> {t(label)}
              </button>
            ))}
          </div>

          {p.effect === 'recolor' && (
          <div className="space-y-2.5">
            <span className="label">{t('Target colour')}</span>
            <div className="vq-picker">
              <HexColorPicker color={p.color} onChange={p.onColorChange} />
            </div>
            <div className="flex items-center gap-2">
              <span className="h-9 w-9 shrink-0 rounded-lg border border-white/10" style={{ background: p.color }} />
              <HexColorInput prefixed color={p.color} onChange={p.onColorChange} className="input num h-9 py-0 uppercase" />
            </div>
            <div className="flex justify-between">
              {SWATCHES.map((c) => (
                <button
                  key={c}
                  aria-label={c}
                  title={c}
                  onClick={() => p.onColorChange(c)}
                  className={cn(
                    'h-6 w-6 rounded-full transition hover:scale-110',
                    p.color.toLowerCase() === c && 'ring-2 ring-white ring-offset-2 ring-offset-ink-900',
                  )}
                  style={{ background: c }}
                />
              ))}
            </div>
          </div>
          )}

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="label">{t('Strength')}</span>
              <span className="num text-xs text-slate-300">{Math.round(pct)}%</span>
            </div>
            <input
              type="range"
              className="range"
              min={0}
              max={1}
              step={0.01}
              value={p.strength}
              onChange={(e) => p.onStrengthChange(Number(e.target.value))}
              aria-label={t('Recolor strength')}
              style={{ background: `linear-gradient(90deg, #7c5cff 0%, #22d3ee ${pct}%, #222636 ${pct}%)` }}
            />
            <p className="text-[11px] text-slate-500">
              {p.effect === 'recolor'
                ? t('Lower keeps more of the original colour; shading, lettering and glass are preserved.')
                : t('How strongly the object is hidden.')}
            </p>
          </div>

          <div className="space-y-2.5">
            <button className="btn-ghost w-full" onClick={p.onPreview} disabled={p.previewLoading || p.applying}>
              {p.previewLoading ? <Loader2 size={16} className="animate-spin" /> : <Eye size={16} strokeWidth={1.75} />}
              {t('Preview on this frame')}
            </button>
            {p.previewLoading && !p.previewUrl && <div className="skeleton aspect-video" />}
            {p.previewUrl && (
              <BeforeAfter
                before={sel.hit.thumbnail_url}
                after={p.previewUrl}
                className={cn(p.previewLoading && 'opacity-60')}
              />
            )}
          </div>

          <div className="space-y-2">
            <div className="grid grid-cols-[1fr_auto] gap-2">
              <button className="btn-primary h-11" onClick={p.onApply} disabled={p.applying}>
                {p.applying ? <Loader2 size={16} className="animate-spin" /> : <Wand2 size={16} strokeWidth={1.75} />}
                {p.applying ? `${t('Rendering…')} ${formatPercent(p.applyProgress ?? 0)}` : t('Apply to entire video')}
              </button>
              <button
                className="btn-ghost h-11 px-3"
                onClick={p.onAddToBatch}
                disabled={p.applying || p.batchCount >= 8}
                title={t('Queue this object and edit several in one render')}
              >
                <Layers size={15} strokeWidth={1.75} />
                <span className="text-xs">{t('Add to batch')}{p.batchCount ? ` (${p.batchCount})` : ''}</span>
              </button>
            </div>
            {p.applying && (
              <div className="h-1 overflow-hidden rounded-full bg-ink-700">
                <div
                  className="h-full rounded-full bg-accent-gradient transition-[width] duration-300"
                  style={{ width: formatPercent(p.applyProgress ?? 0) }}
                />
              </div>
            )}
          </div>

          {p.outputUrl && !p.applying && (
            <div className="animate-fade-up space-y-3 rounded-xl border border-emerald-400/20 bg-emerald-400/[0.06] p-3">
              <div className="flex items-center gap-2 text-sm text-emerald-300">
                <CheckCircle2 size={16} strokeWidth={1.75} />
                {t('Edited video ready')}
              </div>
              <div className="grid grid-cols-2 gap-2">
                <button className="btn-ghost" onClick={p.onViewResult}>
                  <Play size={14} strokeWidth={1.75} /> {t('View')}
                </button>
                <a className="btn-primary" href={p.outputUrl} download>
                  <Download size={14} strokeWidth={1.75} /> {t('Download')}
                </a>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
