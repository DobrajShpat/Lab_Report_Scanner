import { useState } from 'react';
import { api } from '../shared/api';

type Observation = {
  row_id: string;
  raw_test_name: string;
  value_text?: string | null;
  standardized_value?: number | null;
  value?: number | null;
  standardized_unit?: string;
  original_unit?: string;
  reference_range_text?: string;
  acceptance_decision: 'accepted' | 'needs_review' | 'rejected';
};

type Props = {
  reportId: string;
  observations: Observation[];
  onUpdated: () => void;
};

function displayValue(row: Observation) {
  if (row.value_text) return row.value_text;
  if (row.standardized_value != null) return String(row.standardized_value);
  if (row.value != null) return String(row.value);
  return '—';
}

export function InteractiveWorkbench({ reportId, observations, onUpdated }: Props) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [rows, setRows] = useState(observations);
  const [busy, setBusy] = useState(false);

  const ensureSession = async () => {
    if (sessionId) return sessionId;
    const data = await api<{ session_id: string }>('/api/review/session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ report_id: reportId }),
    });
    setSessionId(data.session_id);
    return data.session_id;
  };

  const apply = async (rowId: string, action: string, corrections?: Record<string, string>) => {
    setBusy(true);
    try {
      const sid = await ensureSession();
      await api('/api/review/apply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sid, row_id: rowId, action, corrections }),
      });
      setRows((current) =>
        current.map((row) =>
          row.row_id === rowId
            ? {
                ...row,
                acceptance_decision:
                  action === 'approve' || action === 'edit_and_approve'
                    ? 'accepted'
                    : action === 'reject'
                      ? 'rejected'
                      : row.acceptance_decision,
              }
            : row,
        ),
      );
      onUpdated();
    } finally {
      setBusy(false);
    }
  };

  const reviewRows = rows.filter((r) => r.acceptance_decision === 'needs_review');

  if (!reviewRows.length) {
    return (
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-xs uppercase text-slate-500">
            <th className="py-2">Test</th>
            <th>Value</th>
            <th>Unit</th>
            <th>Range</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.row_id} className="border-b border-slate-100">
              <td className="py-2 font-medium">{row.raw_test_name}</td>
              <td>{displayValue(row)}</td>
              <td>{row.standardized_unit ?? row.original_unit ?? '—'}</td>
              <td>{row.reference_range_text ?? '—'}</td>
              <td className="capitalize text-emerald-600">{row.acceptance_decision.replace('_', ' ')}</td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }

  return (
    <div className="space-y-3">
      {reviewRows.map((row) => (
        <div key={row.row_id} className="rounded-xl border border-amber-200 bg-amber-50/60 p-4">
          <p className="text-sm font-semibold text-slate-900">{row.raw_test_name}</p>
          <div className="mt-3 grid grid-cols-3 gap-2">
            <input
              defaultValue={displayValue(row) === '—' ? '' : String(displayValue(row))}
              id={`value-${row.row_id}`}
              className="rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
              placeholder="Value"
            />
            <input
              defaultValue={row.standardized_unit ?? row.original_unit ?? ''}
              id={`unit-${row.row_id}`}
              className="rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
              placeholder="Unit"
            />
            <input
              defaultValue={row.reference_range_text ?? ''}
              id={`range-${row.row_id}`}
              className="rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
              placeholder="Reference range"
            />
          </div>
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              disabled={busy}
              onClick={() => apply(row.row_id, 'approve')}
              className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white"
            >
              Approve
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                const standardized_value = (
                  document.getElementById(`value-${row.row_id}`) as HTMLInputElement
                ).value;
                const standardized_unit = (document.getElementById(`unit-${row.row_id}`) as HTMLInputElement)
                  .value;
                const reference_range_text = (
                  document.getElementById(`range-${row.row_id}`) as HTMLInputElement
                ).value;
                apply(row.row_id, 'edit_and_approve', {
                  standardized_value,
                  standardized_unit,
                  reference_range_text,
                });
              }}
              className="rounded-lg bg-teal-600 px-3 py-1.5 text-xs font-semibold text-white"
            >
              Modify
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => apply(row.row_id, 'reject')}
              className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-semibold text-slate-700"
            >
              Exclude
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
