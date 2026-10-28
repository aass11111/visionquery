import { useMemo, useState } from 'react';
import { ImageOff, Search } from 'lucide-react';
import { cn, formatPercent, formatTime } from '../lib/format';
import { boxToPercent, sameBox } from '../lib/geometry';
import type { FrameHit, Selection, VideoMeta } from '../types';

interface ResultsGridProps {
  hits: FrameHit[];
  meta: VideoMeta;
  query: string;
  loading: boolean;
  selected: Selection | null;
  onSelect: (sel: Selection) => void;
}

type Sort = 'best' | 'time';
const PAGE = 60;

function scoreText(s: number): string {
  if (s > 0.7) return 'text-signal';
  if (s >= 0.4) return 'text-accent-soft';
  return 'text-slate-400';
}
function scoreBg(s: number): string {
  if (s > 0.7) return 'bg-signal';
  if (s >= 0.4) return 'bg-accent';
  return 'bg-slate-500';
}

export function ResultsGrid({ hits, meta, query, loading, selected, onSelect }: ResultsGridProps) {
  const [sort, setSort] = useState<Sort>('best');
  const [limit, setLimit] = useState(PAGE);

  const sorted = useMemo(
    () =>
      [...hits].sort((a, b) => (sort === 'best' ? b.best_score - a.best_score : a.frame_index - b.frame_index)),
    [hits, sort],
  );

  return (
    <div className="panel">
      <div className="panel-header">
        <div className="flex min-w-0 items-center gap-3">
          <span className="label">Results</span>
          {query && (
            <span className="chip min-w-0">
              <Search size={12} strokeWidth={1.75} />
              <span className="truncate">“{query}”</span>
            </span>
          )}
          {hits.length > 0 && <span className="num text-xs text-slate-500">{hits.length} frames</span>}
        </div>
        <div className="flex rounded-lg bg-ink-850 p-0.5">
          {(
            [
              ['best', 'Best match'],
              ['time', 'Chronological'],
            ] as const
          ).map(([k, label]) => (
            <button
              key={k}
              onClick={() => setSort(k)}
              className={cn(
                'rounded-md px-2.5 py-1 text-xs transition',
                sort === k ? 'bg-white/[0.08] text-white' : 'text-slate-400 hover:text-slate-200',
              )}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="grid grid-cols-2 gap-3 p-4 md:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
          {Array.from({ length: 10 }, (_, i) => (
            <div key={i} className="space-y-2">
              <div className="skeleton aspect-video" />
              <div className="skeleton h-3 w-2/3" />
              <div className="skeleton h-2 w-1/3" />
            </div>
          ))}
        </div>
      ) : hits.length === 0 ? (
        <div className="flex flex-col items-center gap-2 px-6 py-14 text-center">
          <ImageOff size={28} strokeWidth={1.5} className="text-slate-600" />
          <div className="text-sm font-medium text-slate-300">No matches yet</div>
          <div className="max-w-sm text-xs text-slate-500">
            Try a different description or lower the frame step for denser scanning.
          </div>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 p-4 md:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
            {sorted.slice(0, limit).map((hit) => {
              const isSel = selected?.hit.frame_index === hit.frame_index;
              const top = hit.detections[0];
              return (
                <div
                  key={hit.frame_index}
                  role="button"
                  tabIndex={0}
                  onClick={() => onSelect({ hit, detection: top })}
                  onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && onSelect({ hit, detection: top })}
                  className={cn(
                    'group animate-fade-up cursor-pointer overflow-hidden rounded-xl border bg-ink-850 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60',
                    isSel ? 'border-signal/60 shadow-glow-signal' : 'border-white/[0.06] hover:border-white/[0.14]',
                  )}
                >
                  <div className="relative aspect-video overflow-hidden bg-black">
                    <img
                      src={hit.thumbnail_url}
                      loading="lazy"
                      alt={`Frame ${hit.frame_index}`}
                      className="h-full w-full object-cover transition duration-300 group-hover:scale-[1.02]"
                    />
                    {hit.detections.map((d, i) => {
                      const on = isSel && selected && sameBox(selected.detection.box, d.box);
                      return (
                        <span
                          key={i}
                          onClick={(e) => {
                            e.stopPropagation();
                            onSelect({ hit, detection: d });
                          }}
                          className={cn(
                            'absolute rounded-[3px] transition',
                            on
                              ? 'border-2 border-signal shadow-[0_0_10px_rgba(34,211,238,.6)]'
                              : 'border-[1.5px] border-accent-soft/80 hover:border-white',
                          )}
                          style={boxToPercent(d.box, meta.width, meta.height)}
                        />
                      );
                    })}
                    <span className="chip num absolute bottom-1.5 left-1.5 border-white/10 bg-black/50 px-2 py-0.5 text-[11px] backdrop-blur">
                      {formatTime(hit.time)}
                    </span>
                  </div>
                  <div className="space-y-1.5 p-2.5">
                    <div className="flex items-center justify-between">
                      <span className="num text-xs text-slate-500">#{hit.frame_index}</span>
                      <span className={cn('num text-xs font-medium', scoreText(hit.best_score))}>
                        {formatPercent(hit.best_score)}
                      </span>
                    </div>
                    <div className="h-1 overflow-hidden rounded-full bg-ink-700">
                      <div className={cn('h-full rounded-full', scoreBg(hit.best_score))} style={{ width: formatPercent(hit.best_score) }} />
                    </div>
                    <div className="flex justify-between text-[11px] text-slate-500">
                      <span>
                        {hit.detections.length} object{hit.detections.length > 1 ? 's' : ''}
                      </span>
                      {top.clip_score !== null && <span className="num">CLIP {formatPercent(top.clip_score)}</span>}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
          {sorted.length > limit && (
            <div className="flex justify-center pb-4">
              <button className="btn-ghost" onClick={() => setLimit((l) => l + PAGE)}>
                Show more ({sorted.length - limit} left)
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
