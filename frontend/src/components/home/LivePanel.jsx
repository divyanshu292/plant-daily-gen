import { useEffect, useState } from 'react';
import { LightningIcon } from '@phosphor-icons/react';
import { apiFetch } from '@/lib/api';
import { MicroLabel } from '@/components/common/Text';
import { fmtNum } from '@/lib/format';
import { cn } from '@/lib/utils';

const POLL_MS = 2_000;
const FETCH_TIMEOUT_MS = 8_000;
export const UNIT_MW = 210;
const STATION_MW = UNIT_MW * 2;
// The SCADA feed stamps its own readings; older than this and they are not "live".
const FEED_LATE_MS = 30 * 60 * 1000;

const IST_CLOCK = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Asia/Kolkata',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
});
const IST_DAY = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Kolkata', day: 'numeric', month: 'short' });
const MONTHS = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'];

/** "12-Nov-2026 20:55" (IST) -> epoch ms, or null. */
function parseFeedTime(text) {
  const m = /^(\d{1,2})-([A-Za-z]{3})-(\d{4})\s+(\d{1,2}):(\d{2})/.exec(String(text || '').trim());
  if (!m) return null;
  const month = MONTHS.indexOf(m[2].toLowerCase());
  if (month < 0) return null;
  return Date.UTC(+m[3], month, +m[1], +m[4], +m[5]) - 330 * 60 * 1000;
}

function pickUnit(list, n) {
  if (!Array.isArray(list)) return null;
  const re = new RegExp(`unit[\\s-]*${n}\\b`, 'i');
  return list.find((r) => re.test(r?.station || '')) || list[n - 1] || null;
}

function powerOf(reading) {
  const v = reading?.readings?.power;
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

/** Poll the live feed every 2 s. On failure the last readings stay, flagged stale. */
function useLiveFeed() {
  const [state, setState] = useState({ list: null, ok: null });
  useEffect(() => {
    let cancelled = false;
    let busy = false;
    const load = async () => {
      if (busy || document.hidden) return;
      busy = true;
      // A hung request must not stall the poll (and leave old figures marked live).
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), FETCH_TIMEOUT_MS);
      try {
        const res = await apiFetch('/live-generation', { signal: ctrl.signal });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = await res.json();
        if (!Array.isArray(json)) throw new Error('Unexpected live feed');
        if (!cancelled) setState({ list: json, ok: true });
      } catch {
        if (!cancelled) setState((s) => (s.ok === false ? s : { ...s, ok: false }));
      } finally {
        clearTimeout(timer);
        busy = false;
      }
    };
    load();
    const id = setInterval(load, POLL_MS);
    const onVisible = () => !document.hidden && load();
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      cancelled = true;
      clearInterval(id);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, []);
  return state;
}

function useNow() {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  return now;
}

export function LivePanel() {
  const { list, ok } = useLiveFeed();
  const now = useNow();
  const u1 = powerOf(pickUnit(list, 1));
  const u2 = powerOf(pickUnit(list, 2));
  const total = u1 != null && u2 != null ? u1 + u2 : null;
  const stamp = pickUnit(list, 1)?.timestamp || pickUnit(list, 2)?.timestamp;
  const feedAt = parseFeedTime(stamp);
  const late = feedAt != null && now - feedAt > FEED_LATE_MS;

  const state = ok === null ? 'connecting' : ok === false ? (list ? 'stale' : 'offline') : late ? 'late' : 'live';
  const dim = state === 'stale' || state === 'offline';

  let feedText = stamp || '';
  if (feedAt != null) {
    const sameDay = IST_DAY.format(new Date(feedAt)) === IST_DAY.format(new Date(now));
    feedText = `${sameDay ? '' : `${IST_DAY.format(new Date(feedAt))} `}${String(stamp).trim().split(/\s+/)[1]}`;
  }

  return (
    <section aria-labelledby="live-heading" className="space-y-3">
      <div className="flex items-center justify-between">
        <MicroLabel as="h2" id="live-heading" className="flex items-center gap-1.5">
          <LightningIcon weight="fill" className="h-3 w-3 shrink-0" aria-hidden="true" />
          Live generation
        </MicroLabel>
        <LiveState state={state} />
      </div>

      <div className={cn('flex flex-wrap items-baseline gap-x-2 transition-opacity', dim && 'opacity-50')}>
        <span className="text-[52px] font-semibold leading-none tracking-tight tabular">{total != null ? fmtNum(total, 1) : '—'}</span>
        <span className="text-lg font-medium text-muted-foreground">MW</span>
        <span className="text-sm text-muted-foreground tabular">
          of {STATION_MW} MW{total != null && ` · ${fmtNum((total / STATION_MW) * 100, 0)} %`}
        </span>
      </div>

      <div className={cn('grid grid-cols-2 gap-x-6 transition-opacity', dim && 'opacity-50')}>
        <UnitLoad label="Unit 1" mw={u1} />
        <UnitLoad label="Unit 2" mw={u2} />
      </div>

      <div className="flex items-center justify-between gap-3 text-[11px] text-muted-foreground tabular">
        <span>{IST_CLOCK.format(new Date(now))} IST</span>
        {stamp && (
          <span className={cn((state === 'late' || dim) && 'text-attention')}>
            {dim ? 'Last reading' : 'Feed'} {feedText}
          </span>
        )}
      </div>
    </section>
  );
}

function UnitLoad({ label, mw }) {
  const share = mw != null ? Math.max(0, Math.min(1, mw / UNIT_MW)) : 0;
  return (
    <div className="min-w-0">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-xs text-muted-foreground">{label}</span>
        <span className="text-[11px] text-muted-foreground tabular">{mw != null ? `${fmtNum(share * 100, 0)} %` : ''}</span>
      </div>
      <div className="mt-0.5 flex items-baseline gap-1">
        <span className="text-xl font-semibold tracking-tight tabular">{mw != null ? fmtNum(mw, 1) : '—'}</span>
        <span className="text-xs text-muted-foreground">MW</span>
      </div>
      <div
        className="mt-1.5 h-1 overflow-hidden rounded-full bg-muted"
        role="meter"
        aria-label={`${label} load`}
        aria-valuemin={0}
        aria-valuemax={UNIT_MW}
        aria-valuenow={mw ?? undefined}
      >
        <div className="h-full rounded-full bg-foreground transition-[width] duration-700" style={{ width: `${share * 100}%` }} />
      </div>
    </div>
  );
}

const STATES = {
  connecting: { label: 'Connecting', dot: 'bg-muted-foreground/40' },
  live: { label: 'Live', dot: 'bg-foreground', ping: true },
  late: { label: 'Feed late', dot: 'bg-attention', text: 'text-attention' },
  stale: { label: 'Stale', dot: 'bg-attention', text: 'text-attention' },
  offline: { label: 'No feed', dot: 'bg-attention', text: 'text-attention' },
};

function LiveState({ state }) {
  const s = STATES[state];
  return (
    <div className={cn('flex items-center gap-2 text-[10px] font-medium uppercase tracking-widest text-muted-foreground', s.text)} role="status">
      <span className="relative flex h-2 w-2">
        {s.ping && <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-foreground/60" />}
        <span className={cn('relative inline-flex h-2 w-2 rounded-full', s.dot)} />
      </span>
      {s.label}
    </div>
  );
}
