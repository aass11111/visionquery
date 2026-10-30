import React, { useState, useRef, useEffect } from 'react';
import { FolderOpen, HardDrive, AlertTriangle, Trash2, Loader2 } from 'lucide-react';
import { Library, LibraryItem, VideoMeta } from '../types';
import { cn, formatTime } from '../lib/format';

interface LibraryGridProps {
  library: Library | null;
  error: string | null;
  onOpen: (meta: VideoMeta) => void;
  onDelete: (videoId: string) => void;
  deletingId: string | null;
}

function formatBytes(bytes: number): string {
  const mb = bytes / (1024 * 1024);
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
  return `${mb.toFixed(1)} MB`;
}

export function LibraryGrid({ library, error, onOpen, onDelete, deletingId }: LibraryGridProps) {
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const handleDeleteClick = (e: React.MouseEvent, videoId: string) => {
    e.stopPropagation();
    if (confirmId === videoId) {
      if (timerRef.current) clearTimeout(timerRef.current);
      setConfirmId(null);
      onDelete(videoId);
    } else {
      setConfirmId(videoId);
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => setConfirmId(null), 3000);
    }
  };

  return (
    <div className="w-full max-w-5xl animate-fade-up">
      <div className="mb-3 flex items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <FolderOpen size={16} className="text-slate-400" />
          <span className="label">Your library</span>
          {library && (
            <span className="num text-xs text-slate-500">
              {library.videos.length} videos · {formatBytes(library.total_bytes)}
            </span>
          )}
        </div>
        {library?.path && (
          <div className="chip flex max-w-[320px] items-center gap-1.5" title={library.path} dir="ltr">
            <HardDrive size={12} className="shrink-0 text-slate-400" />
            <span className="truncate">{library.path}</span>
          </div>
        )}
      </div>

      {!library && !error && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="overflow-hidden rounded-xl border border-white/[0.06] bg-ink-850">
              <div className="aspect-video skeleton" />
              <div className="space-y-1.5 p-2.5">
                <div className="h-4 w-3/4 rounded skeleton" />
                <div className="h-3 w-1/2 rounded skeleton" />
              </div>
            </div>
          ))}
        </div>
      )}

      {error && (
        <div className="flex items-center gap-2 text-xs text-rose-400">
          <AlertTriangle size={16} className="shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {library && !error && library.videos.length === 0 && (
        <div className="py-12 text-center text-sm text-slate-500">
          No videos yet — upload one above. They are kept on this PC, outside the project folder.
        </div>
      )}

      {library && !error && library.videos.length > 0 && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4">
          {library.videos.map((item: LibraryItem) => {
            const isConfirming = confirmId === item.meta.video_id;
            const isDeleting = deletingId === item.meta.video_id;
            const date = new Date(item.created * 1000);
            const dateStr = `${date.toLocaleDateString()} ${date.toTimeString().slice(0, 5)}`;

            return (
              <div
                key={item.meta.video_id}
                role="button"
                tabIndex={0}
                onClick={() => onOpen(item.meta)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onOpen(item.meta);
                  }
                }}
                className="group relative overflow-hidden rounded-xl border border-white/[0.06] bg-ink-850 text-left transition hover:border-white/[0.14] focus-visible:ring-2 focus-visible:ring-accent/60 outline-none"
              >
                <div className="relative aspect-video bg-black">
                  <img loading="lazy" src={item.thumbnail_url} alt="" className="h-full w-full object-cover" />
                  <span className="chip num absolute bottom-2 left-2 bg-black/50 backdrop-blur text-[11px]">
                    {formatTime(item.meta.duration)}
                  </span>
                  {item.index_status === 'ready' && (
                    <span className="chip absolute top-2 left-2 bg-black/50 backdrop-blur text-[10px] text-emerald-400">
                      ⚡ indexed
                    </span>
                  )}
                  <button
                    type="button"
                    disabled={item.busy || isDeleting}
                    title={item.busy ? 'A job is running on this video' : undefined}
                    aria-label="Delete video"
                    onClick={(e) => handleDeleteClick(e, item.meta.video_id)}
                    className={cn(
                      'btn-icon absolute top-2 right-2 h-7 focus:opacity-100',
                      isConfirming
                        ? 'w-auto px-2 bg-rose-500 text-white text-xs opacity-100 hover:bg-rose-600'
                        : 'w-7 bg-black/50 opacity-0 group-hover:opacity-100',
                      (item.busy || isDeleting) && 'cursor-not-allowed opacity-50'
                    )}
                  >
                    {isDeleting ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : isConfirming ? (
                      'Delete?'
                    ) : (
                      <Trash2 size={14} />
                    )}
                  </button>
                </div>

                <div className="p-2.5">
                  <div className="truncate text-sm text-slate-100" title={item.meta.filename} dir="auto">
                    {item.meta.filename}
                  </div>
                  <div className="num truncate text-[11px] text-slate-500">
                    {item.meta.width}×{item.meta.height} · {dateStr}
                    {item.outputs > 0 && ` · ${item.outputs} edits`}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
