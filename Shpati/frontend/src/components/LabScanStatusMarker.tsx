import { cn } from '../shared/api';

type Props = {
  interpretation?: string | null;
  className?: string;
  size?: 'sm' | 'md' | 'lg';
};

const sizeClass = {
  sm: 'h-8 w-8 text-[9px]',
  md: 'h-11 w-11 text-[10px]',
  lg: 'h-12 w-12 text-[11px]',
};

/** Clinical status marker — green = normal, red = high/low. */
export function LabScanStatusMarker({ interpretation, className, size = 'md' }: Props) {
  const key = interpretation?.toLowerCase();

  if (key === 'normal') {
    return (
      <span
        className={cn(
          'inline-flex shrink-0 items-center justify-center rounded-md bg-emerald-600 font-bold uppercase leading-tight tracking-wide text-white shadow-sm',
          sizeClass[size],
          className,
        )}
        aria-label="Within reference range: normal"
        title="Normal"
      >
        N
      </span>
    );
  }

  if (key === 'high') {
    return (
      <span
        className={cn(
          'inline-flex shrink-0 items-center justify-center rounded-md bg-rose-600 font-bold uppercase leading-tight tracking-wide text-white shadow-sm',
          sizeClass[size],
          className,
        )}
        aria-label="Above reference range: high"
        title="High"
      >
        H
      </span>
    );
  }

  if (key === 'low') {
    return (
      <span
        className={cn(
          'inline-flex shrink-0 items-center justify-center rounded-md bg-rose-600 font-bold uppercase leading-tight tracking-wide text-white shadow-sm',
          sizeClass[size],
          className,
        )}
        aria-label="Below reference range: low"
        title="Low"
      >
        L
      </span>
    );
  }

  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center justify-center rounded-md bg-slate-200 font-semibold uppercase text-slate-500',
        sizeClass[size],
        className,
      )}
      aria-label="No reference comparison"
      title="No reference range"
    >
      —
    </span>
  );
}
