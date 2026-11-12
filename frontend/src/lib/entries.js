// Small helpers for stored day entries.

export function hasGeneration(entry) {
  return !!entry && (entry.u1Gen != null || entry.u2Gen != null);
}

/**
 * report | workbook | manual (has generation), partial (some values, no
 * generation), none, future. Today without data counts as future: its page
 * only comes out tomorrow morning.
 */
export function dayStatus(entry, iso, today) {
  if (iso > today || (iso === today && !entry)) return 'future';
  if (!entry) return 'none';
  if (!hasGeneration(entry)) return 'partial';
  return entry.source || 'manual';
}

export const STATUS_TEXT = {
  report: 'Read from the uploaded page',
  workbook: 'Imported from the workbook',
  manual: 'Entered by hand',
  partial: 'Some values, no generation',
  none: 'No data',
  future: 'Not yet',
};

/** a + b, or null when both are missing. */
export function add(...values) {
  return values.every((v) => v == null) ? null : values.reduce((s, v) => s + (v ?? 0), 0);
}
