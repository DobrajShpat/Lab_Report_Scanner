import { useState } from 'react';
import { Trash2 } from 'lucide-react';
import { deleteReport } from '../shared/api';
import { useAuth } from '../shared/auth';

type Props = {
  reportId: string;
  reportTitle?: string;
  onDeleted?: () => void;
  redirectTo?: string;
  compact?: boolean;
};

export function DeleteReportButton({ reportId, reportTitle, onDeleted, redirectTo, compact }: Props) {
  const { user } = useAuth();
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!user) return null;

  const handleDelete = async () => {
    setBusy(true);
    setError(null);
    try {
      await deleteReport(reportId);
      setConfirming(false);
      onDeleted?.();
      if (redirectTo) {
        window.location.href = redirectTo;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed');
    } finally {
      setBusy(false);
    }
  };

  if (confirming) {
    return (
      <div className={`flex flex-col gap-2 ${compact ? '' : 'rounded-xl border border-rose-200 bg-rose-50 p-3'}`}>
        <p className="text-sm text-slate-800">
          Delete <strong>{reportTitle ?? reportId}</strong>? This cannot be undone.
        </p>
        {error && <p className="text-xs text-rose-700">{error}</p>}
        <div className="flex gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={handleDelete}
            className="rounded-lg bg-rose-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-rose-700 disabled:opacity-60"
          >
            {busy ? 'Deleting…' : 'Confirm delete'}
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => {
              setConfirming(false);
              setError(null);
            }}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700"
          >
            Cancel
          </button>
        </div>
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={() => setConfirming(true)}
      className="inline-flex items-center gap-1.5 rounded-lg border border-rose-200 bg-white px-3 py-1.5 text-xs font-semibold text-rose-700 hover:bg-rose-50"
      aria-label={`Delete report ${reportTitle ?? reportId}`}
    >
      <Trash2 className="h-3.5 w-3.5" aria-hidden />
      Delete
    </button>
  );
}
