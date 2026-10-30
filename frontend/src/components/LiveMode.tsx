import { useEffect, useRef, useState, useCallback } from 'react';
import { Radio, X, Video, Square, AlertTriangle } from 'lucide-react';
import type { LiveDetections } from '../types';
import { cn } from '../lib/format';

type EffectMode = 'Boxes' | 'Blur' | 'Pixelate';
type FpsOption = 1 | 2 | 3;

function drawRoundedRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  radius: number
): void {
  const r = Math.min(radius, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

export function LiveMode(props: { onClose: () => void }) {
  const { onClose } = props;

  const [query, setQuery] = useState('person');
  const [debouncedQuery, setDebouncedQuery] = useState('person');
  const [fps, setFps] = useState<FpsOption>(2);
  const [effect, setEffect] = useState<EffectMode>('Boxes');
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Stats
  const [serverMs, setServerMs] = useState<number | null>(null);
  const [effectiveFps, setEffectiveFps] = useState<number>(0);
  const [droppedCount, setDroppedCount] = useState<number>(0);
  const [detectionCount, setDetectionCount] = useState<number>(0);
  const [queryEn, setQueryEn] = useState<string | null>(null);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const pendingRef = useRef<boolean>(false);
  const latestDetectionsRef = useRef<LiveDetections | null>(null);
  const sendCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const pixelCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const effectRef = useRef<EffectMode>(effect);
  const timestampsRef = useRef<number[]>([]);

  useEffect(() => {
    effectRef.current = effect;
  }, [effect]);

  // Debounce query changes to avoid socket churn while typing
  useEffect(() => {
    const handler = window.setTimeout(() => {
      setDebouncedQuery(query);
    }, 250);
    return () => window.clearTimeout(handler);
  }, [query]);

  // Stop camera stream & socket
  const stopRunning = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    pendingRef.current = false;
    latestDetectionsRef.current = null;
    setIsRunning(false);
  }, []);

  // Start camera stream
  const startRunning = useCallback(async () => {
    setError(null);
    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error('Webcam is not supported in this browser environment.');
      }
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 1280, height: 720 },
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setIsRunning(true);
    } catch (err: unknown) {
      let message = 'Failed to access camera.';
      if (err instanceof DOMException) {
        if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
          message = 'Camera permission denied. Please allow camera access in your browser settings.';
        } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
          message = 'No camera found. Please connect a webcam.';
        } else {
          message = err.message || 'Unable to start camera.';
        }
      } else if (err instanceof Error) {
        message = err.message;
      }
      setError(message);
      setIsRunning(false);
    }
  }, []);

  const handleToggleRunning = () => {
    if (isRunning) {
      stopRunning();
    } else {
      void startRunning();
    }
  };

  const handleClose = () => {
    stopRunning();
    onClose();
  };

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        handleClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [stopRunning, onClose]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopRunning();
    };
  }, [stopRunning]);

  // Manage WebSocket connection (reconnects when debouncedQuery changes while running)
  useEffect(() => {
    if (!isRunning) {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      pendingRef.current = false;
      return;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const wsUrl = `${protocol}://${window.location.host}/api/live?query=${encodeURIComponent(
      debouncedQuery.trim()
    )}&conf=0.25`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;
    pendingRef.current = false;

    ws.onopen = () => {
      setError(null);
    };

    ws.onmessage = (event: MessageEvent<string>) => {
      try {
        const data = JSON.parse(event.data) as LiveDetections;
        pendingRef.current = false;
        latestDetectionsRef.current = data;
        setServerMs(data.ms);
        setDetectionCount(data.detections.length);
        setQueryEn(data.query_en);
        if (data.skipped) {
          setDroppedCount((prev) => prev + 1);
        }

        const now = performance.now();
        timestampsRef.current.push(now);
        timestampsRef.current = timestampsRef.current.filter((t) => now - t <= 2000);
        if (timestampsRef.current.length > 1) {
          const span = (now - timestampsRef.current[0]) / 1000;
          if (span > 0) {
            setEffectiveFps(Math.round(((timestampsRef.current.length - 1) / span) * 10) / 10);
          }
        }
      } catch {
        pendingRef.current = false;
      }
    };

    ws.onerror = () => {
      setError('Live detection socket error occurred.');
      pendingRef.current = false;
    };

    ws.onclose = () => {
      pendingRef.current = false;
    };

    return () => {
      ws.close();
      if (wsRef.current === ws) {
        wsRef.current = null;
      }
      pendingRef.current = false;
    };
  }, [isRunning, debouncedQuery]);

  // Frame sending interval (back-pressured, only 1 frame in flight)
  useEffect(() => {
    if (!isRunning) return;

    const interval = window.setInterval(() => {
      const ws = wsRef.current;
      const video = videoRef.current;

      if (
        ws &&
        ws.readyState === WebSocket.OPEN &&
        !pendingRef.current &&
        video &&
        video.readyState >= 2 &&
        video.videoWidth > 0 &&
        video.videoHeight > 0
      ) {
        if (!sendCanvasRef.current) {
          sendCanvasRef.current = document.createElement('canvas');
        }
        const sCanvas = sendCanvasRef.current;
        const targetWidth = 640;
        const scale = targetWidth / video.videoWidth;
        const targetHeight = Math.round(video.videoHeight * scale);

        if (sCanvas.width !== targetWidth || sCanvas.height !== targetHeight) {
          sCanvas.width = targetWidth;
          sCanvas.height = targetHeight;
        }

        const sCtx = sCanvas.getContext('2d');
        if (sCtx) {
          sCtx.drawImage(video, 0, 0, targetWidth, targetHeight);
          pendingRef.current = true;
          sCanvas.toBlob(
            (blob) => {
              if (blob && ws.readyState === WebSocket.OPEN) {
                ws.send(blob);
              } else {
                pendingRef.current = false;
              }
            },
            'image/jpeg',
            0.7
          );
        }
      }
    }, 1000 / fps);

    return () => {
      window.clearInterval(interval);
    };
  }, [isRunning, fps]);

  // Canvas render loop via requestAnimationFrame
  useEffect(() => {
    if (!isRunning) {
      const canvas = canvasRef.current;
      if (canvas) {
        const ctx = canvas.getContext('2d');
        ctx?.clearRect(0, 0, canvas.width, canvas.height);
      }
      return;
    }

    let animationId: number;

    const render = () => {
      const canvas = canvasRef.current;
      const video = videoRef.current;

      if (canvas && video && video.readyState >= 2) {
        const vw = video.videoWidth || 1280;
        const vh = video.videoHeight || 720;

        if (canvas.width !== vw || canvas.height !== vh) {
          canvas.width = vw;
          canvas.height = vh;
        }

        const ctx = canvas.getContext('2d');
        if (ctx) {
          // 1. Draw raw video frame
          ctx.filter = 'none';
          ctx.drawImage(video, 0, 0, vw, vh);

          // 2. Draw detections with chosen client-side effect
          const result = latestDetectionsRef.current;
          const currentEffect = effectRef.current;

          if (result && result.detections && result.w > 0 && result.h > 0) {
            const scaleX = vw / result.w;
            const scaleY = vh / result.h;

            for (const det of result.detections) {
              const [x1, y1, x2, y2] = det.box;
              const bx = x1 * scaleX;
              const by = y1 * scaleY;
              const bw = (x2 - x1) * scaleX;
              const bh = (y2 - y1) * scaleY;

              if (bw <= 0 || bh <= 0) continue;

              if (currentEffect === 'Boxes') {
                ctx.strokeStyle = '#a593ff';
                ctx.lineWidth = 2;
                ctx.strokeRect(bx, by, bw, bh);

                const pct = Math.round(det.score * 100);
                const tag = `${det.label} ${pct}%`;

                ctx.font = '600 12px ui-sans-serif, system-ui, sans-serif';
                const metrics = ctx.measureText(tag);
                const tagH = 20;
                const tagW = metrics.width + 12;
                const tagY = by >= tagH ? by - tagH : by;

                ctx.fillStyle = '#a593ff';
                ctx.fillRect(bx, tagY, tagW, tagH);

                ctx.fillStyle = '#090a10';
                ctx.textBaseline = 'middle';
                ctx.fillText(tag, bx + 6, tagY + tagH / 2);
              } else if (currentEffect === 'Blur') {
                ctx.save();
                drawRoundedRect(ctx, bx, by, bw, bh, 8);
                ctx.clip();
                ctx.filter = 'blur(18px)';
                ctx.drawImage(video, 0, 0, vw, vh);
                ctx.restore();
              } else if (currentEffect === 'Pixelate') {
                const smallW = Math.max(1, Math.round(bw / 16));
                const smallH = Math.max(1, Math.round(bh / 16));

                if (!pixelCanvasRef.current) {
                  pixelCanvasRef.current = document.createElement('canvas');
                }
                const pCanvas = pixelCanvasRef.current;
                if (pCanvas.width !== smallW || pCanvas.height !== smallH) {
                  pCanvas.width = smallW;
                  pCanvas.height = smallH;
                }

                const pCtx = pCanvas.getContext('2d');
                if (pCtx) {
                  const vScaleX = video.videoWidth / vw;
                  const vScaleY = video.videoHeight / vh;
                  const sx = bx * vScaleX;
                  const sy = by * vScaleY;
                  const sw = bw * vScaleX;
                  const sh = bh * vScaleY;

                  pCtx.imageSmoothingEnabled = true;
                  pCtx.drawImage(video, sx, sy, sw, sh, 0, 0, smallW, smallH);

                  ctx.save();
                  drawRoundedRect(ctx, bx, by, bw, bh, 8);
                  ctx.clip();
                  ctx.imageSmoothingEnabled = false;
                  ctx.drawImage(pCanvas, 0, 0, smallW, smallH, bx, by, bw, bh);
                  ctx.restore();
                }
              }
            }
          }
        }
      }

      animationId = requestAnimationFrame(render);
    };

    animationId = requestAnimationFrame(render);

    return () => {
      cancelAnimationFrame(animationId);
    };
  }, [isRunning]);

  return (
    <div className="fixed inset-0 z-50 flex flex-col justify-between overflow-y-auto bg-ink-950/95 p-4 backdrop-blur animate-fade-up md:p-6">
      <div className="mx-auto flex h-full w-full max-w-6xl flex-col gap-4">
        {/* Header row */}
        <div className="flex items-center justify-between gap-4">
          <div className="flex flex-wrap items-center gap-3">
            <Radio
              size={16}
              strokeWidth={1.75}
              className={cn('text-accent shrink-0', isRunning && 'animate-pulse')}
            />
            <h2 className="text-base font-semibold text-slate-100">Live mode</h2>
            <span className="chip">
              Detection only · max {fps} fps · GPU-safe
            </span>
          </div>

          <button
            type="button"
            onClick={handleClose}
            className="btn-icon"
            aria-label="Close live mode"
            title="Close live mode"
          >
            <X size={16} strokeWidth={1.75} />
          </button>
        </div>

        {/* Controls row */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="min-w-[220px] flex-1">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search query (e.g. person, car, شخص)..."
              className="input"
            />
          </div>

          {/* FPS segmented buttons */}
          <div className="flex items-center gap-1 rounded-xl border border-white/[0.08] bg-ink-850 p-1">
            <span className="px-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">
              FPS
            </span>
            {([1, 2, 3] as const).map((rate) => (
              <button
                key={rate}
                type="button"
                onClick={() => setFps(rate)}
                className={cn(
                  'num rounded-lg px-2.5 py-1 text-xs font-medium transition duration-150',
                  fps === rate
                    ? 'bg-accent text-white shadow-glow'
                    : 'text-slate-400 hover:text-slate-200'
                )}
              >
                {rate}
              </button>
            ))}
          </div>

          {/* Effect segmented buttons */}
          <div className="flex items-center gap-1 rounded-xl border border-white/[0.08] bg-ink-850 p-1">
            {(['Boxes', 'Blur', 'Pixelate'] as const).map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() => setEffect(mode)}
                className={cn(
                  'rounded-lg px-3 py-1 text-xs font-medium transition duration-150',
                  effect === mode
                    ? 'bg-accent text-white shadow-glow'
                    : 'text-slate-400 hover:text-slate-200'
                )}
              >
                {mode}
              </button>
            ))}
          </div>

          {/* Start/Stop button */}
          <button
            type="button"
            onClick={handleToggleRunning}
            className="btn-primary"
          >
            {isRunning ? (
              <>
                <Square size={16} strokeWidth={1.75} />
                <span>Stop</span>
              </>
            ) : (
              <>
                <Video size={16} strokeWidth={1.75} />
                <span>Start</span>
              </>
            )}
          </button>
        </div>

        {/* Error notification */}
        {error && (
          <div className="flex items-center gap-2 rounded-xl border border-rose-500/20 bg-rose-500/10 px-4 py-2.5 text-sm text-rose-400">
            <AlertTriangle size={16} strokeWidth={1.75} className="shrink-0" />
            <span className="flex-1">{error}</span>
          </div>
        )}

        {/* Stage */}
        <div className="flex-1 min-h-0 flex items-center justify-center">
          <div className="relative aspect-video w-full max-h-full bg-black rounded-2xl overflow-hidden flex items-center justify-center border border-white/[0.06] shadow-panel">
            <video
              ref={videoRef}
              playsInline
              muted
              autoPlay
              className="hidden"
            />
            <canvas
              ref={canvasRef}
              className="h-full w-full object-contain"
            />
            {!isRunning && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-ink-950/60 p-6 text-center backdrop-blur-sm">
                <Video size={36} strokeWidth={1.5} className="text-slate-600" />
                <div className="text-sm font-medium text-slate-300">Camera is stopped</div>
                <div className="text-xs text-slate-500">
                  Press Start to begin live webcam streaming and object detection
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Footer stats row */}
        <div className="flex flex-wrap items-center justify-between gap-4 border-t border-white/[0.06] pt-3 text-xs text-slate-400">
          <div className="flex flex-wrap items-center gap-6">
            <div className="flex items-center gap-1.5">
              <span className="text-slate-500">Latency:</span>
              <span className="num font-semibold text-slate-200">
                {serverMs !== null ? `${Math.round(serverMs)} ms` : '—'}
              </span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-slate-500">Effective rate:</span>
              <span className="num font-semibold text-slate-200">
                {effectiveFps > 0 ? `${effectiveFps.toFixed(1)} fps` : '—'}
              </span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-slate-500">Dropped:</span>
              <span className="num font-semibold text-slate-200">{droppedCount}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-slate-500">Detections:</span>
              <span className="num font-semibold text-slate-200">{detectionCount}</span>
            </div>
          </div>

          {queryEn && queryEn.trim().toLowerCase() !== query.trim().toLowerCase() && (
            <div className="flex items-center gap-1 text-slate-400">
              <span>searching as:</span>
              <span className="font-medium text-signal">"{queryEn}"</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
