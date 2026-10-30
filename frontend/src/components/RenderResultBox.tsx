import { CheckCircle2, Download, Play } from 'lucide-react';

export function RenderResultBox(props: { title: string; outputUrl: string; onView: () => void }) {
  return (
    <div className="animate-fade-up space-y-3 rounded-xl border border-emerald-400/20 bg-emerald-400/[0.06] p-3">
      <div className="flex items-center gap-2 text-sm text-emerald-300">
        <CheckCircle2 size={16} strokeWidth={1.75} />
        <span className="truncate font-medium">{props.title}</span>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <button type="button" className="btn-ghost" onClick={props.onView}>
          <Play size={14} strokeWidth={1.75} />
          View
        </button>
        <a className="btn-primary" href={props.outputUrl} download>
          <Download size={14} strokeWidth={1.75} />
          Download
        </a>
      </div>
    </div>
  );
}
