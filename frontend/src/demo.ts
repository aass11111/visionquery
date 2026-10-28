// Dev-only fake data so the UI can be reviewed without the GPU backend: open http://localhost:5173/?demo
import type { FrameHit, Health, SearchResult, VideoMeta } from './types';

export const DEMO = import.meta.env.DEV && new URLSearchParams(location.search).has('demo');

export const demoHealth: Health = {
  status: 'ok',
  device: 'cuda',
  gpu_name: 'NVIDIA GeForce RTX 4060',
  vram_total_gb: 8,
  vram_used_gb: 2.3,
  loaded_models: ['clip', 'yolo'],
};

export const demoVideo: VideoMeta = {
  video_id: 'demo',
  filename: 'street_traffic_1080p.mp4',
  fps: 30,
  frame_count: 2700,
  width: 1920,
  height: 1080,
  duration: 90,
};

function frameImage(seed: number, x: number): string {
  const c = document.createElement('canvas');
  c.width = 480;
  c.height = 270;
  const g = c.getContext('2d')!;
  const sky = g.createLinearGradient(0, 0, 0, 270);
  sky.addColorStop(0, `hsl(${210 + (seed % 30)}, 30%, 32%)`);
  sky.addColorStop(1, '#1b1d24');
  g.fillStyle = sky;
  g.fillRect(0, 0, 480, 270);
  g.fillStyle = '#2a2d36';
  g.fillRect(0, 170, 480, 100);
  g.fillStyle = '#b91c1c';
  g.fillRect(x / 4, 150, 90, 38);
  g.fillRect(x / 4 + 15, 132, 55, 22);
  return c.toDataURL('image/jpeg', 0.8);
}

export function demoSearch(): SearchResult {
  const hits: FrameHit[] = [];
  for (let i = 0; i < 26; i++) {
    const frame = 120 + i * 85 + (i % 3) * 10;
    const x = 200 + ((i * 140) % 1300);
    const s = 0.35 + ((i * 37) % 60) / 100;
    hits.push({
      frame_index: frame,
      time: frame / 30,
      thumbnail_url: frameImage(i, x),
      best_score: s,
      detections: [
        { box: [x, 520, x + 360, 760], score: s, det_score: s - 0.05, clip_score: s + 0.04, label: 'red car' },
        ...(i % 4 === 0
          ? [{ box: [1500, 560, 1780, 720] as [number, number, number, number], score: s * 0.6, det_score: 0.3, clip_score: 0.2, label: 'red car' }]
          : []),
      ],
    });
  }
  return { query: 'red car', frame_step: 5, frames_scanned: 540, hits };
}
