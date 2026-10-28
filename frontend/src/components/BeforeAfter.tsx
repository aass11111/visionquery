import { useState, useRef, useCallback } from 'react';
import clsx from 'clsx';
import { ChevronsLeftRight } from 'lucide-react';

export function BeforeAfter({
  before,
  after,
  className,
}: {
  before: string;
  after: string;
  className?: string;
}) {
  const [pos, setPos] = useState(50);
  const containerRef = useRef<HTMLDivElement>(null);

  const updatePos = useCallback((clientX: number) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    if (rect.width === 0) return;
    const relativeX = clientX - rect.left;
    const percentage = Math.max(0, Math.min(100, (relativeX / rect.width) * 100));
    setPos(percentage);
  }, []);

  const handlePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    updatePos(e.clientX);
  };

  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.currentTarget.hasPointerCapture(e.pointerId)) {
      updatePos(e.clientX);
    }
  };

  const handlePointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.currentTarget.hasPointerCapture(e.pointerId)) {
      e.currentTarget.releasePointerCapture(e.pointerId);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'ArrowLeft') {
      e.preventDefault();
      setPos((prev) => Math.max(0, prev - 5));
    } else if (e.key === 'ArrowRight') {
      e.preventDefault();
      setPos((prev) => Math.min(100, prev + 5));
    }
  };

  return (
    <div
      ref={containerRef}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerUp}
      className={clsx(
        'relative aspect-video overflow-hidden rounded-xl bg-black select-none cursor-ew-resize touch-none',
        className
      )}
    >
      <img
        src={after}
        alt="After"
        draggable={false}
        className="absolute inset-0 h-full w-full object-contain pointer-events-none"
      />

      <img
        src={before}
        alt="Before"
        draggable={false}
        style={{ clipPath: `inset(0 ${100 - pos}% 0 0)` }}
        className="absolute inset-0 h-full w-full object-contain pointer-events-none"
      />

      <div
        className="absolute top-0 bottom-0 w-[2px] -translate-x-1/2 bg-white pointer-events-none"
        style={{ left: `${pos}%` }}
      >
        <div
          role="slider"
          tabIndex={0}
          aria-label="Comparison slider handle"
          aria-valuenow={Math.round(pos)}
          aria-valuemin={0}
          aria-valuemax={100}
          onKeyDown={handleKeyDown}
          className="pointer-events-auto absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 flex h-8 w-8 items-center justify-center rounded-full bg-white/90 text-ink-950 shadow-lg transition duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 cursor-ew-resize"
        >
          <ChevronsLeftRight size={16} strokeWidth={1.75} />
        </div>
      </div>

      <span className="chip absolute top-3 left-3 backdrop-blur pointer-events-none">
        Before
      </span>
      <span className="chip absolute top-3 right-3 backdrop-blur pointer-events-none">
        After
      </span>
    </div>
  );
}
