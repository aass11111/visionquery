import type { Box, FrameHit } from '../types';

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
  scale: number; // displayed px per source px
}

/** Where a srcW x srcH image lands inside a boxW x boxH container with object-fit: contain. */
export function fitContain(srcW: number, srcH: number, boxW: number, boxH: number): Rect {
  const scale = Math.min(boxW / srcW, boxH / srcH);
  const w = srcW * scale;
  const h = srcH * scale;
  return { x: (boxW - w) / 2, y: (boxH - h) / 2, w, h, scale };
}

/** The hit closest to frameIndex, if one lies within maxDistance frames. */
export function nearestHit(hits: FrameHit[], frameIndex: number, maxDistance: number): FrameHit | null {
  let best: FrameHit | null = null;
  let bestDist = Infinity;
  for (const h of hits) {
    const d = Math.abs(h.frame_index - frameIndex);
    if (d < bestDist) {
      best = h;
      bestDist = d;
    }
  }
  return best && bestDist <= maxDistance ? best : null;
}

/** Box as CSS percentages of the frame, for overlays on thumbnails. */
export function boxToPercent(box: Box, width: number, height: number) {
  const [x1, y1, x2, y2] = box;
  return {
    left: `${(x1 / width) * 100}%`,
    top: `${(y1 / height) * 100}%`,
    width: `${((x2 - x1) / width) * 100}%`,
    height: `${((y2 - y1) / height) * 100}%`,
  };
}

export function sameBox(a: Box, b: Box): boolean {
  return a.every((v, i) => Math.abs(v - b[i]) < 0.5);
}
