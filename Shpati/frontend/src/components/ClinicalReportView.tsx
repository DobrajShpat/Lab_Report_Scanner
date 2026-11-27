import { useMemo } from 'react';
import { DigitalReportCanvas } from './DigitalReportCanvas';
import { LabScanStatusMarker } from './LabScanStatusMarker';
import { OcrObservationsList, type OcrLine } from './OcrObservationsList';
import { clinicalRowByText, filterClinicalOcrLines } from '../shared/clinicalLines';

export type ClinicalRow = {
  row_id?: string;
  test_name: string;
  value: string | number | null;
  unit?: string | null;
  reference_range?: string | null;
  interpretation?: 'normal' | 'high' | 'low' | string | null;
  section?: string | null;
  loinc_code?: string | null;
  ocr_source_text?: string | null;
};

export type ClinicalReport = {
  generated_at?: string;
  summary?: {
    total: number;
    normal: number;
    high: number;
    low: number;
    unclassified: number;
  };
  rows: ClinicalRow[];
  sections?: Record<string, ClinicalRow[]>;
  ocr_text?: {
    line_count: number;
    lines: string[];
    text: string;
  };
};

type Props = {
  report: ClinicalReport | null;
  imageUrl: string;
  ocrLines: OcrLine[];
  pageWidth: number;
  pageHeight: number;
};

export function ClinicalReportView({ report, imageUrl, ocrLines, pageWidth, pageHeight }: Props) {
  const clinicalLines = useMemo(() => filterClinicalOcrLines(ocrLines, report), [ocrLines, report]);
  const rowByText = useMemo(() => clinicalRowByText(report), [report]);
  const summary = report?.summary;

  if (!report?.rows?.length) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center">
        <p className="text-base text-slate-600">No clinical results available for this report yet.</p>
        <p className="mt-2 text-sm text-slate-500">Reprocess the report if it was uploaded before clinical extraction was enabled.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {summary && (
        <div className="flex flex-wrap gap-3 rounded-2xl border border-slate-200 bg-white px-5 py-4 text-sm">
          <span className="rounded-full bg-slate-100 px-3 py-1 font-medium text-slate-800">
            {summary.total} lab results
          </span>
          <span className="rounded-full bg-emerald-100 px-3 py-1 font-medium text-emerald-900">
            {summary.normal} normal
          </span>
          <span className="rounded-full bg-rose-100 px-3 py-1 font-medium text-rose-900">
            {summary.high} high · {summary.low} low
          </span>
        </div>
      )}

      <div className="flex flex-col gap-6 lg:grid lg:grid-cols-[1.2fr_0.8fr] lg:gap-4">
        <DigitalReportCanvas
          imageUrl={imageUrl}
          lines={clinicalLines}
          pageWidth={pageWidth || 800}
          pageHeight={pageHeight || 1100}
          defaultViewMode="digital"
          heading="Clinical Lab Report"
          description={`${clinicalLines.length} OCR text segments for lab results only — positioned like the original scan.`}
        />
        <OcrObservationsList
          imageUrl={imageUrl}
          lines={clinicalLines}
          heading="OCR Text (lab results only)"
          description="Detected OCR text for parsed lab rows — headers, billing, and hospital metadata excluded."
          emptyLabel="No clinical OCR lines matched. Reprocess this report to refresh."
          renderTrailing={(line) => {
            const row = rowByText.get(line.text.trim());
            if (!row?.interpretation) return null;
            return <LabScanStatusMarker interpretation={row.interpretation} className="h-9 w-9 text-[9px]" />;
          }}
        />
      </div>

      {report.ocr_text?.text && (
        <section className="rounded-2xl border border-slate-200 bg-white px-5 py-4">
          <h3 className="text-sm font-bold uppercase tracking-wide text-slate-600">Plain OCR excerpt</h3>
          <pre className="mt-2 max-h-48 overflow-auto rounded-lg bg-slate-50 p-3 font-mono text-xs whitespace-pre-wrap text-slate-800">
            {report.ocr_text.text}
          </pre>
        </section>
      )}
    </div>
  );
}
