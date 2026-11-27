import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Activity, FileText, Clock } from 'lucide-react';
import { DeleteReportButton } from '../components/DeleteReportButton';
import { api } from '../shared/api';

export function DashboardPage() {
  const [stats, setStats] = useState<any>(null);

  const load = useCallback(() => {
    api('/api/reports').then(setStats);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const cards = [
    {
      label: 'Total Reports',
      value: stats?.total_reports ?? 0,
      icon: Activity,
      tone: 'text-teal-600 bg-teal-50',
    },
    {
      label: 'OCR Lines Detected',
      value: stats?.total_ocr_lines ?? 0,
      icon: FileText,
      tone: 'text-emerald-600 bg-emerald-50',
    },
    {
      label: 'Pending OCR',
      value: stats?.pending_reports ?? 0,
      icon: Clock,
      tone: 'text-amber-600 bg-amber-50',
    },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-slate-900">Dashboard</h2>
        <p className="text-sm text-slate-500">Upload lab reports and inspect everything OCR detected.</p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {cards.map(({ label, value, icon: Icon, tone }) => (
          <div key={label} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className={`mb-3 inline-flex rounded-xl p-2 ${tone}`}>
              <Icon className="h-5 w-5" />
            </div>
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</p>
            <p className="mt-1 text-3xl font-bold text-slate-900">{value}</p>
          </div>
        ))}
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-5">
        <h3 className="text-sm font-bold text-slate-800">Recent Reports</h3>
        <ul className="mt-3 divide-y divide-slate-100">
          {(stats?.reports ?? []).slice(0, 8).map((report: any) => (
            <li key={report.id} className="flex flex-wrap items-center justify-between gap-3 py-3 text-sm">
              <div className="min-w-0">
                <p className="font-medium text-slate-900">{report.title}</p>
                <p className="text-xs text-slate-500">
                  {report.lab_results ?? 0} lab results · {report.ocr_lines ?? 0} OCR lines · {report.status}
                  {(report.high > 0 || report.low > 0) && (
                    <span className="ml-1 text-rose-600">
                      ({report.high ?? 0}H / {report.low ?? 0}L)
                    </span>
                  )}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Link
                  to={`/reports/${report.id}`}
                  className="rounded-lg bg-teal-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-teal-700"
                >
                  Open
                </Link>
                <DeleteReportButton
                  reportId={report.id}
                  reportTitle={report.title}
                  onDeleted={load}
                  compact
                />
              </div>
            </li>
          ))}
          {!stats?.reports?.length && <li className="py-4 text-sm text-slate-400">No reports yet.</li>}
        </ul>
      </div>
    </div>
  );
}
