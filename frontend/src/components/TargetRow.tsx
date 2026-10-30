import React from 'react';
import { Trash2 } from 'lucide-react';
import type { Effect, Target, VideoMeta } from '../types';
import { cn } from '../lib/format';
import { useT } from '../i18n';

export interface TargetRowProps {
  target: Target;
  thumbnail: string | null;
  meta: VideoMeta;
  onChange: (patch: Partial<Target>) => void;
  onRemove: () => void;
  disabled?: boolean;
}

export function TargetRow({
  target,
  thumbnail,
  meta,
  onChange,
  onRemove,
  disabled = false,
}: TargetRowProps) {
  const t = useT();
  const [x1, y1, x2, y2] = target.box;
  const bw = Math.max(0, x2 - x1);
  const bh = Math.max(0, y2 - y1);
  const side = Math.max(bw, bh, 1) * 1.2;
  const k = 44 / side;
  const cx = (x1 + x2) / 2;
  const cy = (y1 + y2) / 2;

  return (
    <div className="rounded-xl border border-white/[0.06] bg-ink-850 p-2 flex items-center gap-2">
      <div
        dir="ltr"
        className={cn('h-[44px] w-[44px] shrink-0 rounded-lg bg-cover bg-no-repeat', !thumbnail && 'bg-black')}
        style={{
          backgroundImage: thumbnail ? `url("${thumbnail}")` : undefined,
          backgroundSize: `${meta.width * k}px ${meta.height * k}px`,
          backgroundPosition: `${-(cx - side / 2) * k}px ${-(cy - side / 2) * k}px`,
        }}
      />

      <div className="min-w-0 flex-1 flex flex-col">
        <span className="text-sm truncate capitalize text-slate-100">{target.query}</span>
        <span className="num text-[11px] text-slate-500">{t('frame #{n}', { n: target.frame_index })}</span>
      </div>

      <select
        className="input h-8 w-[104px] py-0 text-xs"
        value={target.effect}
        disabled={disabled}
        onChange={(e) => onChange({ effect: e.target.value as Effect })}
      >
        <option value="recolor">{t('Recolor')}</option>
        <option value="blur">{t('Blur')}</option>
        <option value="pixelate">{t('Pixelate')}</option>
      </select>

      {target.effect === 'recolor' && (
        <label
          aria-label={t('Colour')}
          title={t('Colour')}
          className={cn(
            'relative h-6 w-6 shrink-0 rounded-full border border-white/20 cursor-pointer overflow-hidden',
            disabled && 'pointer-events-none opacity-50'
          )}
          style={{ backgroundColor: target.color }}
        >
          <input
            type="color"
            className="sr-only"
            aria-label={t('Colour')}
            value={target.color}
            disabled={disabled}
            onChange={(e) => onChange({ color: e.target.value })}
          />
        </label>
      )}

      <button
        type="button"
        className="btn-icon h-7 w-7"
        aria-label={t('Remove')}
        title={t('Remove')}
        onClick={onRemove}
        disabled={disabled}
      >
        <Trash2 size={14} />
      </button>
    </div>
  );
}
