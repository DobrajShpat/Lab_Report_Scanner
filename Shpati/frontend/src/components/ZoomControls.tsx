import { Minus, Plus, RotateCcw } from 'lucide-react';

type Props = {
  zoom: number;
  onChange: (next: number) => void;
  min?: number;
  max?: number;
  step?: number;
  label?: string;
};

export function clampZoom(value: number, min = 0.5, max = 3) {
  return Math.min(max, Math.max(min, Math.round(value * 100) / 100));
}

export function ZoomControls({
  zoom,
  onChange,
  min = 0.5,
  max = 3,
  step = 0.25,
  label = 'Zoom',
}: Props) {
  const set = (next: number) => onChange(clampZoom(next, min, max));

  return (
    <div className="no-print flex items-center gap-1 rounded-xl border border-slate-200 bg-white p-1" role="group" aria-label={label}>
      <button
        type="button"
        onClick={() => set(zoom - step)}
        disabled={zoom <= min}
        className="inline-flex min-h-[40px] min-w-[40px] items-center justify-center rounded-lg text-slate-700 hover:bg-slate-50 disabled:opacity-40"
        aria-label="Zoom out"
        title="Zoom out"
      >
        <Minus className="h-4 w-4" aria-hidden />
      </button>
      <span className="min-w-[3.5rem] text-center text-sm font-semibold tabular-nums text-slate-800" aria-live="polite">
        {Math.round(zoom * 100)}%
      </span>
      <button
        type="button"
        onClick={() => set(zoom + step)}
        disabled={zoom >= max}
        className="inline-flex min-h-[40px] min-w-[40px] items-center justify-center rounded-lg text-slate-700 hover:bg-slate-50 disabled:opacity-40"
        aria-label="Zoom in"
        title="Zoom in"
      >
        <Plus className="h-4 w-4" aria-hidden />
      </button>
      <button
        type="button"
        onClick={() => set(1)}
        disabled={zoom === 1}
        className="inline-flex min-h-[40px] min-w-[40px] items-center justify-center rounded-lg text-slate-700 hover:bg-slate-50 disabled:opacity-40"
        aria-label="Reset zoom"
        title="Reset zoom"
      >
        <RotateCcw className="h-4 w-4" aria-hidden />
      </button>
    </div>
  );
}
