import { Film, Radio, RotateCcw, ScanSearch, Settings2, ShieldCheck, Zap } from 'lucide-react';
import { useT } from '../i18n';
import { cn, formatTime } from '../lib/format';
import type { Health, IndexStatus, VideoMeta } from '../types';
import { LanguageToggle } from './LanguageToggle';

interface HeaderProps {
  health: Health | null;
  video: VideoMeta | null;
  indexStatus: IndexStatus | null;
  onReset: () => void;
  onOpenSettings: () => void;
  onOpenLive: () => void;
}

export function Header({ health, video, indexStatus, onReset, onOpenSettings, onOpenLive }: HeaderProps) {
  const t = useT();
  const models = health?.loaded_models.length ? t('Loaded: {models}', { models: health.loaded_models.join(', ') }) : t('No models loaded');
  const usedPct =
    health?.vram_cap_gb && health.vram_used_gb !== null ? Math.min(1, health.vram_used_gb / health.vram_total_gb!) : 0;
  const capPct = health?.vram_cap_gb && health.vram_total_gb ? health.vram_cap_gb / health.vram_total_gb : 0;

  return (
    <header className="sticky top-0 z-40 border-b border-white/[0.06] bg-ink-950/70 backdrop-blur-xl">
      <div className="mx-auto flex h-14 max-w-[1600px] items-center gap-4 px-6">
        <div className="flex items-center gap-3">
          <div className="grid h-8 w-8 place-items-center rounded-lg bg-accent-gradient shadow-glow">
            <ScanSearch size={18} strokeWidth={2} className="text-white" />
          </div>
          <div className="leading-tight">
            <div className="font-semibold tracking-tight">VisionQuery</div>
            <div className="hidden text-[11px] text-slate-500 md:block">{t('Language-driven video search & recoloring')}</div>
          </div>
        </div>

        <div className="ms-auto flex items-center gap-3">
          {video && (
            <span className="chip hidden lg:inline-flex" title={video.filename}>
              <Film size={14} strokeWidth={1.75} className="text-slate-400" />
              <span className="max-w-[200px] truncate">{video.filename}</span>
              <span className="num text-slate-500">
                {video.width}×{video.height} · {formatTime(video.duration)}
              </span>
              {indexStatus && indexStatus.status !== 'ready' && (
                <span className="num text-amber-300" title={t('Building the CLIP index for instant search')}>
                  {t('indexing…')}
                </span>
              )}
              {indexStatus?.status === 'ready' && (
                <span className="text-emerald-400" title={t('{n} frames indexed', { n: indexStatus.frames_indexed })}>
                  {t('⚡ instant')}
                </span>
              )}
            </span>
          )}

          {!health ? (
            <span className="skeleton h-7 w-40 rounded-full" />
          ) : health.device === 'cuda' ? (
            <span
              className="chip"
              title={`${models}\n${t('GPU guard: this app never uses more than {n} GB', { n: health.vram_cap_gb ?? 0 })}${health.busy ? `\n${t('GPU busy with a job')}` : ''}`}
            >
              <span
                className={cn(
                  'h-1.5 w-1.5 rounded-full',
                  health.busy ? 'animate-pulse bg-amber-400' : 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,.8)]',
                )}
              />
              <Zap size={13} strokeWidth={1.75} className="text-emerald-400" />
              <span className="hidden max-w-[150px] truncate sm:inline">{health.gpu_name}</span>
              {health.vram_total_gb !== null && (
                <span className="hidden items-center gap-1.5 md:inline-flex">
                  {/* VRAM meter: used vs the app's cap (the tick) */}
                  <span className="relative h-1.5 w-14 overflow-hidden rounded-full bg-ink-700">
                    <span className="absolute inset-y-0 start-0 rounded-full bg-emerald-400/80" style={{ width: `${usedPct * 100}%` }} />
                    <span className="absolute inset-y-0 w-px bg-white/70" style={{ left: `${capPct * 100}%` }} />
                  </span>
                  <span className="num whitespace-nowrap text-slate-500">
                    {(health.vram_used_gb ?? 0).toFixed(1)}/{health.vram_cap_gb?.toFixed(1)} GB
                  </span>
                  <ShieldCheck size={12} className="text-slate-500" />
                </span>
              )}
            </span>
          ) : (
            <span className="chip" title={`${t('No CUDA GPU detected — processing will be slow.')} ${models}`}>
              <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
              <span className="text-amber-300">{t('CPU mode')}</span>
            </span>
          )}

          <button className="btn-ghost h-8 whitespace-nowrap px-3 text-xs" onClick={onOpenLive} title={t('Live webcam detection')}>
            <Radio size={14} strokeWidth={1.75} className="text-rose-400" />
            <span className="hidden sm:inline">{t('Live')}</span>
          </button>

          <LanguageToggle />

          <button className="btn-icon h-8 w-8" onClick={onOpenSettings} aria-label={t('Settings')} title={t('Settings')}>
            <Settings2 size={16} strokeWidth={1.75} />
          </button>

          {video && (
            <button className="btn-ghost h-8 whitespace-nowrap px-3 text-xs" onClick={onReset}>
              <RotateCcw size={14} strokeWidth={1.75} />
              <span className="hidden sm:inline">{t('New video')}</span>
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
