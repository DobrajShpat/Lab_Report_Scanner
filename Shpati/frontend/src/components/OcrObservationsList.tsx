import { memo, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { OcrLineThumbnail, type OcrBBoxLine } from './OcrLineThumbnail';
import { cn } from '../shared/api';

export type OcrLine = OcrBBoxLine & { id: number };

type Props = {
  imageUrl: string;
  lines: OcrLine[];
  heading?: string;
  description?: string;
  renderTrailing?: (line: OcrLine) => ReactNode;
  emptyLabel?: string;
};

const ROW_HEIGHT = 72;

function confidenceTone(confidence: number) {
  const pct = confidence * 100;
  if (pct >= 90) return 'text-emerald-800 bg-emerald-100 border-emerald-300';
  if (pct >= 70) return 'text-amber-900 bg-amber-100 border-amber-300';
  return 'text-rose-900 bg-rose-100 border-rose-300';
}

function formatConfidence(confidence: number) {
  return `${(confidence * 100).toFixed(1)}%`;
}

const OcrObservationRow = memo(function OcrObservationRow({
  line,
  imageUrl,
  index,
  renderTrailing,
}: {
  line: OcrLine;
  imageUrl: string;
  index: number;
  renderTrailing?: (line: OcrLine) => ReactNode;
}) {
  return (
    <div
      className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white px-3 py-2.5"
      role="listitem"
    >
      <span className="w-8 shrink-0 text-center text-sm font-semibold text-slate-500" aria-hidden="true">
        {index + 1}
      </span>
      <OcrLineThumbnail imageUrl={imageUrl} line={line} alt={`Region for: ${line.text}`} size={48} />
      <div className="min-w-0 flex-1">
        <p className="text-base font-medium text-slate-900">{line.text || '(empty)'}</p>
        <span
          className={cn(
            'mt-1 inline-flex rounded-md border px-2 py-0.5 text-sm font-semibold',
            confidenceTone(line.confidence),
          )}
        >
          {formatConfidence(line.confidence)}
        </span>
      </div>
      {renderTrailing?.(line)}
    </div>
  );
});

export function OcrObservationsList({
  imageUrl,
  lines,
  heading = 'Raw OCR Observations',
  description = 'Every text segment the OCR engine detected — unedited, in reading order.',
  renderTrailing,
  emptyLabel = 'No OCR data for this report.',
}: Props) {
  const listRef = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportHeight, setViewportHeight] = useState(400);

  const sorted = useMemo(
    () => [...lines].sort((a, b) => a.y_min - b.y_min || a.x_min - b.x_min),
    [lines],
  );

  const onScroll = () => {
    const el = listRef.current;
    if (!el) return;
    setScrollTop(el.scrollTop);
    setViewportHeight(el.clientHeight);
  };

  useEffect(() => {
    const el = listRef.current;
    if (!el) return;
    onScroll();
    const observer = new ResizeObserver(onScroll);
    observer.observe(el);
    return () => observer.disconnect();
  }, [lines.length]);

  const virtual = useMemo(() => {
    const total = sorted.length;
    const start = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - 2);
    const visible = Math.ceil(viewportHeight / ROW_HEIGHT) + 4;
    const end = Math.min(total, start + visible);
    return {
      topSpacer: start * ROW_HEIGHT,
      bottomSpacer: Math.max(0, (total - end) * ROW_HEIGHT),
      slice: sorted.slice(start, end),
      start,
    };
  }, [sorted, scrollTop, viewportHeight]);

  return (
    <section aria-labelledby="ocr-observations-heading" className="flex min-h-0 flex-col gap-3">
      <header>
        <h2 id="ocr-observations-heading" className="text-lg font-bold text-slate-900">
          {heading}
        </h2>
        <p className="text-base text-slate-600">{description}</p>
      </header>

      <div
        ref={listRef}
        onScroll={onScroll}
        className="max-h-[420px] min-h-[200px] overflow-y-auto rounded-2xl border border-slate-200 bg-slate-50/60 p-2"
        role="list"
        aria-label={heading}
      >
        <div style={{ height: virtual.topSpacer }} aria-hidden />
        <div className="space-y-2">
          {virtual.slice.map((line, i) => (
            <OcrObservationRow
              key={line.id}
              line={line}
              imageUrl={imageUrl}
              index={virtual.start + i}
              renderTrailing={renderTrailing}
            />
          ))}
        </div>
        <div style={{ height: virtual.bottomSpacer }} aria-hidden />
        {!sorted.length && <p className="py-8 text-center text-base text-slate-600">{emptyLabel}</p>}
      </div>
    </section>
  );
}
