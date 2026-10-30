import { Layers, Wand2, Loader2 } from 'lucide-react';
import { Target, VideoMeta } from '../types';
import { cn, formatPercent } from '../lib/format';
import { TargetRow } from './TargetRow';
import { useT } from '../i18n';

interface TargetsPanelProps {
  targets: Target[]; thumbnails: Record<number, string>; meta: VideoMeta;
  onChange: (index: number, patch: Partial<Target>) => void; onRemove: (index: number) => void;
  onClear: () => void; onApply: () => void; applying: boolean; applyProgress: number | null;
}

export function TargetsPanel({
  targets, thumbnails, meta, onChange, onRemove, onClear, onApply, applying, applyProgress,
}: TargetsPanelProps) {
  const t = useT();
  const n = targets.length;

  return (
    <div className={cn('panel flex flex-col')}>
      <div className="panel-header">
        <div className="flex items-center gap-2">
          <Layers size={14} />
          <span className="label">{t('Edit batch')}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="num text-xs text-slate-400">{n}/8</span>
          {n > 0 && (
            <button type="button" className="btn-ghost h-7 px-2 text-xs" onClick={onClear} disabled={applying}>
              {t('Clear')}
            </button>
          )}
        </div>
      </div>

      <div className="p-3 space-y-2">
        {n === 0 ? (
          <p className="text-xs text-slate-500">
            {t('Add objects with “Add to batch” to edit several at once — e.g. the car blue and the bus green.')}
          </p>
        ) : (
          targets.map((target, idx) => (
            <TargetRow
              key={idx}
              target={target}
              thumbnail={thumbnails[target.frame_index] ?? null}
              meta={meta}
              onChange={(patch) => onChange(idx, patch)}
              onRemove={() => onRemove(idx)}
              disabled={applying}
            />
          ))
        )}
      </div>

      {n > 0 && (
        <div className="border-t border-white/[0.06] p-3 space-y-2">
          <button type="button" className="btn-primary w-full" onClick={onApply} disabled={applying}>
            {applying ? (
              <>
                <Loader2 size={16} className="animate-spin" />
                {t('Rendering…')} {formatPercent(applyProgress ?? 0)}
              </>
            ) : (
              <>
                <Wand2 size={16} />
                {n === 1 ? t('Apply 1 edit in one render') : t('Apply {n} edits in one render', { n })}
              </>
            )}
          </button>
          {applying && (
            <div className="h-1 w-full overflow-hidden rounded-full bg-ink-700">
              <div
                className="h-full bg-accent-gradient transition-all duration-150"
                style={{ width: formatPercent(applyProgress ?? 0) }}
              />
            </div>
          )}
          <p className="text-[11px] text-slate-500">
            {t('One pass over the video: every object is segmented in the same frames.')}
          </p>
        </div>
      )}
    </div>
  );
}
