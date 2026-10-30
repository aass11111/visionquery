import { useCallback, useEffect, useRef, useState } from 'react';
import { AlertTriangle, Film, RotateCw, Wand2, X } from 'lucide-react';
import { api, watchJob } from './api/client';
import { FrameStepSlider } from './components/FrameStepSlider';
import { Header } from './components/Header';
import { ImageSearchButton } from './components/ImageSearchButton';
import { JobProgress } from './components/JobProgress';
import { LiveMode } from './components/LiveMode';
import { PrivacyPanel } from './components/PrivacyPanel';
import { RecolorPanel } from './components/RecolorPanel';
import { ResultsGrid } from './components/ResultsGrid';
import { SearchBar } from './components/SearchBar';
import { SettingsPanel } from './components/SettingsPanel';
import { TargetsPanel } from './components/TargetsPanel';
import { Timeline } from './components/Timeline';
import { UploadZone } from './components/UploadZone';
import { VideoPlayer } from './components/VideoPlayer';
import { DEMO, demoHealth, demoSearch, demoSuggestions, demoVideo } from './demo';
import { cn } from './lib/format';
import {
  DEFAULT_SETTINGS,
  type AppSettings,
  type CommandParse,
  type CommandResult,
  type Effect,
  type Health,
  type IndexStatus,
  type Job,
  type RecolorResult,
  type RedactResult,
  type SearchResult,
  type Selection,
  type Suggestion,
  type Target,
  type VideoMeta,
} from './types';

type View = 'original' | 'result';
type RenderKind = 'recolor' | 'redact';

const SETTINGS_KEY = 'vq-settings';
const VIDEO_KEY = 'vq-video';

function loadSettings(): AppSettings {
  try {
    return { ...DEFAULT_SETTINGS, ...JSON.parse(localStorage.getItem(SETTINGS_KEY) ?? '{}') };
  } catch {
    return DEFAULT_SETTINGS;
  }
}

function store(key: string, value: string | null) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    /* storage unavailable */
  }
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [video, setVideo] = useState<VideoMeta | null>(null);
  const [indexStatus, setIndexStatus] = useState<IndexStatus | null>(null);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const [settings, setSettings] = useState<AppSettings>(loadSettings);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [liveOpen, setLiveOpen] = useState(false);
  const [suggestions, setSuggestions] = useState<Suggestion[] | null>(null);
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);
  const [query, setQuery] = useState('');
  const [command, setCommand] = useState<CommandParse | null>(null);
  const [useClip, setUseClip] = useState(true);
  const [frameStep, setFrameStep] = useState(5);
  const [searchJob, setSearchJob] = useState<Job | null>(null);
  const [search, setSearch] = useState<SearchResult | null>(null);

  const [selection, setSelection] = useState<Selection | null>(null);
  const [effect, setEffect] = useState<Effect>('recolor');
  const [color, setColor] = useState('#3b82f6');
  const [strength, setStrength] = useState(0.85);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [targets, setTargets] = useState<Target[]>([]);
  const [renderJob, setRenderJob] = useState<Job | null>(null);
  const [renderKind, setRenderKind] = useState<RenderKind | null>(null);
  const [outputUrl, setOutputUrl] = useState<string | null>(null);
  const [hiddenCount, setHiddenCount] = useState<number | null>(null);

  const [view, setView] = useState<View>('original');
  const [currentTime, setCurrentTime] = useState(0);
  const [seekRequest, setSeekRequest] = useState<{ time: number; nonce: number } | null>(null);
  const [toast, setToast] = useState<{ job: Job; title: string } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const unsubscribers = useRef<Array<() => void>>([]);

  const searching = searchJob?.status === 'queued' || searchJob?.status === 'running';
  const rendering = renderJob?.status === 'queued' || renderJob?.status === 'running';
  const hits = search?.hits ?? [];
  const videoId = video?.video_id;

  // GPU / model status in the header.
  useEffect(() => {
    if (DEMO) return;
    let alive = true;
    const tick = () => api.health().then((h) => alive && setHealth(h)).catch(() => undefined);
    tick();
    const id = window.setInterval(tick, 4000);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, []);

  useEffect(() => () => unsubscribers.current.forEach((u) => u()), []);

  useEffect(() => store(SETTINGS_KEY, JSON.stringify(settings)), [settings]);

  useEffect(() => {
    if (!DEMO) return;
    setHealth(demoHealth);
    setVideo(demoVideo);
    setSuggestions(demoSuggestions);
    setSearch(demoSearch());
    setIndexStatus({ video_id: 'demo', status: 'ready', frames_indexed: 180, step: 15 });
  }, []);

  // ---------------------------------------------------------------- job plumbing

  const follow = useCallback((jobId: string, title: string, onJob: (job: Job) => void) => {
    const unsub = watchJob(jobId, (job) => {
      onJob(job);
      setToast({ job, title: job.resumed ? `${title} (resumed)` : title });
    });
    unsubscribers.current.push(unsub);
  }, []);

  const onSearchJob = useCallback((job: Job) => {
    setSearchJob(job);
    if (job.status === 'done') setSearch(job.result as SearchResult);
  }, []);

  const onRenderJob = useCallback(
    (kind: RenderKind) => (job: Job) => {
      setRenderJob(job);
      setRenderKind(kind);
      if (job.status !== 'done') return;
      if (kind === 'redact') {
        const r = job.result as RedactResult;
        setOutputUrl(r.output_url);
        setHiddenCount(r.objects_hidden);
      } else {
        setOutputUrl((job.result as RecolorResult).output_url);
      }
      setView('result');
    },
    [],
  );

  const onCommandJob = useCallback((job: Job) => {
    setSearchJob(job);
    setRenderJob(job);
    setRenderKind('recolor');
    if (job.status !== 'done') return;
    const r = job.result as CommandResult;
    setSearch(r.search);
    if (r.recolor) {
      setOutputUrl(r.recolor.output_url);
      setView('result');
    } else {
      setNotice(`Nothing matching “${r.parse.object_en}” was found in this video.`);
    }
  }, []);

  /** Re-attach to jobs that were running before a refresh or a server restart (power cut). */
  const reattach = useCallback(
    async (vid: string) => {
      try {
        const active = await api.activeJobs();
        for (const j of active.filter((j) => j.video_id === vid)) {
          if (j.kind === 'search' || j.kind === 'image_search') follow(j.job_id, j.title, onSearchJob);
          else if (j.kind === 'recolor') follow(j.job_id, j.title, onRenderJob('recolor'));
          else if (j.kind === 'redact') follow(j.job_id, j.title, onRenderJob('redact'));
          else if (j.kind === 'command') follow(j.job_id, j.title, onCommandJob);
        }
      } catch {
        /* backend not up yet */
      }
    },
    [follow, onSearchJob, onRenderJob, onCommandJob],
  );

  // Reopen the last video after a refresh or power cut.
  useEffect(() => {
    if (DEMO) return;
    let last: string | null = null;
    try {
      last = localStorage.getItem(VIDEO_KEY);
    } catch {
      last = null;
    }
    if (!last) return;
    api
      .video(last)
      .then((meta) => {
        setVideo(meta);
        void reattach(meta.video_id);
      })
      .catch(() => store(VIDEO_KEY, null));
  }, [reattach]);

  // What is in this video, for the search chips and autocomplete. They are produced with the index, so
  // while the GPU is busy the server answers 409: keep showing "Scanning…" and ask again (up to ~3 min).
  useEffect(() => {
    if (!videoId || DEMO) return;
    let alive = true;
    let timer: number | undefined;
    let tries = 0;
    setSuggestionsLoading(true);
    setSuggestions(null);
    const tick = () =>
      api
        .suggestions(videoId)
        .then((s) => {
          if (!alive) return;
          setSuggestions(s.items);
          setSuggestionsLoading(false);
        })
        .catch(() => {
          if (!alive) return;
          if (++tries < 60) timer = window.setTimeout(tick, 3000);
          else setSuggestionsLoading(false);
        });
    tick();
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [videoId]);

  // CLIP index status: poll until instant search is ready.
  useEffect(() => {
    if (!videoId || DEMO) return;
    let alive = true;
    let timer: number | undefined;
    const tick = () =>
      api
        .indexStatus(videoId)
        .then((s) => {
          if (!alive) return;
          setIndexStatus(s);
          if (s.status !== 'ready') timer = window.setTimeout(tick, 3000);
        })
        .catch(() => alive && (timer = window.setTimeout(tick, 5000)));
    tick();
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [videoId]);

  // Is the typed text an edit command? (CPU-only parse on the server, debounced.)
  useEffect(() => {
    const text = query.trim();
    if (text.length < 5 || DEMO) {
      setCommand(null);
      return;
    }
    const id = window.setTimeout(() => {
      api
        .parseCommand(text)
        .then((p) => setCommand(p.ok ? p : null))
        .catch(() => setCommand(null));
    }, 300);
    return () => window.clearTimeout(id);
  }, [query]);

  const replacePreview = useCallback((url: string | null) => {
    setPreviewUrl((old) => {
      if (old) URL.revokeObjectURL(old);
      return url;
    });
  }, []);

  const seek = (time: number) => setSeekRequest({ time, nonce: Date.now() });

  const reset = () => {
    unsubscribers.current.forEach((u) => u());
    unsubscribers.current = [];
    store(VIDEO_KEY, null);
    setVideo(null);
    setIndexStatus(null);
    setSuggestions(null);
    setSearch(null);
    setSearchJob(null);
    setSelection(null);
    replacePreview(null);
    setTargets([]);
    setRenderJob(null);
    setOutputUrl(null);
    setHiddenCount(null);
    setView('original');
    setToast(null);
    setQuery('');
  };

  const onFile = async (file: File) => {
    setUploadError(null);
    setUploadProgress(0);
    try {
      const meta = await api.uploadVideo(file, setUploadProgress);
      setVideo(meta);
      store(VIDEO_KEY, meta.video_id);
    } catch (e) {
      setUploadError((e as Error).message);
    } finally {
      setUploadProgress(null);
    }
  };

  // ---------------------------------------------------------------- actions

  const runSearch = async (q?: string) => {
    const text = (q ?? query).trim();
    if (!video || !text) return;
    setNotice(null);
    setSelection(null);
    replacePreview(null);
    try {
      const { job_id } = await api.search({
        video_id: video.video_id,
        query: text,
        frame_step: frameStep,
        conf: settings.conf,
        use_clip: useClip,
        yolo_half: settings.yoloHalf,
        mode: settings.searchMode,
      });
      follow(job_id, `Searching “${text}”`, onSearchJob);
    } catch (e) {
      setNotice((e as Error).message);
    }
  };

  const runImageSearch = async (file: File) => {
    if (!video) return;
    setNotice(null);
    setSelection(null);
    try {
      const { job_id } = await api.searchImage(video.video_id, file);
      follow(job_id, 'Searching by image', onSearchJob);
    } catch (e) {
      setNotice((e as Error).message);
    }
  };

  const runCommand = async () => {
    if (!video || !command) return;
    setNotice(null);
    setOutputUrl(null);
    try {
      const { job_id } = await api.command({
        video_id: video.video_id,
        text: query.trim(),
        frame_step: frameStep,
        conf: settings.conf,
        yolo_half: settings.yoloHalf,
      });
      follow(job_id, `“${query.trim()}”`, onCommandJob);
    } catch (e) {
      setNotice((e as Error).message);
    }
  };

  const select = (sel: Selection) => {
    setSelection(sel);
    replacePreview(null);
    setView('original');
    seek(sel.hit.time);
  };

  const currentTarget = (): Target | null =>
    selection && {
      query: selection.detection.label,
      frame_index: selection.hit.frame_index,
      box: selection.detection.box,
      effect,
      color,
      strength,
    };

  const runPreview = async () => {
    if (!video || !selection) return;
    setPreviewLoading(true);
    setNotice(null);
    try {
      replacePreview(
        await api.preview({
          video_id: video.video_id,
          frame_index: selection.hit.frame_index,
          box: selection.detection.box,
          effect,
          color,
          strength,
        }),
      );
    } catch (e) {
      setNotice((e as Error).message);
    } finally {
      setPreviewLoading(false);
    }
  };

  const render = async (list: Target[]) => {
    if (!video || !list.length) return;
    setNotice(null);
    setOutputUrl(null);
    try {
      const { job_id } = await api.recolor({
        video_id: video.video_id,
        targets: list,
        frame_step: frameStep,
        yolo_half: settings.yoloHalf,
      });
      follow(job_id, list.length > 1 ? `Editing ${list.length} objects` : 'Editing video', onRenderJob('recolor'));
    } catch (e) {
      setNotice((e as Error).message);
    }
  };

  const addToBatch = () => {
    const t = currentTarget();
    if (!t) return;
    setTargets((ts) => (ts.length >= 8 ? ts : [...ts, t]));
  };

  const runRedact = async (q: string, fx: 'blur' | 'pixelate') => {
    if (!video) return;
    setNotice(null);
    setOutputUrl(null);
    setHiddenCount(null);
    try {
      const { job_id } = await api.redact({
        video_id: video.video_id,
        query: q,
        effect: fx,
        frame_step: 3,
        conf: Math.max(0.2, settings.conf),
        yolo_half: settings.yoloHalf,
      });
      follow(job_id, `Hiding every “${q}”`, onRenderJob('redact'));
    } catch (e) {
      setNotice((e as Error).message);
    }
  };

  const thumbnails: Record<number, string> = {};
  for (const h of hits) thumbnails[h.frame_index] = h.thumbnail_url;
  if (video) {
    for (const t of targets) thumbnails[t.frame_index] ??= `/api/videos/${video.video_id}/frames/${t.frame_index}.jpg`;
  }

  return (
    <div className="min-h-screen">
      <Header
        health={health}
        video={video}
        indexStatus={indexStatus}
        onReset={reset}
        onOpenSettings={() => setSettingsOpen(true)}
        onOpenLive={() => setLiveOpen(true)}
      />
      <SettingsPanel
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        settings={settings}
        onChange={setSettings}
        device={health?.device ?? null}
      />
      {liveOpen && <LiveMode onClose={() => setLiveOpen(false)} />}

      <main className="mx-auto max-w-[1600px] px-6 py-6">
        {!video ? (
          <div className="flex min-h-[calc(100vh-8rem)] items-center justify-center">
            <UploadZone onFile={onFile} progress={uploadProgress} error={uploadError} />
          </div>
        ) : (
          <div className="space-y-6 animate-fade-up">
            {notice && (
              <div className="flex items-center gap-3 rounded-xl border border-rose-400/20 bg-rose-400/[0.06] px-4 py-2.5 text-sm text-rose-300">
                <AlertTriangle size={16} strokeWidth={1.75} />
                <span className="flex-1">{notice}</span>
                <button className="btn-icon h-7 w-7" aria-label="Dismiss" title="Dismiss" onClick={() => setNotice(null)}>
                  <X size={14} />
                </button>
              </div>
            )}
            {renderJob?.resumed && rendering && (
              <div className="flex items-center gap-2 rounded-xl border border-amber-400/20 bg-amber-400/[0.06] px-4 py-2 text-xs text-amber-200">
                <RotateCw size={14} /> The server restarted — your render is continuing from where it stopped.
              </div>
            )}

            <div className="grid gap-6 lg:grid-cols-12">
              <section className="space-y-4 lg:col-span-8">
                <SearchBar
                  value={query}
                  onChange={setQuery}
                  onSubmit={runSearch}
                  loading={searching || (rendering && renderJob?.kind === 'command')}
                  disabled={rendering}
                  useClip={useClip}
                  onUseClipChange={setUseClip}
                  suggestions={suggestions}
                  suggestionsLoading={suggestionsLoading}
                  command={command}
                  onRunCommand={runCommand}
                  translatedAs={search?.translated ? search.query_en : null}
                  extra={
                    <ImageSearchButton
                      onImage={runImageSearch}
                      disabled={searching || rendering}
                      loading={searching && searchJob?.kind === 'image_search'}
                      indexReady={indexStatus?.status === 'ready'}
                    />
                  }
                />

                {outputUrl && (
                  <div className="inline-flex rounded-xl border border-white/[0.06] bg-ink-900/70 p-1">
                    {(['original', 'result'] as const).map((v) => (
                      <button
                        key={v}
                        onClick={() => setView(v)}
                        className={cn(
                          'btn px-3 py-1.5 text-xs',
                          view === v ? 'bg-white/[0.08] text-white' : 'text-slate-400 hover:text-slate-200',
                        )}
                      >
                        {v === 'original' ? <Film size={14} /> : <Wand2 size={14} />}
                        {v === 'original' ? 'Original' : 'Edited'}
                      </button>
                    ))}
                  </div>
                )}

                {view === 'result' && outputUrl ? (
                  <VideoPlayer
                    key={outputUrl}
                    src={outputUrl}
                    meta={video}
                    hits={[]}
                    frameStep={frameStep}
                    selected={null}
                    onSelect={() => undefined}
                    seekRequest={seekRequest}
                    onTimeUpdate={setCurrentTime}
                    badge="Edited"
                    showOverlays={false}
                  />
                ) : (
                  <VideoPlayer
                    key={video.video_id}
                    src={api.streamUrl(video.video_id)}
                    meta={video}
                    hits={hits}
                    frameStep={search?.frame_step ?? frameStep}
                    selected={selection}
                    onSelect={select}
                    seekRequest={seekRequest}
                    onTimeUpdate={setCurrentTime}
                    badge={outputUrl ? 'Original' : undefined}
                  />
                )}

                <Timeline
                  meta={video}
                  hits={hits}
                  frameStep={search?.frame_step ?? frameStep}
                  currentTime={currentTime}
                  selectedFrame={selection?.hit.frame_index ?? null}
                  onSeek={seek}
                />
              </section>

              <aside className="space-y-4 lg:col-span-4">
                <FrameStepSlider value={frameStep} onChange={setFrameStep} meta={video} disabled={searching || rendering} />
                <RecolorPanel
                  meta={video}
                  selection={selection}
                  effect={effect}
                  onEffectChange={setEffect}
                  onAddToBatch={addToBatch}
                  batchCount={targets.length}
                  color={color}
                  onColorChange={setColor}
                  strength={strength}
                  onStrengthChange={setStrength}
                  previewUrl={previewUrl}
                  previewLoading={previewLoading}
                  onPreview={runPreview}
                  onApply={() => {
                    const t = currentTarget();
                    if (t) void render([t]);
                  }}
                  applying={rendering && renderKind === 'recolor'}
                  applyProgress={rendering ? renderJob?.progress ?? 0 : null}
                  outputUrl={renderKind === 'recolor' ? outputUrl : null}
                  onViewResult={() => setView('result')}
                />
                <TargetsPanel
                  targets={targets}
                  thumbnails={thumbnails}
                  meta={video}
                  onChange={(i, patch) => setTargets((ts) => ts.map((t, k) => (k === i ? { ...t, ...patch } : t)))}
                  onRemove={(i) => setTargets((ts) => ts.filter((_, k) => k !== i))}
                  onClear={() => setTargets([])}
                  onApply={() => void render(targets)}
                  applying={rendering && renderKind === 'recolor'}
                  applyProgress={rendering ? renderJob?.progress ?? 0 : null}
                />
                <PrivacyPanel
                  onRun={runRedact}
                  running={rendering && renderKind === 'redact'}
                  progress={rendering && renderKind === 'redact' ? renderJob?.progress ?? 0 : null}
                  outputUrl={renderKind === 'redact' ? outputUrl : null}
                  objectsHidden={renderKind === 'redact' ? hiddenCount : null}
                  onViewResult={() => setView('result')}
                />
              </aside>
            </div>

            <ResultsGrid
              hits={hits}
              meta={video}
              query={search?.query ?? ''}
              loading={searching}
              selected={selection}
              onSelect={select}
            />
          </div>
        )}
      </main>

      <JobProgress job={toast?.job ?? null} title={toast?.title ?? ''} onDismiss={() => setToast(null)} />
    </div>
  );
}
