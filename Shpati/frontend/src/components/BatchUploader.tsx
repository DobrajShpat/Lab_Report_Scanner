import { useCallback, useState } from 'react';
import { Upload } from 'lucide-react';
import { useAuth } from '../shared/auth';

const STAGES = [
  'Ingestion',
  'Preprocess',
  'OCR Engine',
  'Digital Reproduction',
  'Complete Extraction',
];

type FileJob = {
  file: File;
  status: 'queued' | 'processing' | 'done' | 'failed';
  stage: string;
  reportId?: string;
  error?: string;
};

type Props = {
  onComplete?: () => void;
};

export function BatchUploader({ onComplete }: Props) {
  const { user, authHeaders } = useAuth();
  const [jobs, setJobs] = useState<FileJob[]>([]);
  const [dragging, setDragging] = useState(false);

  const processFile = useCallback(
    async (file: File) => {
      if (!user) {
        setJobs((current) =>
          current.map((job) =>
            job.file === file
              ? { ...job, status: 'failed', error: 'Sign in from the sidebar to upload reports.' }
              : job,
          ),
        );
        return;
      }
      setJobs((current) =>
        current.map((job) =>
          job.file === file ? { ...job, status: 'processing', stage: STAGES[0] } : job,
        ),
      );

      const body = new FormData();
      body.append('file', file);

      let stageIndex = 0;
      const ticker = window.setInterval(() => {
        stageIndex = Math.min(stageIndex + 1, STAGES.length - 1);
        setJobs((current) =>
          current.map((job) => (job.file === file ? { ...job, stage: STAGES[stageIndex] } : job)),
        );
      }, 900);

      try {
        const response = await fetch('/api/reports/upload', {
          method: 'POST',
          headers: authHeaders(),
          body,
        });
        window.clearInterval(ticker);
        if (!response.ok) throw new Error(await response.text());
        const data = await response.json();

        setJobs((current) =>
          current.map((job) =>
            job.file === file
              ? { ...job, status: 'done', stage: 'Done', reportId: data.report_id }
              : job,
          ),
        );
        onComplete?.();
      } catch (error) {
        window.clearInterval(ticker);
        setJobs((current) =>
          current.map((job) =>
            job.file === file
              ? {
                  ...job,
                  status: 'failed',
                  error: error instanceof Error ? error.message : 'Failed',
                }
              : job,
          ),
        );
      }
    },
    [onComplete, user, authHeaders],
  );

  const addFiles = useCallback(
    (list: FileList | File[]) => {
      const incoming = Array.from(list).slice(0, 50);
      const newJobs: FileJob[] = incoming.map((file) => ({
        file,
        status: 'queued',
        stage: 'Queued',
      }));
      setJobs((current) => [...current, ...newJobs].slice(0, 50));
      newJobs.forEach((job) => processFile(job.file));
    },
    [processFile],
  );

  return (
    <div className="space-y-4">
      {!user && (
        <p className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          Sign in using the panel in the sidebar before uploading (demo: <strong>demo</strong> / <strong>demo123</strong>).
        </p>
      )}

      <label
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
        }}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-14 transition ${
          dragging ? 'border-teal-500 bg-teal-50/50' : 'border-slate-300 bg-white hover:border-teal-400'
        }`}
      >
        <Upload className="mb-3 h-8 w-8 text-teal-600" />
        <p className="text-sm font-semibold text-slate-800">Drop up to 50 lab reports (PNG, JPG, PDF)</p>
        <p className="mt-1 text-xs text-slate-500">or click to browse</p>
        <input
          type="file"
          multiple
          accept=".png,.jpg,.jpeg,.pdf,.tif,.tiff"
          className="hidden"
          onChange={(e) => e.target.files && addFiles(e.target.files)}
        />
      </label>

      {jobs.length > 0 && (
        <ul className="space-y-2 rounded-2xl border border-slate-200 bg-white p-4">
          {jobs.map((job) => (
            <li key={`${job.file.name}-${job.file.size}`} className="rounded-xl bg-slate-50 px-4 py-3">
              <div className="flex items-center justify-between gap-3">
                <span className="truncate text-sm font-medium">{job.file.name}</span>
                <span
                  className={`text-xs font-semibold uppercase ${
                    job.status === 'done'
                      ? 'text-emerald-600'
                      : job.status === 'failed'
                        ? 'text-rose-600'
                        : 'text-teal-600'
                  }`}
                >
                  {job.status}
                </span>
              </div>
              <p className="mt-1 text-xs text-slate-500">[{job.stage}]</p>
              {job.status === 'processing' && (
                <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-200">
                  <div className="h-full w-2/3 animate-pulse rounded-full bg-teal-500" />
                </div>
              )}
              {job.error && <p className="mt-1 text-xs text-rose-600">{job.error}</p>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
