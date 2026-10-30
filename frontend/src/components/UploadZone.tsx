import React, {
  useState,
  useRef,
  useCallback,
  type DragEvent,
  type ChangeEvent,
  type KeyboardEvent,
} from 'react';
import { Sparkles, UploadCloud, AlertCircle, Search, Scan, Palette } from 'lucide-react';
import { useT } from '../i18n';
import { cn, formatPercent } from '../lib/format';

export interface UploadZoneProps {
  onFile: (file: File) => void;
  progress: number | null; /* 0..1 while uploading */
  error: string | null;
}

export function UploadZone({ onFile, progress, error }: UploadZoneProps) {
  const t = useT();
  const [isDragging, setIsDragging] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const isUploading = progress !== null;
  const displayError = error || localError;

  const handleValidateAndUpload = useCallback(
    (file: File) => {
      const isVideo =
        file.type.startsWith('video/') ||
        /\.(mp4|mov|webm|mkv|avi)$/i.test(file.name);

      if (!isVideo) {
        setLocalError(t('Please choose a valid video file (MP4, MOV, or WEBM).'));
        return;
      }

      setLocalError(null);
      onFile(file);
    },
    [onFile]
  );

  const handleDragOver = useCallback((e: DragEvent<HTMLLabelElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  }, []);

  const handleDragEnter = useCallback((e: DragEvent<HTMLLabelElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: DragEvent<HTMLLabelElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback(
    (e: DragEvent<HTMLLabelElement>) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragging(false);

      if (isUploading) return;

      const file = e.dataTransfer.files?.[0];
      if (file) {
        handleValidateAndUpload(file);
      }
    },
    [isUploading, handleValidateAndUpload]
  );

  const handleChange = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) {
        handleValidateAndUpload(file);
      }
      e.target.value = '';
    },
    [handleValidateAndUpload]
  );

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLLabelElement>) => {
      if ((e.key === 'Enter' || e.key === ' ') && inputRef.current && !isUploading) {
        e.preventDefault();
        inputRef.current.click();
      }
    },
    [isUploading]
  );

  return (
    <div className="animate-fade-up mx-auto flex w-full max-w-3xl flex-col items-center px-4 py-16 text-center">
      {/* Eyebrow */}
      <div className="chip mb-6">
        <Sparkles size={14} strokeWidth={1.75} className="text-accent" />
        <span>YOLO-World · CLIP · SAM 2</span>
      </div>

      {/* Hero Headline */}
      <h1 className="text-4xl font-semibold tracking-tight text-slate-100 md:text-5xl">
        {t('Search video with words.')}
        <br />
        <span className="bg-accent-gradient bg-clip-text text-transparent">
          {t('Recolor anything you find.')}
        </span>
      </h1>

      {/* Subtitle */}
      <p className="mt-4 max-w-xl text-base text-slate-400 md:text-lg">
        {t('Pinpoint objects and actions across footage with zero-shot AI, then track and recolor them with studio precision.')}
      </p>

      {/* Drop Zone */}
      <label
        htmlFor="video-file-input"
        tabIndex={isUploading ? -1 : 0}
        onKeyDown={handleKeyDown}
        onDragOver={handleDragOver}
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={cn(
          'panel mt-10 flex w-full cursor-pointer flex-col items-center justify-center rounded-3xl border-2 border-dashed border-white/10 p-10 transition duration-150',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60',
          isDragging && 'border-accent/60 bg-accent/[0.06] shadow-glow',
          isUploading && 'pointer-events-none cursor-default opacity-90'
        )}
      >
        <input
          ref={inputRef}
          id="video-file-input"
          type="file"
          accept="video/*"
          className="sr-only"
          disabled={isUploading}
          onChange={handleChange}
        />

        <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl border border-white/10 bg-gradient-to-br from-accent/20 to-signal/10 text-accent">
          <UploadCloud size={28} strokeWidth={1.75} />
        </div>

        <span className="text-base font-medium text-slate-100">
          {t('Drop a video here or browse')}
        </span>

        {isUploading ? (
          <div className="mt-3 flex w-full max-w-xs flex-col items-center gap-2">
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-ink-700">
              <div
                className="h-full bg-accent-gradient transition-all duration-150"
                style={{ width: `${Math.min(100, Math.max(0, progress * 100))}%` }}
              />
            </div>
            <div className="flex items-center gap-1.5 text-xs text-slate-400">
              <span className="num font-medium text-slate-200">
                {formatPercent(progress)}
              </span>
              <span>{t('Uploading…')}</span>
            </div>
          </div>
        ) : (
          <p className="num mt-1 text-xs text-slate-500">
            {t('MP4, MOV, WEBM · up to 2 GB')}
          </p>
        )}

        {displayError && (
          <div className="mt-4 flex items-center justify-center gap-2 text-sm text-rose-400">
            <AlertCircle size={16} strokeWidth={1.75} className="shrink-0" />
            <span>{displayError}</span>
          </div>
        )}
      </label>

      {/* Feature Cards */}
      <div className="mt-10 grid w-full grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="panel flex flex-col items-start p-4 text-start">
          <div className="mb-3 flex h-8 w-8 items-center justify-center rounded-lg border border-white/[0.06] bg-white/[0.03] text-accent">
            <Search size={16} strokeWidth={1.75} />
          </div>
          <h3 className="text-sm font-semibold text-slate-200">
            {t('Natural-language search')}
          </h3>
          <p className="mt-1 text-xs leading-relaxed text-slate-400">
            {t('Find arbitrary objects and moments across footage using open-vocabulary prompts.')}
          </p>
        </div>

        <div className="panel flex flex-col items-start p-4 text-start">
          <div className="mb-3 flex h-8 w-8 items-center justify-center rounded-lg border border-white/[0.06] bg-white/[0.03] text-signal">
            <Scan size={16} strokeWidth={1.75} />
          </div>
          <h3 className="text-sm font-semibold text-slate-200">
            {t('Segment & track')}
          </h3>
          <p className="mt-1 text-xs leading-relaxed text-slate-400">
            {t('Extract pixel-accurate masks with SAM 2 that follow targets through motion.')}
          </p>
        </div>

        <div className="panel flex flex-col items-start p-4 text-start">
          <div className="mb-3 flex h-8 w-8 items-center justify-center rounded-lg border border-white/[0.06] bg-white/[0.03] text-accent">
            <Palette size={16} strokeWidth={1.75} />
          </div>
          <h3 className="text-sm font-semibold text-slate-200">
            {t('Realistic recoloring')}
          </h3>
          <p className="mt-1 text-xs leading-relaxed text-slate-400">
            {t('Restyle target elements cleanly while preserving fine surface textures and lighting.')}
          </p>
        </div>
      </div>
    </div>
  );
}
