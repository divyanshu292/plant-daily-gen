import { useEffect, useMemo, useRef, useState } from 'react';
import { LightningSlashIcon, WarningIcon } from '@phosphor-icons/react';
import { api } from '@/lib/api';
import { DayCurve, LoadLegend } from '@/components/home/charts';
import { fmtNum } from '@/lib/format';
import { cn } from '@/lib/utils';

const UNIT_MW = 210;
const REFRESH_MS = 2 * 60_000;
const FETCH_TIMEOUT_MS = 10_000;
// A new feed stamp is stored by the server as it serves it; ask for the day a moment later.
const AFTER_STAMP_MS = 1_000;
const MONTHS = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'];

/** Feed stamp "12-Nov-2026 20:55" -> "2026-11-12T20:55" (the form /live/day uses), or null. */
function feedIso(stamp) {
  const m = /^(\d{1,2})-([A-Za-z]{3})-(\d{4})\s+(\d{1,2}):(\d{2})/.exec(String(stamp || '').trim());
  const month = m ? MONTHS.indexOf(m[2].toLowerCase()) : -1;
  if (month < 0) return null;
  const pad = (n) => String(n).padStart(2, '0');
  return `${m[3]}-${pad(month + 1)}-${pad(+m[1])}T${pad(+m[4])}:${m[5]}`;
}

/** "2026-11-12T21:54" -> "21:54". */
export const hhmm = (at) => String(at || '').slice(11, 16);

const num = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : null);

/**
 * Today's recorded readings from /live/day: on mount, when the live feed shows a
 * reading newer than the last one recorded, and every 2 minutes, never while the
 * tab is hidden. Errors are silent and keep the last day.
 */
function useLiveDay(stamp) {
  const [day, setDay] = useState(null);
  const loadRef = useRef(() => {});

  useEffect(() => {
    let cancelled = false;
    let busy = false;
    let again = false;
    let paused = false;
    let timer = null;
    const load = async () => {
      clearTimeout(timer);
      if (cancelled) return;
      if (document.hidden) {
        paused = true;
        return;
      }
      if (busy) {
        again = true;
        return;
      }
      busy = true;
      const ctrl = new AbortController();
      const abort = setTimeout(() => ctrl.abort(), FETCH_TIMEOUT_MS);
      try {
        const data = await api('/live/day', { signal: ctrl.signal });
        if (!cancelled && data && Array.isArray(data.points)) setDay(data);
      } catch {
        // Silent: the live numbers still work, and the last curve stays up.
      } finally {
        clearTimeout(abort);
        busy = false;
        if (!cancelled) {
          if (again) {
            again = false;
            load();
          } else {
            timer = setTimeout(load, REFRESH_MS);
          }
        }
      }
    };
    loadRef.current = load;
    load();
    const onVisible = () => {
      if (!document.hidden && paused) {
        paused = false;
        load();
      }
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      cancelled = true;
      clearTimeout(timer);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, []);

  // The feed moved on past the last recorded reading: fetch the day again.
  const lastAt = day ? day.lastAt || '' : null;
  const feedAt = feedIso(stamp);
  useEffect(() => {
    if (lastAt == null || !feedAt || feedAt <= lastAt) return undefined;
    const t = setTimeout(() => loadRef.current(), AFTER_STAMP_MS);
    return () => clearTimeout(t);
  }, [feedAt, lastAt]);

  return day;
}

/** Readings as { at, min, u1, u2, stn }; the station figure needs both units. */
function toPoints(raw) {
  if (!Array.isArray(raw)) return [];
  const out = [];
  for (const p of raw) {
    const at = String(p?.at || '');
    const h = Number(at.slice(11, 13));
    const m = Number(at.slice(14, 16));
    if (!Number.isFinite(h) || !Number.isFinite(m) || at.length < 16) continue;
    const u1 = num(p.u1);
    const u2 = num(p.u2);
    out.push({ at, min: h * 60 + m, u1, u2, stn: u1 != null && u2 != null ? u1 + u2 : null });
  }
  return out;
}

/** Minutes since 00:00 -> "14:05". */
export function clockOf(min) {
  const m = Math.round(min);
  return `${String(Math.floor(m / 60) % 24).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
}

/**
 * Under the live numbers: today's load curve, energy so far with where the day is
 * heading, and any unit that tripped or is offline. Nothing until the first answer.
 */
export function TodayLoad({ stamp, askingRate, active, onActive }) {
  const day = useLiveDay(stamp);
  const points = useMemo(() => toPoints(day?.points), [day]);
  if (!day) return null;

  const capacity = (num(day.unitMw) || UNIT_MW) * 2;
  if (points.length === 0) {
    return <p className="text-[11px] text-muted-foreground/70">Load curve starts once readings are recorded</p>;
  }

  const values = points.map((p) => p.stn).filter((v) => v != null);
  const label = values.length
    ? `Station load today with Unit 1 and Unit 2, ${hhmm(points[0].at)} to ${hhmm(points[points.length - 1].at)} IST, total between ${fmtNum(Math.min(...values), 0)} and ${fmtNum(Math.max(...values), 0)} MW`
    : 'Station and unit load today';

  return (
    <div className="space-y-2">
      <div className="space-y-1">
        <LoadLegend />
        <DayCurve points={points} capacity={capacity} active={active} onActive={onActive} label={label} />
      </div>
      <TodaySoFar day={day} askingRate={num(askingRate)} />
      <UnitEvents day={day} points={points} />
    </div>
  );
}

function hoursText(h) {
  return fmtNum(h, h < 10 && h % 1 >= 0.05 ? 1 : 0);
}

/**
 * "Today 4.12 MU · PLF 71.5 % · on course for 7.41 MU · needs 9.35/day", wrapping only after a dot.
 * When the readings miss a good part of the day (recording started late, or the
 * scheduler stopped) the MU only covers the recorded hours, so the line says so
 * and leaves out the day's projection, which would come out far too low.
 */
function TodaySoFar({ day, askingRate }) {
  const energy = num(day.energy?.stn);
  const plf = num(day.plf?.stn);
  const elapsed = num(day.hours?.elapsed);
  const covered = num(day.hours?.covered);
  if (energy == null) return null;
  const partial = elapsed != null && covered != null && elapsed - covered > Math.max(1, elapsed * 0.1);
  const projected = partial ? null : num(day.projected?.stn);
  const short = projected != null && askingRate != null && projected < askingRate;

  // Two groups that each stay on one line: what the day has made, and where it is heading.
  const made = (
    <>
      {partial ? `Recorded ${hoursText(covered)} of ${hoursText(elapsed)} h · ` : 'Today '}
      <Strong>{fmtNum(energy, 2)}</Strong> MU
      {plf != null && (
        <>
          {' · '}PLF <Strong>{fmtNum(plf, 1)}</Strong> %
        </>
      )}
    </>
  );
  const heading = projected != null && (
    <>
      on course for <Strong>{fmtNum(projected, 2)}</Strong> MU
      {askingRate != null && (
        <>
          {' · '}
          <span className={cn(short && 'text-attention')}>
            needs <span className={cn('font-medium', !short && 'text-foreground')}>{fmtNum(askingRate, 2)}</span>/day
          </span>
        </>
      )}
    </>
  );

  // The dot stays with the group before it, so a wrapped line never starts with one.
  return (
    <p className="text-xs leading-relaxed text-muted-foreground tabular">
      <span className="whitespace-nowrap">
        {made}
        {heading && ' ·'}
      </span>{' '}
      {heading && <span className="whitespace-nowrap">{heading}</span>}
    </p>
  );
}

function Strong({ children }) {
  return <span className="font-medium text-foreground">{children}</span>;
}

/** Latest trip or stop of a unit at or before the end of the list. */
function lastDown(events, unit) {
  for (let i = events.length - 1; i >= 0; i--) {
    const e = events[i];
    if (e.unit === unit && (e.kind === 'trip' || e.kind === 'stop')) return e;
  }
  return null;
}

/**
 * Units offline now (attention), else today's trips and when the unit came back (quiet).
 * At most one line per unit.
 */
function UnitEvents({ day, points }) {
  const events = Array.isArray(day.events) ? day.events.filter((e) => e && (e.unit === 1 || e.unit === 2)) : [];
  const offline = Array.isArray(day.offline) ? day.offline.filter((u) => u === 1 || u === 2) : [];

  let rows = [];
  if (offline.length) {
    rows = offline.map((unit) => {
      const down = lastDown(events, unit);
      const key = `u${unit}`;
      const allDay = !down && points.length > 0 && points.every((p) => p[key] == null || p[key] < 5);
      let text = `Unit ${unit} offline`;
      if (down) text += ` since ${hhmm(down.at)}`;
      else if (allDay) text += ' all day';
      const detail = down?.kind === 'trip' && num(down.fromMw) != null ? `tripped from ${fmtNum(down.fromMw, 0)} MW` : null;
      return { unit, attention: true, text, detail };
    });
  } else {
    for (const unit of [1, 2]) {
      const trips = events.filter((e) => e.unit === unit && e.kind === 'trip');
      const trip = trips[trips.length - 1];
      if (!trip) continue;
      const back = events.find((e) => e.unit === unit && e.kind === 'back' && e.at > trip.at);
      rows.push({
        unit,
        attention: false,
        text: `Unit ${unit} tripped at ${hhmm(trip.at)}${back ? ` · back at ${hhmm(back.at)}` : ''}`,
        detail: trips.length > 1 ? `${trips.length} trips today` : null,
      });
    }
  }
  if (!rows.length) return null;

  return (
    <ul className="space-y-1">
      {rows.map((r) => (
        <li key={r.unit} className={cn('flex items-start gap-2 text-xs leading-snug', !r.attention && 'text-muted-foreground')}>
          {r.attention ? (
            <WarningIcon weight="fill" className="mt-px h-3.5 w-3.5 shrink-0 text-attention" aria-hidden="true" />
          ) : (
            <LightningSlashIcon weight="bold" className="mt-px h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          )}
          <span className="min-w-0 tabular">
            <span className={cn(r.attention && 'font-medium')}>{r.text}</span>
            {r.detail && <span className="text-muted-foreground"> · {r.detail}</span>}
          </span>
        </li>
      ))}
    </ul>
  );
}
