// Shared contract between the React app and the FastAPI backend (see docs/API.md).

/** [x1, y1, x2, y2] in source-video pixel coordinates. */
export type Box = [number, number, number, number];

export interface VideoMeta {
  video_id: string;
  filename: string;
  fps: number;
  frame_count: number;
  width: number;
  height: number;
  duration: number; // seconds
}

export interface Health {
  status: 'ok';
  device: 'cuda' | 'cpu';
  gpu_name: string | null;
  vram_total_gb: number | null;
  vram_used_gb: number | null;
  vram_cap_gb: number | null; // the app never uses more than this (GPU guard)
  loaded_models: string[];
  busy: boolean; // a GPU job is running right now
}

export interface Detection {
  box: Box;
  score: number; // final score 0..1 (detector x CLIP when enabled)
  det_score: number; // raw YOLO-World confidence
  clip_score: number | null; // CLIP image-text similarity 0..1, null when CLIP is off
  label: string;
}

export interface FrameHit {
  frame_index: number;
  time: number; // seconds
  thumbnail_url: string; // full frame JPEG, same aspect as the video
  detections: Detection[]; // sorted by score, best first
  best_score: number;
}

export type SearchMode = 'instant' | 'full';

export interface SearchResult {
  query: string; // what the user typed (may be Arabic)
  query_en: string; // what the models searched for
  translated: boolean;
  mode: SearchMode;
  frame_step: number;
  frames_scanned: number;
  hits: FrameHit[]; // chronological
}

/** What the backend found in a quick scan of the video, used for search suggestions. */
export interface Suggestion {
  label: string; // "car" or "red car"
  count: number;
  frames: number;
  kind: 'object' | 'color';
}

export interface Suggestions {
  video_id: string;
  frames_sampled: number;
  items: Suggestion[];
}

export interface IndexStatus {
  video_id: string;
  status: 'none' | 'building' | 'ready';
  frames_indexed: number;
  step: number; // frames between indexed frames
}

/** What happens to a chosen object. */
export type Effect = 'recolor' | 'blur' | 'pixelate';

/** One object to edit in the video (several can be applied in one render). */
export interface Target {
  query: string;
  frame_index: number;
  box: Box;
  effect: Effect;
  color: string; // #RRGGBB, used by 'recolor'
  strength: number; // 0..1
}

export interface RecolorResult {
  output_url: string;
  frames_written: number;
  frames_segmented: number;
  targets: number;
}

export interface RedactResult {
  output_url: string;
  frames_written: number;
  objects_hidden: number; // detections blurred across the video
}

export interface CommandParse {
  ok: boolean;
  object: string | null; // object phrase as typed
  object_en: string | null; // English query sent to the models
  color: string | null; // #RRGGBB
  color_name: string | null;
  effect: Effect;
  error: string | null; // why it could not be understood
}

export interface CommandResult {
  parse: CommandParse;
  search: SearchResult;
  recolor: RecolorResult | null;
}

export type JobKind = 'search' | 'image_search' | 'recolor' | 'redact' | 'command' | 'index';
export type JobStatus = 'queued' | 'running' | 'done' | 'error';

export interface Job<R = SearchResult | RecolorResult | RedactResult | CommandResult> {
  job_id: string;
  kind: JobKind;
  video_id: string | null;
  title: string;
  status: JobStatus;
  progress: number; // 0..1
  message: string;
  result: R | null;
  error: string | null;
  resumed: boolean; // restarted after the server went down (power cut)
}

export interface SearchRequest {
  video_id: string;
  query: string;
  frame_step: number;
  conf: number;
  use_clip: boolean;
  yolo_half: boolean;
  mode: SearchMode;
}

/** User-tunable options from the settings panel (kept in localStorage). */
export interface AppSettings {
  yoloHalf: boolean; // YOLO-World in FP16 instead of FP32
  conf: number; // detection confidence threshold
  searchMode: SearchMode; // instant = CLIP index picks the frames, full = scan every N frames
}

export const DEFAULT_SETTINGS: AppSettings = { yoloHalf: false, conf: 0.15, searchMode: 'instant' };

export interface RecolorRequest {
  video_id: string;
  targets: Target[];
  frame_step: number;
  yolo_half: boolean;
}

export interface RedactRequest {
  video_id: string;
  query: string; // e.g. "face", "license plate", or Arabic
  effect: 'blur' | 'pixelate';
  frame_step: number;
  conf: number;
  yolo_half: boolean;
}

export interface CommandRequest {
  video_id: string;
  text: string; // "make the red car blue" / "خلي السيارة الحمراء زرقاء"
  frame_step: number;
  conf: number;
  yolo_half: boolean;
}

export interface PreviewRequest {
  video_id: string;
  frame_index: number;
  box: Box;
  effect: Effect;
  color: string;
  strength: number;
}

/** The object the user picked: one detection inside one frame hit. */
export interface Selection {
  hit: FrameHit;
  detection: Detection;
}

/** Live mode: the server's answer to one webcam frame. */
export interface LiveDetections {
  w: number;
  h: number;
  ms: number; // GPU time for this frame
  skipped: boolean; // GPU was busy, frame dropped
  query_en: string;
  detections: { box: Box; score: number; label: string }[];
}
