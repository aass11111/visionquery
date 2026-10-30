import { useState } from 'react';
import { ShieldCheck, Droplets, Grid3x3, EyeOff, Loader2 } from 'lucide-react';
import { useT } from '../i18n';
import { RenderResultBox } from './RenderResultBox';
import { cn, formatPercent } from '../lib/format';

interface PrivacyPanelProps {
  onRun: (query: string, effect: 'blur' | 'pixelate') => void;
  running: boolean;
  progress: number | null;
  outputUrl: string | null;
  objectsHidden: number | null;
  onViewResult: () => void;
}

const PRESETS = [
  { label: 'Faces', value: 'face' },
  { label: 'License plates', value: 'license plate' },
  { label: 'People', value: 'person' },
  { label: 'Screens', value: 'tv' },
];

export function PrivacyPanel({
  onRun,
  running,
  progress,
  outputUrl,
  objectsHidden,
  onViewResult,
}: PrivacyPanelProps) {
  const t = useT();
  const [selectedPreset, setSelectedPreset] = useState('face');
  const [customTarget, setCustomTarget] = useState('');
  const [effect, setEffect] = useState<'blur' | 'pixelate'>('blur');

  const target = customTarget.trim() || selectedPreset;

  return (
    <div className="panel">
      <div className="panel-header">
        <ShieldCheck size={14} />
        <span className="label">{t('Privacy')}</span>
      </div>

      <div className="p-4 space-y-4">
        <p className="text-xs text-slate-400">
          {t('Hide every face, plate or person in the whole video — useful before sharing footage.')}
        </p>

        <div className="space-y-2">
          <div className="flex flex-wrap gap-1.5">
            {PRESETS.map((p) => {
              const active = !customTarget.trim() && selectedPreset === p.value;
              return (
                <button
                  key={p.value}
                  type="button"
                  onClick={() => {
                    setSelectedPreset(p.value);
                    setCustomTarget('');
                  }}
                  className={cn('chip', active && 'border-accent/40 bg-accent/20 text-white')}
                >
                  {t(p.label)}
                </button>
              );
            })}
          </div>
          <input
            type="text"
            dir="auto"
            value={customTarget}
            onChange={(e) => setCustomTarget(e.target.value)}
            placeholder={t('or type: وجه، لوحة سيارة…')}
            className="input h-9 text-sm w-full"
          />
        </div>

        <div className="grid grid-cols-2 gap-1 rounded-xl bg-ink-850 p-1">
          <button
            type="button"
            onClick={() => setEffect('blur')}
            className={cn(
              'flex items-center justify-center gap-1.5 rounded-lg py-1.5 text-xs font-medium transition-colors',
              effect === 'blur' ? 'bg-ink-700 text-white' : 'text-slate-400 hover:text-slate-200'
            )}
          >
            <Droplets size={13} />
            {t('Blur')}
          </button>
          <button
            type="button"
            onClick={() => setEffect('pixelate')}
            className={cn(
              'flex items-center justify-center gap-1.5 rounded-lg py-1.5 text-xs font-medium transition-colors',
              effect === 'pixelate' ? 'bg-ink-700 text-white' : 'text-slate-400 hover:text-slate-200'
            )}
          >
            <Grid3x3 size={13} />
            {t('Pixelate')}
          </button>
        </div>

        <div className="space-y-1.5">
          <button
            type="button"
            className="btn-primary w-full"
            disabled={running || !target}
            onClick={() => onRun(target, effect)}
          >
            {running ? (
              <>
                <Loader2 size={16} className="animate-spin" />
                {t('Hiding…')} {formatPercent(progress ?? 0)}
              </>
            ) : (
              <>
                <EyeOff size={16} />
                {t('Hide all in video')}
              </>
            )}
          </button>
          {running && (
            <div className="h-1 w-full overflow-hidden rounded-full bg-ink-700">
              <div
                className="h-full bg-accent-gradient transition-all duration-150"
                style={{ width: `${Math.round(Math.max(0, Math.min(1, progress ?? 0)) * 100)}%` }}
              />
            </div>
          )}
        </div>

        {outputUrl && !running && (
          <RenderResultBox
            title={t('{n} detections hidden', { n: objectsHidden ?? 0 })}
            outputUrl={outputUrl}
            onView={onViewResult}
          />
        )}

        <p className="text-[11px] text-slate-500">
          {t('Runs the detector only (no segmentation) — light on the GPU.')}
        </p>
      </div>
    </div>
  );
}
