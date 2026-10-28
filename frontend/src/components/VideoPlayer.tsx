import { useCallback, useEffect, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight, Maximize, Pause, Play, Volume2, VolumeX } from 'lucide-react';
import { formatTime } from '../lib/format';
import { fitContain, nearestHit, sameBox } from '../lib/geometry';
import type { Detection, FrameHit, Selection, VideoMeta } from '../types';

interface VideoPlayerProps {
  src: string;
  meta: VideoMeta;
  hits: FrameHit[];
  frameStep: number;
  selected: Selection | null;
  onSelect: (sel: Selection) => void;
  seekRequest: { time: number; nonce: number } | null;
  onTimeUpdate: (time: number) => void;
  badge?: string;
  showOverlays?: boolean;
}

const RATES = [0.5, 1, 2];
const ICON = { size: 16, strokeWidth: 1.75 };

interface Drawn {
  hit: FrameHit;
  boxes: { det: Detection; x: number; y: number; w: number; h: number }[];
}

export function VideoPlayer({
  src,
  meta,
  hits,
  frameStep,
  selected,
  onSelect,
  seekRequest,
  onTimeUpdate,
  badge,
  showOverlays = true,
}: VideoPlayerProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const drawnRef = useRef<Drawn | null>(null);
  const hoverRef = useRef<number>(-1);

  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [muted, setMuted] = useState(false);
  const [rate, setRate] = useState(1);
  const [cursor, setCursor] = useState('default');

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    const stage = stageRef.current;
    const v = videoRef.current;
    if (!canvas || !stage || !v) return;
    const dpr = window.devicePixelRatio || 1;
    const W = stage.clientWidth;
    const H = stage.clientHeight;
    if (canvas.width !== Math.round(W * dpr) || canvas.height !== Math.round(H * dpr)) {
      canvas.width = Math.round(W * dpr);
      canvas.height = Math.round(H * dpr);
    }
    const ctx = canvas.getContext('2d')!;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);
    drawnRef.current = null;
    if (!showOverlays || hits.length === 0) return;

    const hit = nearestHit(hits, Math.round(v.currentTime * meta.fps), Math.max(1, frameStep));
    if (!hit) return;
    const r = fitContain(meta.width, meta.height, W, H);
    const boxes = hit.detections.map((det) => {
      const [x1, y1, x2, y2] = det.box;
      return { det, x: r.x + x1 * r.scale, y: r.y + y1 * r.scale, w: (x2 - x1) * r.scale, h: (y2 - y1) * r.scale };
    });
    drawnRef.current = { hit, boxes };

    ctx.font = '500 11px Inter, system-ui, sans-serif';
    boxes.forEach((b, i) => {
      const isSel =
        selected !== null && selected.hit.frame_index === hit.frame_index && sameBox(selected.detection.box, b.det.box);
      const isHover = hoverRef.current === i;
      ctx.save();
      if (isSel) {
        ctx.strokeStyle = '#22d3ee';
        ctx.lineWidth = 2.5;
        ctx.shadowColor = 'rgba(34,211,238,.8)';
        ctx.shadowBlur = 12;
      } else {
        ctx.strokeStyle = isHover ? '#c4b8ff' : '#a593ff';
        ctx.lineWidth = 1.5;
        if (isHover) {
          ctx.fillStyle = 'rgba(124,92,255,.08)';
          ctx.fillRect(b.x, b.y, b.w, b.h);
        }
      }
      ctx.strokeRect(b.x, b.y, b.w, b.h);
      if (isSel) {
        const c = Math.min(14, b.w / 3, b.h / 3);
        ctx.lineWidth = 4;
        ctx.beginPath();
        for (const [px, py, dx, dy] of [
          [b.x, b.y, 1, 1],
          [b.x + b.w, b.y, -1, 1],
          [b.x, b.y + b.h, 1, -1],
          [b.x + b.w, b.y + b.h, -1, -1],
        ]) {
          ctx.moveTo(px + dx * c, py);
          ctx.lineTo(px, py);
          ctx.lineTo(px, py + dy * c);
        }
        ctx.stroke();
      }
      ctx.restore();

      const text = `${b.det.label} ${Math.round(b.det.score * 100)}%`;
      const tw = ctx.measureText(text).width + 12;
      const ty = b.y - 20 < 0 ? b.y + 2 : b.y - 20;
      ctx.fillStyle = isSel ? '#0891b2' : 'rgba(91,61,245,.92)';
      ctx.beginPath();
      ctx.roundRect(b.x, ty, tw, 18, 5);
      ctx.fill();
      ctx.fillStyle = '#fff';
      ctx.fillText(text, b.x + 6, ty + 12.5);
    });
  }, [hits, frameStep, meta, selected, showOverlays]);

  // Redraw loop while playing; single redraws otherwise.
  useEffect(() => {
    if (!playing) {
      draw();
      return;
    }
    let raf = 0;
    const loop = () => {
      draw();
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [playing, draw]);

  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;
    const ro = new ResizeObserver(() => draw());
    ro.observe(stage);
    return () => ro.disconnect();
  }, [draw]);

  useEffect(() => {
    if (!seekRequest || !videoRef.current) return;
    videoRef.current.pause();
    videoRef.current.currentTime = seekRequest.time;
  }, [seekRequest]);

  useEffect(() => {
    if (videoRef.current) videoRef.current.playbackRate = rate;
  }, [rate]);

  const syncTime = () => {
    const t = videoRef.current?.currentTime ?? 0;
    setTime(t);
    onTimeUpdate(t);
    draw();
  };

  const toggle = () => {
    const v = videoRef.current;
    if (!v) return;
    if (v.paused) void v.play();
    else v.pause();
  };

  const step = (dir: number) => {
    const v = videoRef.current;
    if (!v) return;
    v.pause();
    v.currentTime = Math.min(Math.max(0, v.currentTime + dir / meta.fps), meta.duration);
  };

  const boxAt = (e: React.MouseEvent) => {
    const drawn = drawnRef.current;
    if (!drawn) return -1;
    const rect = canvasRef.current!.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    // Smallest box first so nested objects stay clickable.
    let best = -1;
    let bestArea = Infinity;
    drawn.boxes.forEach((b, i) => {
      if (x >= b.x && x <= b.x + b.w && y >= b.y && y <= b.y + b.h && b.w * b.h < bestArea) {
        best = i;
        bestArea = b.w * b.h;
      }
    });
    return best;
  };

  const onMouseMove = (e: React.MouseEvent) => {
    const i = boxAt(e);
    if (i !== hoverRef.current) {
      hoverRef.current = i;
      setCursor(i >= 0 ? 'pointer' : 'default');
      draw();
    }
  };

  const onClick = (e: React.MouseEvent) => {
    const i = boxAt(e);
    const drawn = drawnRef.current;
    if (i >= 0 && drawn) onSelect({ hit: drawn.hit, detection: drawn.boxes[i].det });
    else toggle();
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.target !== panelRef.current) return;
    if (e.key === ' ') {
      e.preventDefault();
      toggle();
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault();
      step(-1);
    } else if (e.key === 'ArrowRight') {
      e.preventDefault();
      step(1);
    }
  };

  const fullscreen = () => {
    const el = panelRef.current;
    if (!el) return;
    if (document.fullscreenElement) void document.exitFullscreen();
    else void el.requestFullscreen();
  };

  const progress = meta.duration ? (time / meta.duration) * 100 : 0;

  return (
    <div
      ref={panelRef}
      tabIndex={0}
      onKeyDown={onKeyDown}
      className="panel overflow-hidden focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
    >
      <div ref={stageRef} className="relative aspect-video bg-black">
        <video
          ref={videoRef}
          src={src}
          className="h-full w-full object-contain"
          playsInline
          preload="metadata"
          muted={muted}
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onEnded={() => setPlaying(false)}
          onTimeUpdate={syncTime}
          onSeeked={syncTime}
          onLoadedMetadata={syncTime}
        />
        <canvas
          ref={canvasRef}
          className="absolute inset-0 h-full w-full"
          style={{ cursor }}
          onMouseMove={onMouseMove}
          onMouseLeave={() => {
            hoverRef.current = -1;
            draw();
          }}
          onClick={onClick}
        />
        {badge && (
          <span className="chip pointer-events-none absolute left-3 top-3 border-white/10 bg-black/50 backdrop-blur">
            {badge}
          </span>
        )}
        {!playing && time === 0 && !selected && (
          <button
            onClick={toggle}
            aria-label="Play"
            className="absolute left-1/2 top-1/2 grid h-14 w-14 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full bg-white/10 text-white backdrop-blur-md transition hover:scale-105 hover:bg-white/20"
          >
            <Play size={22} strokeWidth={1.75} className="ml-0.5" />
          </button>
        )}
      </div>

      <div className="flex items-center gap-1.5 border-t border-white/[0.06] px-3 py-2">
        <button className="btn-icon" onClick={toggle} aria-label={playing ? 'Pause' : 'Play'} title={playing ? 'Pause (Space)' : 'Play (Space)'}>
          {playing ? <Pause {...ICON} /> : <Play {...ICON} />}
        </button>
        <button className="btn-icon" onClick={() => step(-1)} aria-label="Previous frame" title="Previous frame (←)">
          <ChevronLeft {...ICON} />
        </button>
        <button className="btn-icon" onClick={() => step(1)} aria-label="Next frame" title="Next frame (→)">
          <ChevronRight {...ICON} />
        </button>
        <span className="num shrink-0 whitespace-nowrap px-1 text-xs text-slate-400">
          <span className="text-slate-200">{formatTime(time)}</span> / {formatTime(meta.duration)}
        </span>
        <input
          type="range"
          className="range mx-2 flex-1"
          min={0}
          max={meta.duration}
          step="any"
          value={time}
          aria-label="Seek"
          onChange={(e) => {
            if (videoRef.current) videoRef.current.currentTime = Number(e.target.value);
          }}
          style={{ background: `linear-gradient(90deg, #7c5cff 0%, #22d3ee ${progress}%, #222636 ${progress}%)` }}
        />
        <span className="num hidden w-16 text-right text-[11px] text-slate-500 sm:block">
          f {Math.round(time * meta.fps)}
        </span>
        <button className="btn-icon" onClick={() => setMuted((m) => !m)} aria-label={muted ? 'Unmute' : 'Mute'} title={muted ? 'Unmute' : 'Mute'}>
          {muted ? <VolumeX {...ICON} /> : <Volume2 {...ICON} />}
        </button>
        <button
          className="btn num h-9 w-12 px-0 text-xs text-slate-300 hover:bg-white/[0.06]"
          onClick={() => setRate((r) => RATES[(RATES.indexOf(r) + 1) % RATES.length])}
          aria-label="Playback speed"
          title="Playback speed"
        >
          {rate}×
        </button>
        <button className="btn-icon" onClick={fullscreen} aria-label="Fullscreen" title="Fullscreen">
          <Maximize {...ICON} />
        </button>
      </div>
    </div>
  );
}
