import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../shared/api';
import { BatchUploader } from '../components/BatchUploader';

export function UploadPage() {
  const [, setTick] = useState(0);
  const refresh = () => setTick((v) => v + 1);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Upload</h2>
        <p className="text-sm text-slate-500">Upload a lab report PNG — OCR runs automatically.</p>
      </div>
      <BatchUploader onComplete={refresh} />
    </div>
  );
}

export function AuditQueuePage() {
  const [reports, setReports] = useState<any[]>([]);

  useEffect(() => {
    api<any>('/api/reports').then((data) => setReports(data.reports ?? []));
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">All Reports</h2>
        <p className="text-sm text-slate-500">Every uploaded report and its OCR line count.</p>
      </div>

      <ul className="divide-y divide-slate-100 rounded-2xl border border-slate-200 bg-white p-5">
        {reports.map((report) => (
          <li key={report.id} className="flex items-center justify-between py-3 text-sm">
            <div>
              <p className="font-medium">{report.title}</p>
              <p className="text-xs text-slate-500">
                {report.ocr_lines ?? 0} OCR lines · {report.status}
              </p>
            </div>
            <Link
              to={`/reports/${report.id}`}
              className="rounded-lg bg-teal-600 px-3 py-1.5 text-xs font-semibold text-white"
            >
              Open
            </Link>
          </li>
        ))}
        {!reports.length && <li className="py-3 text-xs text-slate-400">No reports yet.</li>}
      </ul>
    </div>
  );
}
