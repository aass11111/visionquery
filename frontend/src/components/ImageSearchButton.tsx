import React, { useCallback, useEffect, useRef, useState, type ChangeEvent, type DragEvent } from 'react';
import { ImagePlus, Loader2 } from 'lucide-react';
import { useT } from '../i18n';
import { cn } from '../lib/format';

const MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024; // 10 MB

export function ImageSearchButton(props: {
  onImage: (file: File) => void;
  disabled?: boolean;
  loading?: boolean;
  indexReady: boolean;
}) {
  const { onImage, disabled = false, loading = false, indexReady } = props;
  const t = useT();

  const [thumbnailUrl, setThumbnailUrl] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const inputRef = useRef<HTMLInputElement>(null);
  const activeUrlRef = useRef<string | null>(null);
  const dragCounterRef = useRef(0);

  const updateThumbnail = useCallback((url: string | null) => {
    if (activeUrlRef.current) {
      URL.revokeObjectURL(activeUrlRef.current);
    }
    activeUrlRef.current = url;
    setThumbnailUrl(url);
  }, []);

  useEffect(() => {
    return () => {
      if (activeUrlRef.current) {
        URL.revokeObjectURL(activeUrlRef.current);
      }
    };
  }, []);

  const processFile = useCallback(
    (file: File) => {
      if (!file.type.startsWith('image/')) {
        setError(t('Please select an image file'));
        return;
      }

      if (file.size > MAX_FILE_SIZE_BYTES) {
        setError(t('Image must be 10 MB or less'));
        return;
      }

      setError(null);
      const url = URL.createObjectURL(file);
      updateThumbnail(url);
      onImage(file);
    },
    [onImage, updateThumbnail]
  );

  const handleInputChange = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      processFile(file);
    }
    e.target.value = '';
  };

  const handleClick = () => {
    if (disabled || loading || !indexReady) return;
    setError(null);
    inputRef.current?.click();
  };

  const handleDragEnter = (e: DragEvent<HTMLButtonElement>) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounterRef.current += 1;
    if (e.dataTransfer.items && e.dataTransfer.items.length > 0) {
      setIsDragging(true);
    }
  };

  const handleDragLeave = (e: DragEvent<HTMLButtonElement>) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounterRef.current -= 1;
    if (dragCounterRef.current <= 0) {
      dragCounterRef.current = 0;
      setIsDragging(false);
    }
  };

  const handleDragOver = (e: DragEvent<HTMLButtonElement>) => {
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = 'copy';
  };

  const handleDrop = (e: DragEvent<HTMLButtonElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    dragCounterRef.current = 0;

    if (disabled || loading || !indexReady) return;

    const file = e.dataTransfer.files?.[0];
    if (file) {
      processFile(file);
    }
  };

  const isButtonDisabled = disabled || loading || !indexReady;

  const buttonTitle = !indexReady
    ? t('Building the video index… image search will be ready in a moment')
    : t('Search the video with a photo (uses the CLIP index)');

  return (
    <div className="relative inline-flex items-center">
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={handleInputChange}
        aria-hidden="true"
        tabIndex={-1}
      />

      <button
        type="button"
        disabled={isButtonDisabled}
        title={buttonTitle}
        aria-label={t('Search the video with a photo (uses the CLIP index)')}
        onClick={handleClick}
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
        className={cn(
          'btn-ghost h-11 px-3',
          isDragging && 'border-accent/60'
        )}
      >
        {loading ? (
          <Loader2 size={16} strokeWidth={1.75} className="animate-spin text-accent" />
        ) : thumbnailUrl ? (
          <img
            src={thumbnailUrl}
            alt={t('Search reference')}
            className="h-7 w-7 shrink-0 rounded-lg object-cover"
          />
        ) : (
          <ImagePlus size={16} strokeWidth={1.75} />
        )}
        <span className="hidden sm:inline">{t('Image')}</span>
      </button>

      {error && (
        <span
          role="alert"
          className="pointer-events-none absolute start-1/2 top-full z-20 mt-1.5 -translate-x-1/2 whitespace-nowrap rounded-lg border border-rose-500/20 bg-ink-900/95 px-2.5 py-1 text-[11px] font-medium text-rose-400 shadow-panel backdrop-blur-md animate-fade-up"
        >
          {error}
        </span>
      )}
    </div>
  );
}
