import { useCallback, useEffect, useRef, useState } from 'react';
import { AlertTriangle, Film, Wand2, X } from 'lucide-react';
import { api, watchJob } from './api/client';
import { FrameStepSlider } from './components/FrameStepSlider';
import { Header } from './components/Header';
import { JobProgress } from './components/JobProgress';
import { RecolorPanel } from './components/RecolorPanel';
import { ResultsGrid } from './components/ResultsGrid';
import { SearchBar } from './components/SearchBar';
import { Timeline } from './components/Timeline';
import { UploadZone } from './components/UploadZone';
import { VideoPlayer } from './components/VideoPlayer';
import { DEMO, demoHealth, demoSearch, demoSuggestions, demoVideo } from './demo';
import { cn } from './lib/format';
import type { Health, Job, RecolorResult, SearchResult, Selection, Suggestion, VideoMeta } from './types';

type View = 'original' | 'result';

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [video, setVideo] = useState<VideoMeta | null>(null);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const [suggestions, setSuggestions] = useState<Suggestion[] | null>(null);
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);
  const [query, setQuery] = useState('');
  const [useClip, setUseClip] = useState(true);
  const [frameStep, setFrameStep] = useState(5);
  const [searchJob, setSearchJob] = useState<Job | null>(null);
  const [search, setSearch] = useState<SearchResult | null>(null);

  const [selection, setSelection] = useState<Selection | null>(null);
  const [color, setColor] = useState('#3b82f6');
  const [strength, setStrength] = useState(0.85);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [recolorJob, setRecolorJob] = useState<Job | null>(null);
  const [outputUrl, setOutputUrl] = useState<string | null>(null);

  const [view, setView] = useState<View>('original');
  const [currentTime, setCurrentTime] = useState(0);
  const [seekRequest, setSeekRequest] = useState<{ time: number; nonce: number } | null>(null);
  const [toast, setToast] = useState<{ job: Job; title: string } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const unsubscribers = useRef<Array<() => void>>([]);

  // GPU / model status in the header.
  useEffect(() => {
    let alive = true;
    if (DEMO) return;
    const tick = () => api.health().then((h) => alive && setHealth(h)).catch(() => undefined);
    tick();
    const id = window.setInterval(tick, 8000);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, []);

  useEffect(() => () => unsubscribers.current.forEach((u) => u()), []);

  useEffect(() => {
    if (!DEMO) return;
    setHealth(demoHealth);
    setVideo(demoVideo);
    setSuggestions(demoSuggestions);
    setSearch(demoSearch());
  }, []);

  // What is in this video, for the search chips and autocomplete.
  const videoId = video?.video_id;
  useEffect(() => {
    if (!videoId || DEMO) return;
    let alive = true;
    setSuggestionsLoading(true);
    api
      .suggestions(videoId)
      .then((s) => alive && setSuggestions(s.items))
      .catch(() => alive && setSuggestions(null))
      .finally(() => alive && setSuggestionsLoading(false));
    return () => {
      alive = false;
    };
  }, [videoId]);

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
    setVideo(null);
    setSuggestions(null);
    setSearch(null);
    setSearchJob(null);
    setSelection(null);
    replacePreview(null);
    setRecolorJob(null);
    setOutputUrl(null);
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
    } catch (e) {
      setUploadError((e as Error).message);
    } finally {
      setUploadProgress(null);
    }
  };

  const follow = (jobId: string, title: string, onJob: (job: Job) => void) => {
    const unsub = watchJob(jobId, (job) => {
      onJob(job);
      setToast({ job, title });
    });
    unsubscribers.current.push(unsub);
  };

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
        conf: 0.15,
        use_clip: useClip,
      });
      follow(job_id, `Searching “${text}”`, (job) => {
        setSearchJob(job);
        if (job.status === 'done') setSearch(job.result as SearchResult);
      });
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

  const runRecolor = async () => {
    if (!video || !selection) return;
    setNotice(null);
    setOutputUrl(null);
    try {
      const { job_id } = await api.recolor({
        video_id: video.video_id,
        query: selection.detection.label,
        frame_index: selection.hit.frame_index,
        box: selection.detection.box,
        color,
        strength,
        frame_step: frameStep,
      });
      follow(job_id, 'Recoloring video', (job) => {
        setRecolorJob(job);
        if (job.status === 'done') {
          setOutputUrl((job.result as RecolorResult).output_url);
          setView('result');
        }
      });
    } catch (e) {
      setNotice((e as Error).message);
    }
  };

  const searching = searchJob?.status === 'queued' || searchJob?.status === 'running';
  const applying = recolorJob?.status === 'queued' || recolorJob?.status === 'running';
  const hits = search?.hits ?? [];

  return (
    <div className="min-h-screen">
      <Header health={health} video={video} onReset={reset} />

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

            <div className="grid gap-6 lg:grid-cols-12">
              <section className="space-y-4 lg:col-span-8">
                <SearchBar
                  value={query}
                  onChange={setQuery}
                  onSubmit={runSearch}
                  loading={searching}
                  disabled={applying}
                  useClip={useClip}
                  onUseClipChange={setUseClip}
                  suggestions={suggestions}
                  suggestionsLoading={suggestionsLoading}
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
                        {v === 'original' ? 'Original' : 'Recolored'}
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
                    badge="Recolored"
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
                <FrameStepSlider value={frameStep} onChange={setFrameStep} meta={video} disabled={searching || applying} />
                <RecolorPanel
                  meta={video}
                  selection={selection}
                  color={color}
                  onColorChange={setColor}
                  strength={strength}
                  onStrengthChange={setStrength}
                  previewUrl={previewUrl}
                  previewLoading={previewLoading}
                  onPreview={runPreview}
                  onApply={runRecolor}
                  applying={applying}
                  applyProgress={applying ? recolorJob?.progress ?? 0 : null}
                  outputUrl={outputUrl}
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
