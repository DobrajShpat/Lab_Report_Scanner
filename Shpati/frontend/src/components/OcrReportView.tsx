import { useMemo } from 'react';
import { DigitalReportCanvas } from './DigitalReportCanvas';
import { OcrObservationsList, type OcrLine } from './OcrObservationsList';

type Props = {
  imageUrl: string;
  ocrLines: OcrLine[];
  pageWidth: number;
  pageHeight: number;
  lineCount?: number;
  selectedVariant?: string | null;
};

export function OcrReportView({ imageUrl, ocrLines, pageWidth, pageHeight, lineCount, selectedVariant }: Props) {
  const plainText = useMemo(
    () =>
      [...ocrLines]
        .sort((a, b) => a.y_min - b.y_min || a.x_min - b.x_min)
        .map((line) => line.text)
        .join('\n'),
    [ocrLines],
  );

  if (!ocrLines.length) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center">
        <p className="text-base text-slate-600">No OCR data for this report yet.</p>
        <p className="mt-2 text-sm text-slate-500">Upload or reprocess the report to run OCR.</p>
      </div>
    );
  }

  const count = lineCount ?? ocrLines.length;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-3 rounded-2xl border border-slate-200 bg-white px-5 py-4 text-sm">
        <span className="rounded-full bg-slate-100 px-3 py-1 font-medium text-slate-800">
          {count} OCR segments
        </span>
        {selectedVariant && (
          <span className="rounded-full bg-teal-100 px-3 py-1 font-medium text-teal-900">
            variant: {selectedVariant}
          </span>
        )}
      </div>

      <div className="flex flex-col gap-6 lg:grid lg:grid-cols-[1.2fr_0.8fr] lg:gap-4">
        <DigitalReportCanvas
          imageUrl={imageUrl}
          lines={ocrLines}
          pageWidth={pageWidth || 800}
          pageHeight={pageHeight || 1100}
          defaultViewMode="digital"
          heading="OCR Report"
          description={`${count} text segments detected by OCR — positioned to match the original scan.`}
        />
        <OcrObservationsList
          imageUrl={imageUrl}
          lines={ocrLines}
          heading="OCR Text"
          description="Every text segment the OCR engine detected — unedited, in reading order."
        />
      </div>

      <section className="rounded-2xl border border-slate-200 bg-white px-5 py-4">
        <h3 className="text-sm font-bold uppercase tracking-wide text-slate-600">Plain text</h3>
        <pre className="mt-2 max-h-64 overflow-auto rounded-lg bg-slate-50 p-3 font-mono text-xs whitespace-pre-wrap text-slate-800">
          {plainText}
        </pre>
      </section>
    </div>
  );
}
