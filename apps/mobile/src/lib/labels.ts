import type { LabeledValue } from './types';

/** Kodun Türkçe adını döndürür; sözlükte yoksa kodun kendisini gösterir (boş ekran yerine). */
export function labelOf(values: LabeledValue[], code: string | null | undefined): string {
  if (!code) return '';
  return values.find((item) => item.code === code)?.label ?? code;
}
