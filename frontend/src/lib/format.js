// Number, duration and date helpers. Dates are handled as 'YYYY-MM-DD' strings
// and only turned into Date objects (local time) for display, so no timezone
// shift can move a day.

const NUM_LOCALE = 'en-IN';
const DATE_LOCALE = 'en-GB';
export const DASH = '—';

export function fmtNum(value, decimals = 2) {
  if (value == null || Number.isNaN(value)) return DASH;
  const v = Math.abs(value) < 0.5 * 10 ** -decimals ? 0 : value; // no "-0.00"
  return v.toLocaleString(NUM_LOCALE, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/** Up to `max` decimals, trailing zeros dropped (for headline figures and sums). */
export function fmtTrim(value, max = 2) {
  if (value == null || Number.isNaN(value)) return DASH;
  return value.toLocaleString(NUM_LOCALE, { maximumFractionDigits: max });
}

/** Decimal hours as h:mm, e.g. 399.9 -> "399:54". */
export function fmtHours(hours) {
  if (hours == null || Number.isNaN(hours)) return DASH;
  const total = Math.round(Math.abs(hours) * 60);
  const sign = hours < 0 && total > 0 ? '-' : '';
  return `${sign}${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
}

/** Format a value by the kind used in the performance report. */
export function fmtByKind(value, kind, decimals = 2) {
  if (kind === 'hours') return fmtHours(value);
  if (kind === 'count') return fmtNum(value, 0);
  return fmtNum(value, decimals);
}

/**
 * Parse what a person typed. Returns { ok, value } with value null for blank.
 * kind 'hours' accepts "h:mm", "h:mm:ss" or decimal hours.
 */
export function parseInput(text, kind = 'number') {
  const s = String(text ?? '').trim().replace(/,/g, '');
  if (s === '') return { ok: true, value: null };
  if (kind === 'text') return { ok: true, value: s };
  if (kind === 'hours' && s.includes(':')) {
    const parts = s.split(':');
    if (parts.length > 3 || !parts.every((p) => /^\d+$/.test(p))) return { ok: false };
    const [h, m = 0, sec = 0] = parts.map(Number);
    if (m >= 60 || sec >= 60) return { ok: false };
    return { ok: true, value: Math.round((h + m / 60 + sec / 3600) * 1e6) / 1e6 };
  }
  if (!/^-?(\d+\.?\d*|\.\d+)$/.test(s)) return { ok: false };
  return { ok: true, value: Number(s) };
}

/** A stored value as the text to put in an input box. */
export function toInputText(value, kind = 'number') {
  if (value == null) return '';
  if (kind === 'hours') return fmtHours(value);
  if (kind === 'text') return String(value);
  return String(Math.round(value * 1e6) / 1e6);
}

/** Number printed on the report page (string) -> number, or null. */
export function printedNumber(text) {
  if (text == null) return null;
  const s = String(text).trim().replace(/,/g, '').replace(/%/g, '');
  if (s.includes(':')) {
    const r = parseInput(s, 'hours');
    return r.ok ? r.value : null;
  }
  if (!/^-?(\d+\.?\d*|\.\d+)$/.test(s)) return null;
  return Number(s);
}

/** Decimal places of a printed number string ("7.16" -> 2). */
export function printedDecimals(text) {
  const m = String(text ?? '').match(/\.(\d+)/);
  return m ? m[1].length : 0;
}

// ---- dates ---------------------------------------------------------------------------

export function parseIso(iso) {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d || 1);
}

export function toIso(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

export function localTodayIso() {
  return toIso(new Date());
}

export function addDays(iso, delta) {
  const d = parseIso(iso);
  d.setDate(d.getDate() + delta);
  return toIso(d);
}

export function isIsoDate(s) {
  return typeof s === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(s) && !Number.isNaN(parseIso(s).getTime());
}

export function isMonth(s) {
  return typeof s === 'string' && /^\d{4}-(0[1-9]|1[0-2])$/.test(s);
}

const DATE_STYLES = {
  long: { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' },
  medium: { day: 'numeric', month: 'short', year: 'numeric' },
  short: { day: 'numeric', month: 'short' },
  weekday: { weekday: 'short', day: 'numeric', month: 'short' },
  weekdayYear: { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' },
};

export function fmtDate(iso, style = 'medium') {
  if (!iso) return DASH;
  return parseIso(iso).toLocaleDateString(DATE_LOCALE, DATE_STYLES[style]);
}

export function fmtDateTime(timestamp) {
  if (!timestamp) return DASH;
  const d = new Date(timestamp);
  if (Number.isNaN(d.getTime())) return DASH;
  return d.toLocaleString(DATE_LOCALE, {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

export function monthLabel(ym, style = 'long') {
  return parseIso(`${ym}-01`).toLocaleDateString(DATE_LOCALE, {
    month: style,
    year: 'numeric',
  });
}

export function daysInMonth(ym) {
  const [y, m] = ym.split('-').map(Number);
  return new Date(y, m, 0).getDate();
}

export function monthDays(ym) {
  return Array.from({ length: daysInMonth(ym) }, (_, i) => `${ym}-${String(i + 1).padStart(2, '0')}`);
}

/** Days as "5, 6, 7 and 9 Nov" (grouped per month). */
export function fmtDayList(isoList) {
  if (!isoList?.length) return '';
  const groups = [];
  for (const iso of [...isoList].sort()) {
    const ym = iso.slice(0, 7);
    const last = groups[groups.length - 1];
    if (last && last.ym === ym) last.days.push(Number(iso.slice(8)));
    else groups.push({ ym, days: [Number(iso.slice(8))] });
  }
  return groups
    .map(({ ym, days }) => {
      const month = parseIso(`${ym}-01`).toLocaleDateString(DATE_LOCALE, { month: 'short' });
      const list = days.length > 1 ? `${days.slice(0, -1).join(', ')} and ${days[days.length - 1]}` : `${days[0]}`;
      return `${list} ${month}`;
    })
    .join('; ');
}

// ---- fiscal year (April to March) -------------------------------------------------

export function fyOfMonth(ym) {
  const [y, m] = ym.split('-').map(Number);
  return m >= 4 ? y : y - 1;
}

export function fyLabel(fy) {
  return `FY ${fy}–${String(fy + 1).slice(2)}`;
}

export function fyMonths(fy) {
  return Array.from({ length: 12 }, (_, i) => {
    const d = new Date(fy, 3 + i, 1);
    return {
      value: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`,
      label: d.toLocaleDateString(DATE_LOCALE, { month: 'short' }),
    };
  });
}
