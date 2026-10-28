# VisionQuery design system

Aesthetic: a professional dark "studio" tool in the spirit of DaVinci Resolve, Runway and Linear:
calm, dense, precise, with one confident accent. No playful illustrations, no emoji in the UI.

## Stack rules
- React 18 + TypeScript (strict) + Tailwind CSS 3. Function components with **named exports**.
- Allowed libraries only: `react`, `lucide-react` (icons, `size={16}` `strokeWidth={1.75}` unless noted),
  `react-colorful`, `clsx` (via `cn()` from `src/lib/format.ts`). Nothing else: no framer-motion, no UI kits.
- Import shared types from `../types` and helpers from `../lib/format` / `../lib/geometry`.
- Components are presentational: no fetch calls; everything comes in through props and goes out through callbacks.

## Tokens (tailwind.config.js)
- Background `bg-ink-950`; surfaces `bg-ink-900/70`, `bg-ink-850`, `bg-ink-800`; borders `border-white/[0.06]`
  (hover `border-white/[0.14]`).
- Accent `accent` (#7c5cff, violet) and `signal` (#22d3ee, cyan). Gradient `bg-accent-gradient`.
- Text: `text-slate-100` primary, `text-slate-400` secondary, `text-slate-500` tertiary.
- Success `emerald-400`, warning `amber-400`, error `rose-400`.
- Shadows `shadow-panel`, `shadow-glow` (accent), `shadow-glow-signal` (selection).
- Radius: panels `rounded-2xl`, controls `rounded-xl`, chips `rounded-full`.

## Component classes (src/index.css)
`.panel` `.panel-header` `.label` `.btn-primary` `.btn-ghost` `.btn-icon` `.input` `.chip` `.kbd` `.num`
`.range` `.skeleton`, plus `animate-fade-up` and `animate-shimmer`. Prefer these over re-inventing styles.

## Conventions
- Numbers, timestamps and scores use `.num` (mono, tabular).
- Section titles use `.label` (11px uppercase, tracked).
- Detection boxes: normal = violet (`#a593ff`, 1.5px), hovered = brighter, **selected = cyan `#22d3ee` 2.5px with a soft glow**.
  Labels sit on a small filled tag above the box: `label 87%`.
- Score colour scale: < 0.4 slate, 0.4–0.7 accent, > 0.7 signal.
- Transitions `duration-150`; focus states `focus-visible:ring-2 ring-accent/60`. Every icon-only button has `aria-label` and `title`.
- Loading: skeletons, never bare "Loading..." text. Empty states: muted icon + one line title + one line hint.
- Responsive: must work from 1024 px up; graceful single column below `lg`.
