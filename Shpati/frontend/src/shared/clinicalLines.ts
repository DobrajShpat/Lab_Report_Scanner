import type { ClinicalReport, ClinicalRow } from '../components/ClinicalReportView';
import type { OcrLine } from '../components/OcrObservationsList';

export function clinicalTextKeys(report: ClinicalReport | null): Set<string> {
  const keys = new Set<string>();
  if (!report) return keys;
  report.ocr_text?.lines?.forEach((line) => keys.add(line.trim()));
  report.rows.forEach((row) => {
    if (row.ocr_source_text) keys.add(row.ocr_source_text.trim());
  });
  return keys;
}

export function filterClinicalOcrLines(ocrLines: OcrLine[], report: ClinicalReport | null): OcrLine[] {
  const keys = clinicalTextKeys(report);
  if (!keys.size) return [];
  return ocrLines.filter((line) => keys.has(line.text.trim()));
}

export function clinicalRowByText(report: ClinicalReport | null): Map<string, ClinicalRow> {
  const map = new Map<string, ClinicalRow>();
  if (!report) return map;
  report.rows.forEach((row) => {
    if (row.ocr_source_text) map.set(row.ocr_source_text.trim(), row);
  });
  return map;
}
