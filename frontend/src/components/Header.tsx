import { Film, RotateCcw, ScanSearch, Settings2, Zap } from 'lucide-react';
import { formatTime } from '../lib/format';
import type { Health, VideoMeta } from '../types';

interface HeaderProps {
  health: Health | null;
  video: VideoMeta | null;
  onReset: () => void;
  onOpenSettings: () => void;
}

export function Header({ health, video, onReset, onOpenSettings }: HeaderProps) {
  const models = health?.loaded_models.length ? `Loaded: ${health.loaded_models.join(', ')}` : 'No models loaded';

  return (
    <header className="sticky top-0 z-40 border-b border-white/[0.06] bg-ink-950/70 backdrop-blur-xl">
      <div className="mx-auto flex h-14 max-w-[1600px] items-center gap-4 px-6">
        <div className="flex items-center gap-3">
          <div className="grid h-8 w-8 place-items-center rounded-lg bg-accent-gradient shadow-glow">
            <ScanSearch size={18} strokeWidth={2} className="text-white" />
          </div>
          <div className="leading-tight">
            <div className="font-semibold tracking-tight">VisionQuery</div>
            <div className="hidden text-[11px] text-slate-500 md:block">Language-driven video search &amp; recoloring</div>
          </div>
        </div>

        <div className="ml-auto flex items-center gap-3">
          {video && (
            <span className="chip hidden sm:inline-flex" title={video.filename}>
              <Film size={14} strokeWidth={1.75} className="text-slate-400" />
              <span className="max-w-[220px] truncate">{video.filename}</span>
              <span className="num text-slate-500">
                {video.width}×{video.height} · {formatTime(video.duration)}
              </span>
            </span>
          )}

          {!health ? (
            <span className="skeleton h-7 w-40 rounded-full" />
          ) : health.device === 'cuda' ? (
            <span className="chip" title={models}>
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,.8)]" />
              <Zap size={13} strokeWidth={1.75} className="text-emerald-400" />
              <span className="max-w-[160px] truncate">{health.gpu_name}</span>
              {health.vram_total_gb !== null && (
                <span className="num hidden whitespace-nowrap text-slate-500 md:inline">
                  {(health.vram_used_gb ?? 0).toFixed(1)} / {health.vram_total_gb.toFixed(1)} GB
                </span>
              )}
            </span>
          ) : (
            <span className="chip" title={`No CUDA GPU detected — processing will be slow. ${models}`}>
              <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
              <span className="text-amber-300">CPU mode</span>
            </span>
          )}

          <button className="btn-icon h-8 w-8" onClick={onOpenSettings} aria-label="Settings" title="Settings">
            <Settings2 size={16} strokeWidth={1.75} />
          </button>

          {video && (
            <button className="btn-ghost h-8 whitespace-nowrap px-3 text-xs" onClick={onReset}>
              <RotateCcw size={14} strokeWidth={1.75} />
              New video
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
