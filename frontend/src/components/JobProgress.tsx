import { useEffect, useRef, useState } from 'react';
import { CheckCircle2, Clock, Loader2, X, XCircle } from 'lucide-react';
import type { Job, JobStatus } from '../types';
import { cn, formatPercent } from '../lib/format';
import { useT } from '../i18n';

export interface JobProgressProps {
  job: Job | null;
  title: string;
  onDismiss: () => void;
}

function formatElapsed(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const mins = Math.floor(s / 60);
  const secs = s % 60;
  return `${mins}:${String(secs).padStart(2, '0')}`;
}

const STATUS_CONFIG: Record<
  JobStatus,
  {
    label: string;
    pillClass: string;
    icon: (className?: string) => JSX.Element;
  }
> = {
  queued: {
    label: 'Queued',
    pillClass: 'border-slate-500/20 bg-slate-500/10 text-slate-400',
    icon: (className) => (
      <Clock size={16} strokeWidth={1.75} className={cn('text-slate-400', className)} />
    ),
  },
  running: {
    label: 'Running',
    pillClass: 'border-accent/20 bg-accent/10 text-accent',
    icon: (className) => (
      <Loader2 size={16} strokeWidth={1.75} className={cn('text-accent animate-spin', className)} />
    ),
  },
  done: {
    label: 'Done',
    pillClass: 'border-emerald-500/20 bg-emerald-500/10 text-emerald-400',
    icon: (className) => (
      <CheckCircle2 size={16} strokeWidth={1.75} className={cn('text-emerald-400', className)} />
    ),
  },
  error: {
    label: 'Error',
    pillClass: 'border-rose-500/20 bg-rose-500/10 text-rose-400',
    icon: (className) => (
      <XCircle size={16} strokeWidth={1.75} className={cn('text-rose-400', className)} />
    ),
  },
};

export function JobProgress(props: JobProgressProps) {
  const { job, title, onDismiss } = props;
  const t = useT();

  const startTimeRef = useRef<number | null>(null);
  const currentJobIdRef = useRef<string | null>(null);
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!job) {
      startTimeRef.current = null;
      currentJobIdRef.current = null;
      setElapsed(0);
      return;
    }

    if (currentJobIdRef.current !== job.job_id) {
      currentJobIdRef.current = job.job_id;
      startTimeRef.current = Date.now();
      setElapsed(0);
    }

    if (job.status !== 'queued' && job.status !== 'running') {
      if (startTimeRef.current !== null) {
        setElapsed(Math.floor((Date.now() - startTimeRef.current) / 1000));
      }
      return;
    }

    const updateElapsed = () => {
      if (startTimeRef.current !== null) {
        setElapsed(Math.floor((Date.now() - startTimeRef.current) / 1000));
      }
    };

    updateElapsed();
    const timer = setInterval(updateElapsed, 1000);
    return () => clearInterval(timer);
  }, [job?.job_id, job?.status]);

  if (!job) {
    return null;
  }

  const statusConfig = STATUS_CONFIG[job.status];
  const progressPercent = Math.round(Math.max(0, Math.min(1, job.progress)) * 100);

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed bottom-6 end-6 z-50 w-[360px] panel p-4 animate-fade-up"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          {statusConfig.icon('shrink-0')}
          <span className="truncate text-sm font-medium text-slate-100">{title}</span>
          <span
            className={cn(
              'shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider',
              statusConfig.pillClass
            )}
          >
            {t(statusConfig.label)}
          </span>
        </div>
        <button
          type="button"
          onClick={onDismiss}
          className="btn-icon h-7 w-7 shrink-0 text-slate-400 hover:text-slate-200"
          aria-label={t('Dismiss')}
          title={t('Dismiss')}
        >
          <X size={16} strokeWidth={1.75} />
        </button>
      </div>

      {(job.message || (job.status === 'error' && job.error)) && (
        <div className="mt-2 space-y-1">
          {job.message && (
            <p className="truncate text-xs text-slate-400" title={job.message}>
              {job.message}
            </p>
          )}
          {job.status === 'error' && job.error && (
            <p className="truncate text-xs text-rose-400" title={job.error}>
              {job.error}
            </p>
          )}
        </div>
      )}

      <div className="mt-3 flex items-center gap-3">
        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-ink-700" dir="ltr">
          <div
            className={cn(
              'h-full rounded-full transition-[width] duration-300',
              job.status === 'done'
                ? 'bg-emerald-400'
                : job.status === 'error'
                ? 'bg-rose-400'
                : 'bg-accent-gradient'
            )}
            style={{ width: `${progressPercent}%` }}
          />
        </div>
        <span className="num shrink-0 text-xs text-slate-400">
          {formatPercent(job.progress)}
        </span>
      </div>

      <div className="mt-2 flex items-center justify-between">
        <span className="num text-[11px] text-slate-500">
          {formatElapsed(elapsed)} {t('elapsed')}
        </span>
      </div>
    </div>
  );
}
