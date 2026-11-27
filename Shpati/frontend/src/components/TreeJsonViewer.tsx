import { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';

type Props = {
  title: string;
  data: unknown;
};

function Node({ label, value, depth = 0 }: { label: string; value: unknown; depth?: number }) {
  const [open, setOpen] = useState(depth < 1);

  if (value === null || typeof value !== 'object') {
    return (
      <div className="flex gap-2 py-0.5 text-xs" style={{ paddingLeft: depth * 12 }}>
        <span className="font-medium text-slate-600">{label}:</span>
        <span className="text-slate-800">{String(value)}</span>
      </div>
    );
  }

  const entries = Array.isArray(value)
    ? value.map((item, index) => [String(index), item] as const)
    : Object.entries(value as Record<string, unknown>);

  return (
    <div style={{ paddingLeft: depth * 12 }}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1 py-1 text-xs font-semibold text-slate-700"
      >
        {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        {label}
        <span className="font-normal text-slate-400">({entries.length})</span>
      </button>
      {open &&
        entries.map(([key, child]) => <Node key={key} label={key} value={child} depth={depth + 1} />)}
    </div>
  );
}

export function TreeJsonViewer({ title, data }: Props) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3">
      <h4 className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-500">{title}</h4>
      <div className="max-h-80 overflow-auto font-mono">
        <Node label="root" value={data} />
      </div>
    </div>
  );
}
