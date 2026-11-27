import { useMemo, useState } from 'react';
import { ArrowDown, ArrowUp, AlertTriangle } from 'lucide-react';
import { LabScanStatusMarker } from './LabScanStatusMarker';
import { ZoomControls } from './ZoomControls';
import { cn } from '../shared/api';

export type ClinicalRow = {
  row_id?: string;
  test_name: string;
  value: string | number | null;
  unit?: string | null;
  reference_range?: string | null;
  interpretation?: 'normal' | 'high' | 'low' | string | null;
  section?: string | null;
  result_type?: string | null;
  ocr_source_text?: string | null;
  parse_status?: string | null;
};

export type ClinicalReport = {
  generated_at?: string;
  engine?: string;
  summary?: {
    total: number;
    normal: number;
    high: number;
    low: number;
    unclassified: number;
    needs_review?: number;
    review_lines?: number;
    ocr_lines?: number;
    coverage?: number;
  };
  rows: ClinicalRow[];
  sections?: Record<string, ClinicalRow[]>;
  review_lines?: Array<{ text: string; confidence: number; reason?: string }>;
};

type Props = {
  report: ClinicalReport | null;
  onReprocess?: () => void;
  reprocessing?: boolean;
  reportTitle?: string;
  imageUrl?: string | null;
};

function formatValue(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === '') return '—';
  return String(value);
}

function statusKey(interpretation?: string | null) {
  return interpretation?.toLowerCase() ?? null;
}

function isAbnormal(interpretation?: string | null) {
  const key = statusKey(interpretation);
  return key === 'high' || key === 'low';
}

function sortForReading(rows: ClinicalRow[]) {
  // Abnormal first so doctors see flags immediately — display-only, no backend change
  const rank = (row: ClinicalRow) => {
    const key = statusKey(row.interpretation);
    if (key === 'high' || key === 'low') return 0;
    if (key === 'normal') return 1;
    return 2;
  };
  return [...rows].sort((a, b) => rank(a) - rank(b));
}

function FlagBadge({ interpretation }: { interpretation?: string | null }) {
  const key = statusKey(interpretation);

  if (key === 'normal') {
    return (
      <span className="inline-flex items-center gap-1 rounded-md bg-emerald-100 px-2.5 py-1 text-xs font-bold uppercase tracking-wide text-emerald-800">
        Normal
      </span>
    );
  }
  if (key === 'high') {
    return (
      <span className="inline-flex items-center gap-1 rounded-md bg-rose-100 px-2.5 py-1 text-xs font-bold uppercase tracking-wide text-rose-700">
        <ArrowUp className="h-3.5 w-3.5" aria-hidden />
        High
      </span>
    );
  }
  if (key === 'low') {
    return (
      <span className="inline-flex items-center gap-1 rounded-md bg-rose-100 px-2.5 py-1 text-xs font-bold uppercase tracking-wide text-rose-700">
        <ArrowDown className="h-3.5 w-3.5" aria-hidden />
        Low
      </span>
    );
  }
  return (
    <span className="inline-flex items-center rounded-md bg-slate-100 px-2.5 py-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
      No range
    </span>
  );
}

function ResultValue({ row }: { row: ClinicalRow }) {
  const key = statusKey(row.interpretation);
  return (
    <span
      className={cn(
        'font-mono text-xl font-bold tabular-nums tracking-tight',
        key === 'normal' && 'text-emerald-700',
        (key === 'high' || key === 'low') && 'text-rose-600',
        !key && 'text-slate-900',
      )}
    >
      {formatValue(row.value)}
      {row.unit ? (
        <span className="ml-1.5 text-sm font-semibold text-slate-500">{row.unit}</span>
      ) : null}
      {key === 'high' && <ArrowUp className="ml-1 inline h-4 w-4 align-[-2px]" aria-hidden />}
      {key === 'low' && <ArrowDown className="ml-1 inline h-4 w-4 align-[-2px]" aria-hidden />}
    </span>
  );
}

export function LabResultsTable({ report, onReprocess, reprocessing, reportTitle, imageUrl }: Props) {
  const [reportZoom, setReportZoom] = useState(1);
  const [scanZoom, setScanZoom] = useState(1);
  const [showScan, setShowScan] = useState(Boolean(imageUrl));

  const abnormalRows = useMemo(
    () => (report?.rows ?? []).filter((row) => isAbnormal(row.interpretation)),
    [report],
  );

  const sectionEntries = useMemo(() => {
    if (!report?.rows?.length) return [] as Array<[string, ClinicalRow[]]>;
    const entries = report.sections
      ? Object.entries(report.sections)
      : [['Results', report.rows] as [string, ClinicalRow[]]];
    return entries.map(([name, rows]) => [name, sortForReading(rows)] as [string, ClinicalRow[]]);
  }, [report]);

  if (!report?.rows?.length) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white px-8 py-12 text-center shadow-sm">
        <p className="font-display text-2xl font-semibold text-slate-900">No lab results yet</p>
        <p className="mt-2 text-base text-slate-600">
          Reprocess this report to extract analytes and flag high / low / normal values.
        </p>
        {onReprocess && (
          <button
            type="button"
            onClick={onReprocess}
            disabled={reprocessing}
            className="mt-6 rounded-xl bg-teal-700 px-5 py-2.5 text-sm font-semibold text-white disabled:opacity-60"
          >
            {reprocessing ? 'Reprocessing…' : 'Reprocess report'}
          </button>
        )}
      </div>
    );
  }

  const summary = report.summary;
  const abnormalCount = (summary?.high ?? 0) + (summary?.low ?? 0);

  return (
    <div className="space-y-5">
      {/* Clinical summary strip */}
      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-100 bg-gradient-to-r from-slate-50 via-white to-emerald-50/40 px-6 py-5">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-teal-800">Clinical laboratory report</p>
          <h2 className="font-display mt-1 text-3xl font-bold tracking-tight text-slate-900">
            {reportTitle ?? 'Lab Results'}
          </h2>
          <p className="mt-2 max-w-2xl text-base text-slate-600">
            Values outside the reference range are highlighted in{' '}
            <span className="font-semibold text-rose-600">red</span>. Values within range are shown in{' '}
            <span className="font-semibold text-emerald-700">green</span>.
          </p>
        </div>

        {summary && (
          <div className="grid gap-3 border-b border-slate-100 px-6 py-4 sm:grid-cols-4">
            <div className="rounded-xl bg-slate-50 px-4 py-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Total tests</p>
              <p className="mt-1 text-3xl font-bold tabular-nums text-slate-900">{summary.total}</p>
            </div>
            <div className="rounded-xl bg-emerald-50 px-4 py-3 ring-1 ring-emerald-100">
              <p className="text-xs font-semibold uppercase tracking-wide text-emerald-800">Normal</p>
              <p className="mt-1 text-3xl font-bold tabular-nums text-emerald-700">{summary.normal}</p>
            </div>
            <div className="rounded-xl bg-rose-50 px-4 py-3 ring-1 ring-rose-100">
              <p className="text-xs font-semibold uppercase tracking-wide text-rose-800">High</p>
              <p className="mt-1 text-3xl font-bold tabular-nums text-rose-600">{summary.high}</p>
            </div>
            <div className="rounded-xl bg-rose-50 px-4 py-3 ring-1 ring-rose-100">
              <p className="text-xs font-semibold uppercase tracking-wide text-rose-800">Low</p>
              <p className="mt-1 text-3xl font-bold tabular-nums text-rose-600">{summary.low}</p>
            </div>
          </div>
        )}

        {/* Legend */}
        <div className="flex flex-wrap items-center gap-4 px-6 py-3 text-sm text-slate-600">
          <span className="font-semibold text-slate-800">Legend</span>
          <span className="inline-flex items-center gap-2">
            <LabScanStatusMarker interpretation="normal" size="sm" />
            <span>Normal (green)</span>
          </span>
          <span className="inline-flex items-center gap-2">
            <LabScanStatusMarker interpretation="high" size="sm" />
            <span>High (red)</span>
          </span>
          <span className="inline-flex items-center gap-2">
            <LabScanStatusMarker interpretation="low" size="sm" />
            <span>Low (red)</span>
          </span>
        </div>
      </div>

      {/* Abnormal findings first — doctors scan this immediately */}
      {abnormalCount > 0 && (
        <section
          className="overflow-hidden rounded-2xl border-2 border-rose-200 bg-rose-50/70 shadow-sm"
          aria-labelledby="abnormal-heading"
        >
          <div className="flex items-start gap-3 border-b border-rose-200 px-5 py-4">
            <div className="mt-0.5 rounded-lg bg-rose-600 p-2 text-white">
              <AlertTriangle className="h-5 w-5" aria-hidden />
            </div>
            <div>
              <h3 id="abnormal-heading" className="font-display text-xl font-bold text-rose-900">
                Out-of-range findings
              </h3>
              <p className="mt-0.5 text-sm text-rose-800">
                {abnormalCount} result{abnormalCount === 1 ? '' : 's'} outside the reference range — review first.
              </p>
            </div>
          </div>
          <ul className="divide-y divide-rose-100 bg-white/80">
            {abnormalRows.map((row, index) => (
              <li
                key={row.row_id ?? `abn-${index}`}
                className="flex flex-wrap items-center justify-between gap-3 border-l-4 border-l-rose-500 px-5 py-3.5"
              >
                <div className="min-w-0">
                  <p className="text-base font-semibold text-slate-900">{row.test_name}</p>
                  <p className="mt-0.5 text-sm text-slate-500">
                    Reference: {row.reference_range ?? '—'}
                    {row.unit ? ` · ${row.unit}` : ''}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <ResultValue row={row} />
                  <FlagBadge interpretation={row.interpretation} />
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Full panel tables */}
      <div className="no-print flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="font-display text-lg font-bold text-slate-900">Digitized report</h3>
          <p className="text-sm text-slate-500">Zoom the clinical table for easier reading</p>
        </div>
        <ZoomControls zoom={reportZoom} onChange={setReportZoom} label="Report zoom" />
      </div>

      <article
        className="print-report overflow-auto rounded-2xl border border-slate-200 bg-white shadow-sm"
        style={{ zoom: reportZoom }}
      >
        {sectionEntries.map(([sectionName, rows]) => (
          <section key={sectionName} className="border-b border-slate-100 last:border-b-0">
            <div className="flex items-center justify-between gap-3 bg-slate-50/80 px-5 py-3 md:px-6">
              <h3 className="font-display text-lg font-bold text-slate-900">{sectionName}</h3>
              <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
                {rows.filter((r) => isAbnormal(r.interpretation)).length} flagged · {rows.length} tests
              </p>
            </div>

            {/* Mobile */}
            <div className="grid gap-3 p-4 sm:hidden">
              {rows.map((row, index) => {
                const abnormal = isAbnormal(row.interpretation);
                const normal = statusKey(row.interpretation) === 'normal';
                return (
                  <div
                    key={row.row_id ?? `${sectionName}-m-${index}`}
                    className={cn(
                      'rounded-2xl border p-4',
                      abnormal && 'border-rose-200 bg-rose-50/50 border-l-4 border-l-rose-500',
                      normal && 'border-emerald-100 bg-emerald-50/30 border-l-4 border-l-emerald-500',
                      !abnormal && !normal && 'border-slate-200 bg-white border-l-4 border-l-slate-300',
                    )}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <p className="text-base font-semibold text-slate-900">{row.test_name}</p>
                      <LabScanStatusMarker interpretation={row.interpretation} size="sm" />
                    </div>
                    <div className="mt-3 flex items-end justify-between gap-3">
                      <div>
                        <ResultValue row={row} />
                        <p className="mt-1 text-sm text-slate-500">{row.unit ?? '—'}</p>
                      </div>
                      <FlagBadge interpretation={row.interpretation} />
                    </div>
                    <p className="mt-3 text-sm text-slate-600">
                      <span className="font-medium text-slate-500">Ref range:</span> {row.reference_range ?? '—'}
                    </p>
                  </div>
                );
              })}
            </div>

            {/* Desktop table */}
            <div className="hidden overflow-x-auto sm:block">
              <table className="w-full min-w-[760px] border-collapse text-left">
                <thead>
                  <tr className="border-b border-slate-200 text-[11px] font-bold uppercase tracking-[0.08em] text-slate-500">
                    <th className="w-14 px-5 py-3" scope="col">
                      Flag
                    </th>
                    <th className="px-3 py-3" scope="col">
                      Test
                    </th>
                    <th className="px-3 py-3" scope="col">
                      Result
                    </th>
                    <th className="px-3 py-3" scope="col">
                      Unit
                    </th>
                    <th className="px-3 py-3" scope="col">
                      Reference range
                    </th>
                    <th className="px-5 py-3" scope="col">
                      Status
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, index) => {
                    const abnormal = isAbnormal(row.interpretation);
                    const normal = statusKey(row.interpretation) === 'normal';
                    return (
                      <tr
                        key={row.row_id ?? `${sectionName}-${index}`}
                        className={cn(
                          'border-b border-slate-100 transition-colors',
                          abnormal && 'bg-rose-50/70',
                          normal && 'bg-emerald-50/25',
                        )}
                      >
                        <td
                          className={cn(
                            'px-5 py-3.5 align-middle',
                            abnormal && 'border-l-4 border-l-rose-500',
                            normal && 'border-l-4 border-l-emerald-500',
                            !abnormal && !normal && 'border-l-4 border-l-transparent',
                          )}
                        >
                          <LabScanStatusMarker interpretation={row.interpretation} size="sm" />
                        </td>
                        <td className="px-3 py-3.5 align-middle text-base font-semibold text-slate-900">
                          {row.test_name}
                        </td>
                        <td className="px-3 py-3.5 align-middle">
                          <ResultValue row={row} />
                        </td>
                        <td className="px-3 py-3.5 align-middle text-sm text-slate-600">{row.unit ?? '—'}</td>
                        <td className="px-3 py-3.5 align-middle font-mono text-sm tabular-nums text-slate-600">
                          {row.reference_range ?? '—'}
                        </td>
                        <td className="px-5 py-3.5 align-middle">
                          <FlagBadge interpretation={row.interpretation} />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        ))}
      </article>

      {imageUrl && (
        <section className="no-print space-y-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="font-display text-lg font-bold text-slate-900">Original scan</h3>
              <p className="text-sm text-slate-500">Zoom and pan the uploaded report image</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => setShowScan((v) => !v)}
                className="min-h-[40px] rounded-lg border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
              >
                {showScan ? 'Hide scan' : 'Show scan'}
              </button>
              {showScan && <ZoomControls zoom={scanZoom} onChange={setScanZoom} label="Scan zoom" />}
            </div>
          </div>
          {showScan && (
            <div className="max-h-[75vh] overflow-auto rounded-xl border border-slate-200 bg-slate-100 p-2">
              <img
                src={imageUrl}
                alt="Original uploaded lab report scan"
                className="mx-auto block h-auto max-w-none origin-top"
                style={{ width: `${Math.round(scanZoom * 100)}%` }}
                draggable={false}
              />
            </div>
          )}
        </section>
      )}

      {!!report.review_lines?.length && (
        <details className="no-print rounded-2xl border border-amber-200 bg-amber-50/50 open:shadow-sm">
          <summary className="cursor-pointer list-none px-5 py-4 text-sm font-semibold text-amber-950">
            Technical OCR notes ({report.review_lines.length} unmerged fragments)
          </summary>
          <ul className="max-h-40 space-y-1 overflow-auto border-t border-amber-200 px-5 py-3 font-mono text-xs text-amber-950">
            {report.review_lines.map((line, i) => (
              <li key={`${line.text}-${i}`}>• {line.text}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
