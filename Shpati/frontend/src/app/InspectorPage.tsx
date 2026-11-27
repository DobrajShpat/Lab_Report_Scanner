import { useEffect, useMemo, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, RefreshCw } from 'lucide-react';
import { api } from '../shared/api';
import { LabResultsTable } from '../components/LabResultsTable';
import { OcrReportView } from '../components/OcrReportView';
import { type OcrLine } from '../components/OcrObservationsList';
import { TreeJsonViewer } from '../components/TreeJsonViewer';

type Tab = 'results' | 'ocr' | 'raw';

export function InspectorPage() {
  const { reportId } = useParams<{ reportId: string }>();
  const [tab, setTab] = useState<Tab>('results');
  const [detail, setDetail] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [reprocessing, setReprocessing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    if (!reportId) return;
    setLoading(true);
    setError(null);
    api(`/api/reports/${reportId}`)
      .then(setDetail)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load'))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, [reportId]);

  const reprocess = async () => {
    if (!reportId) return;
    setReprocessing(true);
    setError(null);
    try {
      await api(`/api/reports/${reportId}/process`, { method: 'POST' });
      const next = await api(`/api/reports/${reportId}`);
      setDetail(next);
      setTab('results');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Reprocess failed');
    } finally {
      setReprocessing(false);
    }
  };

  const ocrLines: OcrLine[] = useMemo(() => {
    const raw = detail?.digital_report?.lines ?? detail?.ocr?.lines ?? [];
    return raw.map((line: any, index: number) => ({
      id: index,
      text: line.text ?? '',
      confidence: Number(line.confidence ?? 0),
      x_min: Number(line.x_min ?? 0),
      y_min: Number(line.y_min ?? 0),
      x_max: Number(line.x_max ?? 0),
      y_max: Number(line.y_max ?? 0),
      bbox: line.bbox,
    }));
  }, [detail]);

  const pageWidth = Number(detail?.digital_report?.page_width ?? 0);
  const pageHeight = Number(detail?.digital_report?.page_height ?? 0);

  if (loading) return <p className="text-base text-slate-700">Loading report…</p>;
  if (!detail) return <p className="text-base text-rose-700">{error ?? 'Report not found.'}</p>;

  const imageUrl = detail.assets.original_image_url;
  const summary = detail.summary;
  const clinicalReport = detail.clinical_report ?? null;

  const tabs: { key: Tab; label: string }[] = [
    { key: 'results', label: 'Lab Results' },
    { key: 'ocr', label: 'OCR Text' },
    { key: 'raw', label: 'Raw JSON' },
  ];

  return (
    <div className="flex min-h-[calc(100vh-3rem)] flex-col gap-5">
      <div className="no-print flex flex-wrap items-center gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
        <Link
          to="/"
          className="rounded-lg border border-slate-200 p-2.5 text-slate-700 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700"
          aria-label="Back to dashboard"
        >
          <ArrowLeft className="h-5 w-5" aria-hidden />
        </Link>
        <div className="min-w-0 flex-1">
          <h1 className="font-display truncate text-2xl font-bold text-slate-900">{summary.title}</h1>
          <p className="truncate text-sm text-slate-500">{summary.id}</p>
        </div>
        <button
          type="button"
          onClick={reprocess}
          disabled={reprocessing}
          className="inline-flex min-h-[44px] items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60"
        >
          <RefreshCw className={`h-4 w-4 ${reprocessing ? 'animate-spin' : ''}`} aria-hidden />
          {reprocessing ? 'Reprocessing…' : 'Reprocess'}
        </button>
        <nav className="flex flex-wrap gap-1.5 rounded-xl bg-slate-100 p-1" aria-label="Report views">
          {tabs.map(({ key, label }) => (
            <button
              key={key}
              type="button"
              onClick={() => setTab(key)}
              aria-current={tab === key ? 'page' : undefined}
              className={`min-h-[40px] rounded-lg px-4 py-2 text-sm font-semibold transition ${
                tab === key
                  ? 'bg-white text-teal-900 shadow-sm'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              {label}
            </button>
          ))}
        </nav>
      </div>

      {error && (
        <p className="no-print rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">{error}</p>
      )}

      {tab === 'results' && (
        <LabResultsTable
          report={clinicalReport}
          onReprocess={reprocess}
          reprocessing={reprocessing}
          reportTitle={summary.title}
          imageUrl={imageUrl}
        />
      )}

      {tab === 'ocr' && (
        <OcrReportView
          imageUrl={imageUrl}
          ocrLines={ocrLines}
          pageWidth={pageWidth}
          pageHeight={pageHeight}
          lineCount={summary.ocr_lines}
          selectedVariant={summary.selected_variant}
        />
      )}

      {tab === 'raw' && (
        <div className="no-print grid gap-3">
          <TreeJsonViewer title="clinical_report.json" data={detail.clinical_report ?? {}} />
          <TreeJsonViewer title="ocr.json" data={detail.ocr ?? {}} />
          <TreeJsonViewer title="digital_report.json" data={detail.digital_report ?? {}} />
        </div>
      )}
    </div>
  );
}
