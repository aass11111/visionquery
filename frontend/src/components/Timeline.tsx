import { useMemo, useRef, useState } from 'react';
import { cn, formatPercent, formatTime } from '../lib/format';
import { nearestHit } from '../lib/geometry';
import type { FrameHit, VideoMeta } from '../types';

interface TimelineProps {
  meta: VideoMeta;
  hits: FrameHit[];
  frameStep: number;
  currentTime: number;
  selectedFrame: number | null;
  onSeek: (time: number) => void;
}

const NICE = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600];

function scoreColor(s: number): string {
  if (s > 0.7) return '#22d3ee';
  if (s >= 0.4) return '#7c5cff';
  return '#64748b';
}

export function Timeline({ meta, hits, frameStep, currentTime, selectedFrame, onSeek }: TimelineProps) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<{ x: number; time: number } | null>(null);
  const duration = Math.max(meta.duration, 0.001);

  const ticks = useMemo(() => {
    const interval = NICE.find((n) => duration / n <= 12) ?? 600;
    const out: number[] = [];
    for (let t = 0; t <= duration; t += interval) out.push(t);
    return out;
  }, [duration]);

  const barWidth = `max(2px, ${(frameStep / meta.fps / duration) * 100}%)`;

  const timeAt = (clientX: number) => {
    const r = trackRef.current!.getBoundingClientRect();
    const x = Math.min(Math.max(clientX - r.left, 0), r.width);
    return { x, time: (x / r.width) * duration };
  };

  const onPointerDown = (e: React.PointerEvent) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    onSeek(timeAt(e.clientX).time);
  };
  const onPointerMove = (e: React.PointerEvent) => {
    const p = timeAt(e.clientX);
    setHover(p);
    if (e.currentTarget.hasPointerCapture(e.pointerId)) onSeek(p.time);
  };

  const hoverHit = hover ? nearestHit(hits, Math.round(hover.time * meta.fps), frameStep) : null;

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="label">Timeline</span>
        <span className="num text-xs text-slate-400">
          {hits.length} matches · scanned every {frameStep} frames
        </span>
      </div>

      <div className="px-4 py-3">
        <div className="relative h-5">
          {ticks.map((t) => (
            <span
              key={t}
              className="num absolute top-0 -translate-x-1/2 text-[10px] text-slate-500 first:translate-x-0"
              style={{ left: `${(t / duration) * 100}%` }}
            >
              {formatTime(t).replace(/\.\d$/, '')}
            </span>
          ))}
        </div>

        <div
          ref={trackRef}
          className="relative h-14 cursor-crosshair touch-none overflow-hidden rounded-xl border border-white/[0.06] bg-ink-850"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerLeave={() => setHover(null)}
        >
          {ticks.map((t) => (
            <span
              key={t}
              className="absolute top-0 h-full w-px bg-white/[0.04]"
              style={{ left: `${(t / duration) * 100}%` }}
            />
          ))}

          {hits.length === 0 && (
            <div className="absolute inset-0 grid place-items-center text-xs text-slate-500">
              Run a search to map matches onto the timeline
            </div>
          )}

          {hits.map((h) => (
            <span
              key={h.frame_index}
              className="absolute bottom-0 rounded-t-sm"
              style={{
                left: `${(h.time / duration) * 100}%`,
                width: barWidth,
                height: `${25 + 75 * h.best_score}%`,
                background: scoreColor(h.best_score),
                opacity: 0.5 + 0.5 * h.best_score,
              }}
            />
          ))}

          {selectedFrame !== null && (
            <span
              className="absolute top-0 h-full w-[3px] -translate-x-1/2 bg-signal shadow-glow-signal"
              style={{ left: `${(selectedFrame / meta.fps / duration) * 100}%` }}
            />
          )}

          <span
            className="pointer-events-none absolute top-0 h-full w-0.5 -translate-x-1/2 bg-white shadow-[0_0_10px_rgba(255,255,255,.6)]"
            style={{ left: `${(Math.min(currentTime, duration) / duration) * 100}%` }}
          >
            <span className="absolute -top-0.5 left-1/2 h-2 w-2 -translate-x-1/2 rounded-full bg-white" />
          </span>
        </div>

        <div className="relative h-0">
          {hover && (
            <div
              className={cn('panel pointer-events-none absolute top-1.5 z-10 -translate-x-1/2 whitespace-nowrap px-2 py-1 text-xs')}
              style={{ left: hover.x }}
            >
              <span className="num">{formatTime(hover.time)}</span>
              {hoverHit && <span className="ml-2 text-signal-soft">match {formatPercent(hoverHit.best_score)}</span>}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
