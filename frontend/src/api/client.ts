import type {
  CommandParse,
  CommandRequest,
  Health,
  IndexStatus,
  Job,
  Library,
  PreviewRequest,
  RecolorRequest,
  RedactRequest,
  SearchRequest,
  Suggestions,
  VideoMeta,
} from '../types';

const BACKEND_DOWN = 'Cannot reach the backend on port 8000 — is it running?';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

const json = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

export const api = {
  health: () => request<Health>('/api/health'),

  /** XHR so the UI can show real upload progress. */
  uploadVideo(file: File, onProgress: (p: number) => void): Promise<VideoMeta> {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      const form = new FormData();
      form.append('file', file);
      xhr.open('POST', '/api/videos');
      xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
      xhr.onload = () => {
        let body: { detail?: string } & Partial<VideoMeta> = {};
        try {
          body = JSON.parse(xhr.responseText);
        } catch {
          /* ignore */
        }
        if (xhr.status >= 200 && xhr.status < 300) resolve(body as VideoMeta);
        else reject(new Error(body.detail ?? (xhr.status >= 500 ? BACKEND_DOWN : `Upload failed (${xhr.status})`)));
      };
      xhr.onerror = () => reject(new Error(BACKEND_DOWN));
      xhr.send(form);
    });
  },

  streamUrl: (videoId: string) => `/api/videos/${videoId}/stream`,
  suggestions: (videoId: string) => request<Suggestions>(`/api/videos/${videoId}/suggestions`),
  video: (videoId: string) => request<VideoMeta>(`/api/videos/${videoId}`),
  library: () => request<Library>('/api/library'),
  deleteVideo: (videoId: string) => request<{ deleted: string }>(`/api/videos/${videoId}`, { method: 'DELETE' }),
  indexStatus: (videoId: string) => request<IndexStatus>(`/api/videos/${videoId}/index`),
  parseCommand: (text: string) => request<CommandParse>(`/api/command/parse?text=${encodeURIComponent(text)}`),
  command: (req: CommandRequest) => request<{ job_id: string }>('/api/command', json(req)),
  redact: (req: RedactRequest) => request<{ job_id: string }>('/api/redact', json(req)),
  activeJobs: () => request<Job[]>('/api/jobs?active=1'),

  searchImage(videoId: string, file: File): Promise<{ job_id: string }> {
    const form = new FormData();
    form.append('video_id', videoId);
    form.append('top_k', '40');
    form.append('file', file);
    return request<{ job_id: string }>('/api/search-image', { method: 'POST', body: form });
  },
  search: (req: SearchRequest) => request<{ job_id: string }>('/api/search', json(req)),
  recolor: (req: RecolorRequest) => request<{ job_id: string }>('/api/recolor', json(req)),
  job: (jobId: string) => request<Job>(`/api/jobs/${jobId}`),

  async preview(req: PreviewRequest): Promise<string> {
    const res = await fetch('/api/preview', json(req));
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail ?? `Preview failed (${res.status})`);
    }
    return URL.createObjectURL(await res.blob());
  },
};

/** Live job updates over WebSocket, with polling as a fallback. Returns an unsubscribe function. */
export function watchJob(jobId: string, onUpdate: (job: Job) => void): () => void {
  let closed = false;
  let poll: number | undefined;
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${proto}://${location.host}/api/jobs/${jobId}/ws`);

  ws.onmessage = (e) => onUpdate(JSON.parse(e.data) as Job);
  ws.onerror = () => {
    if (closed || poll !== undefined) return;
    poll = window.setInterval(async () => {
      try {
        const job = await api.job(jobId);
        onUpdate(job);
        if (job.status === 'done' || job.status === 'error') window.clearInterval(poll);
      } catch {
        /* keep polling */
      }
    }, 1000);
  };

  return () => {
    closed = true;
    ws.close();
    if (poll !== undefined) window.clearInterval(poll);
  };
}
