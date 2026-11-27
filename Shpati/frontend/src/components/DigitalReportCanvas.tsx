import { useEffect, useMemo, useRef, useState } from 'react';
import type { OcrLine } from './OcrObservationsList';
import { ZoomControls, clampZoom } from './ZoomControls';

type ViewMode = 'overlay' | 'digital' | 'original';

type Props = {
  imageUrl: string;
  lines: OcrLine[];
  pageWidth: number;
  pageHeight: number;
  defaultViewMode?: ViewMode;
  heading?: string;
  description?: string;
};

export function DigitalReportCanvas({
  imageUrl,
  lines,
  pageWidth,
  pageHeight,
  defaultViewMode = 'overlay',
  heading = 'Digital Lab Report',
  description,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [fitScale, setFitScale] = useState(1);
  const [zoom, setZoom] = useState(1);
  const [viewMode, setViewMode] = useState<ViewMode>(defaultViewMode);

  useEffect(() => {
    const el = containerRef.current;
    if (!el || !pageWidth) return;

    const update = () => {
      const available = el.clientWidth - 16;
      setFitScale(Math.min(1, available / pageWidth));
    };

    update();
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => observer.disconnect();
  }, [pageWidth]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const onWheel = (event: WheelEvent) => {
      if (!(event.ctrlKey || event.metaKey)) return;
      event.preventDefault();
      const direction = event.deltaY > 0 ? -0.1 : 0.1;
      setZoom((current) => clampZoom(current + direction));
    };

    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, []);

  const scale = fitScale * zoom;
  const displayWidth = pageWidth * scale;
  const displayHeight = pageHeight * scale;

  const sortedLines = useMemo(
    () => [...lines].sort((a, b) => a.y_min - b.y_min || a.x_min - b.x_min),
    [lines],
  );

  return (
    <section aria-labelledby="digital-report-heading" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id="digital-report-heading" className="text-lg font-bold text-slate-900">
            {heading}
          </h2>
          <p className="text-base text-slate-600">
            {description ??
              `${lines.length} OCR segments positioned to match the original document layout.`}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <ZoomControls zoom={zoom} onChange={setZoom} />
          <div className="flex flex-wrap gap-2" role="group" aria-label="View mode">
            {(
              [
                ['overlay', 'Overlay'],
                ['digital', 'Text only'],
                ['original', 'Original scan'],
              ] as const
            ).map(([mode, label]) => (
              <button
                key={mode}
                type="button"
                onClick={() => setViewMode(mode)}
                aria-pressed={viewMode === mode}
                className={`min-h-[44px] rounded-lg px-3 py-2 text-sm font-semibold ${
                  viewMode === mode
                    ? 'bg-teal-700 text-white'
                    : 'border border-slate-300 bg-white text-slate-800 hover:bg-slate-50'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <p className="no-print text-xs text-slate-500">Tip: Ctrl/⌘ + scroll to zoom · drag scrollbars to pan</p>

      <div
        ref={containerRef}
        className="max-h-[75vh] overflow-auto rounded-2xl border-2 border-slate-200 bg-slate-100 p-2"
      >
        <div
          className="relative mx-auto shadow-md"
          style={{ width: displayWidth, height: displayHeight, background: '#ffffff' }}
        >
          {(viewMode === 'overlay' || viewMode === 'original') && (
            <img
              src={imageUrl}
              alt="Original lab report scan"
              width={displayWidth}
              height={displayHeight}
              className="absolute inset-0 h-full w-full object-fill"
              draggable={false}
            />
          )}

          {viewMode !== 'original' &&
            sortedLines.map((line) => {
              const left = line.x_min * scale;
              const top = line.y_min * scale;
              const width = Math.max(1, (line.x_max - line.x_min) * scale);
              const height = Math.max(1, (line.y_max - line.y_min) * scale);
              const fontSize = Math.max(7, height * 0.82);

              return (
                <span
                  key={line.id}
                  title={`${line.text} (${(line.confidence * 100).toFixed(1)}%)`}
                  className={
                    viewMode === 'overlay'
                      ? 'absolute overflow-hidden bg-white/75 text-slate-900'
                      : 'absolute overflow-hidden border border-slate-200/80 bg-white text-slate-900'
                  }
                  style={{
                    left,
                    top,
                    width,
                    height,
                    fontSize,
                    lineHeight: `${height}px`,
                    whiteSpace: 'nowrap',
                  }}
                >
                  {line.text}
                </span>
              );
            })}
        </div>
      </div>
    </section>
  );
}
