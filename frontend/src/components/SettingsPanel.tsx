import { useEffect } from 'react';
import { Cpu, Gauge, Rocket, RotateCcw, ShieldCheck, Settings2, X, Zap } from 'lucide-react';
import { cn } from '../lib/format';
import { DEFAULT_SETTINGS, type AppSettings } from '../types';

interface SettingsPanelProps {
  open: boolean;
  onClose: () => void;
  settings: AppSettings;
  onChange: (s: AppSettings) => void;
  device: 'cuda' | 'cpu' | null;
}

const PRECISION = [
  {
    half: false,
    title: 'FP32 · Full',
    badge: 'Recommended',
    icon: ShieldCheck,
    text: 'Full 32-bit precision. The most stable choice, works on every GPU and on CPU.',
  },
  {
    half: true,
    title: 'FP16 · Half',
    badge: 'Faster',
    icon: Zap,
    text: 'Half precision: faster and about half the VRAM for the detector. GPU only.',
  },
];

export function SettingsPanel({ open, onClose, settings, onChange, device }: SettingsPanelProps) {
  const gpu = device === 'cuda';
  const confPct = ((settings.conf - 0.05) / (0.6 - 0.05)) * 100;

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <button aria-label="Close settings" className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby="vq-settings-title"
        className="relative flex h-full w-full max-w-[400px] flex-col border-l border-white/[0.08] bg-ink-900 shadow-panel animate-fade-up"
      >
        <div className="panel-header h-14">
          <h2 id="vq-settings-title" className="flex items-center gap-2 text-sm font-semibold">
            <Settings2 size={16} strokeWidth={1.75} className="text-accent-soft" />
            Settings
          </h2>
          <button className="btn-icon h-8 w-8" onClick={onClose} aria-label="Close" title="Close (Esc)">
            <X size={16} />
          </button>
        </div>

        <div className="flex-1 space-y-7 overflow-y-auto p-5">
          <section className="space-y-3">
            <div>
              <div className="label flex items-center gap-2">
                <Rocket size={13} strokeWidth={1.75} /> Search mode
              </div>
              <p className="mt-1 text-xs text-slate-500">
                Instant uses the CLIP index built after upload and checks only the most promising frames.
              </p>
            </div>
            <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label="Search mode">
              {(
                [
                  ['instant', 'Instant', 'Index ranks frames · ~10× less GPU work'],
                  ['full', 'Full scan', 'Every N frames · finds rare moments'],
                ] as const
              ).map(([mode, title, text]) => (
                <button
                  key={mode}
                  role="radio"
                  aria-checked={settings.searchMode === mode}
                  onClick={() => onChange({ ...settings, searchMode: mode })}
                  className={cn(
                    'rounded-xl border p-3 text-left transition',
                    settings.searchMode === mode
                      ? 'border-accent/50 bg-accent/[0.08] shadow-glow'
                      : 'border-white/[0.06] bg-ink-850 hover:border-white/[0.14]',
                  )}
                >
                  <span className="block text-sm font-medium">{title}</span>
                  <span className="mt-1 block text-[11px] leading-relaxed text-slate-400">{text}</span>
                </button>
              ))}
            </div>
          </section>

          <section className="space-y-3">
            <div>
              <div className="label flex items-center gap-2">
                <Cpu size={13} strokeWidth={1.75} /> Detector precision
              </div>
              <p className="mt-1 text-xs text-slate-500">How YOLO-World does its maths on the GPU. Applies to search and recolor.</p>
            </div>
            <div className="space-y-2" role="radiogroup" aria-label="Detector precision">
              {PRECISION.map((p) => {
                const active = settings.yoloHalf === p.half;
                const locked = p.half && !gpu;
                const Icon = p.icon;
                return (
                  <button
                    key={p.title}
                    role="radio"
                    aria-checked={active}
                    disabled={locked}
                    onClick={() => onChange({ ...settings, yoloHalf: p.half })}
                    className={cn(
                      'flex w-full items-start gap-3 rounded-xl border p-3 text-left transition',
                      active ? 'border-accent/50 bg-accent/[0.08] shadow-glow' : 'border-white/[0.06] bg-ink-850 hover:border-white/[0.14]',
                      locked && 'cursor-not-allowed opacity-40',
                    )}
                  >
                    <span
                      className={cn(
                        'mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full border',
                        active ? 'border-accent bg-accent' : 'border-white/20',
                      )}
                    >
                      {active && <span className="h-1.5 w-1.5 rounded-full bg-white" />}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center gap-2 text-sm font-medium">
                        <Icon size={14} strokeWidth={1.75} className={p.half ? 'text-signal' : 'text-emerald-400'} />
                        {p.title}
                        <span className="chip px-2 py-0 text-[10px]">{p.badge}</span>
                      </span>
                      <span className="mt-1 block text-xs leading-relaxed text-slate-400">
                        {locked ? 'Needs an NVIDIA GPU — this server is running on CPU.' : p.text}
                      </span>
                    </span>
                  </button>
                );
              })}
            </div>
          </section>

          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="label flex items-center gap-2">
                <Gauge size={13} strokeWidth={1.75} /> Detection confidence
              </div>
              <span className="num text-sm text-slate-200">{settings.conf.toFixed(2)}</span>
            </div>
            <input
              type="range"
              className="range"
              min={0.05}
              max={0.6}
              step={0.01}
              value={settings.conf}
              onChange={(e) => onChange({ ...settings, conf: Number(e.target.value) })}
              aria-label="Detection confidence threshold"
              style={{ background: `linear-gradient(90deg, #7c5cff 0%, #22d3ee ${confPct}%, #222636 ${confPct}%)` }}
            />
            <div className="flex justify-between text-[11px] text-slate-500">
              <span>More matches</span>
              <span>Fewer, surer matches</span>
            </div>
            <p className="text-xs text-slate-500">
              The minimum YOLO-World score a box needs to count. Lower finds small or partly hidden objects but adds false
              matches.
            </p>
          </section>
        </div>

        <div className="flex items-center justify-between border-t border-white/[0.06] p-4">
          <span className="text-[11px] text-slate-500">Saved in this browser · used on the next search</span>
          <button className="btn-ghost h-8 px-3 text-xs" onClick={() => onChange(DEFAULT_SETTINGS)}>
            <RotateCcw size={13} strokeWidth={1.75} /> Defaults
          </button>
        </div>
      </aside>
    </div>
  );
}
