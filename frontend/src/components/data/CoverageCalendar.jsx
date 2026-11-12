import { useMemo } from 'react';
import { cn } from '@/lib/utils';
import { add, dayStatus, STATUS_TEXT } from '@/lib/entries';
import { fmtDate, fmtNum, monthDays } from '@/lib/format';

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

/** Source marker: filled dot = report, ring = workbook, diamond = by hand. */
export function SourceMarker({ status, className }) {
  const base = 'inline-block h-2 w-2 shrink-0';
  if (status === 'report') return <span className={cn(base, 'rounded-full bg-foreground', className)} />;
  if (status === 'workbook') return <span className={cn(base, 'rounded-full border-[1.5px] border-foreground/80', className)} />;
  if (status === 'manual') return <span className={cn(base, 'h-[7px] w-[7px] rotate-45 bg-foreground/80', className)} />;
  if (status === 'partial') return <span className={cn(base, 'rounded-full border-[1.5px] border-dashed border-attention', className)} />;
  if (status === 'none') return <span className={cn('inline-block h-0.5 w-2.5 shrink-0 rounded bg-attention', className)} />;
  return null;
}

export function CoverageCalendar({ month, byDate, today, selected, onPick }) {
  const cells = useMemo(() => {
    const days = monthDays(month);
    const firstWeekday = (new Date(`${month}-01T00:00:00`).getDay() + 6) % 7; // Monday first
    const out = Array(firstWeekday).fill(null).concat(days);
    while (out.length % 7) out.push(null);
    return out;
  }, [month]);

  const counts = useMemo(() => {
    const c = { report: 0, workbook: 0, manual: 0, partial: 0, none: 0, future: 0 };
    for (const iso of monthDays(month)) c[dayStatus(byDate[iso], iso, today)] += 1;
    return c;
  }, [month, byDate, today]);

  return (
    <div className="rounded-xl border border-border bg-card p-3 md:p-5">
      <div className="mb-2 grid grid-cols-7 gap-1 text-center md:gap-2">
        {WEEKDAYS.map((w) => (
          <div key={w} className="text-[10px] font-medium uppercase tracking-widest text-muted-foreground">
            <span className="md:hidden">{w.slice(0, 1)}</span>
            <span className="hidden md:inline">{w}</span>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-7 gap-1 md:gap-2">
        {cells.map((iso, i) => {
          if (!iso) return <div key={`pad-${i}`} />;
          const entry = byDate[iso];
          const status = dayStatus(entry, iso, today);
          const isToday = iso === today;
          const future = status === 'future';
          const gen = add(entry?.u1Gen, entry?.u2Gen);
          const isSelected = iso === selected;
          return (
            <button
              key={iso}
              type="button"
              disabled={future}
              onClick={() => onPick(iso)}
              title={`${fmtDate(iso, 'weekday')}: ${STATUS_TEXT[status]}${gen != null ? `, ${fmtNum(gen, 2)} MU` : ''}`}
              aria-label={`${fmtDate(iso, 'long')}: ${STATUS_TEXT[status]}`}
              className={cn(
                'relative flex h-12 flex-col justify-between rounded-md border p-1.5 text-left transition-colors sm:h-16 md:h-20 md:rounded-lg md:p-2',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                ['report', 'workbook', 'manual'].includes(status) && 'border-border bg-background hover:border-foreground/50',
                status === 'partial' && 'border-dashed border-attention/60 hover:border-attention',
                status === 'none' && 'border-dashed border-attention/50 bg-attention/[0.04] hover:border-attention',
                future && 'cursor-default border-transparent bg-muted/30 text-muted-foreground/40',
                isToday && 'ring-1 ring-foreground/60',
                isSelected && 'ring-2 ring-foreground'
              )}
            >
              <div className="flex items-start justify-between gap-1">
                <span
                  className={cn(
                    'text-sm font-semibold leading-none tabular md:text-base',
                    status === 'none' && 'text-muted-foreground'
                  )}
                >
                  {Number(iso.slice(8))}
                </span>
                <SourceMarker status={status} className="mt-0.5" />
              </div>
              <div className="hidden truncate text-[10px] leading-tight text-muted-foreground sm:block md:text-[11px]">
                {isToday && future ? 'Today' : null}
                {gen != null && (
                  <span className="tabular">
                    {fmtNum(gen, 2)}
                    <span className="ml-0.5 opacity-60">MU</span>
                  </span>
                )}
                {status === 'none' && <span className="text-attention">No data</span>}
                {status === 'partial' && <span className="text-attention">No gen.</span>}
                {isToday && !future && gen == null && status !== 'none' && 'Today'}
              </div>
            </button>
          );
        })}
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-border pt-3 text-[11px] text-muted-foreground">
        <LegendItem status="report" label="From report" count={counts.report} />
        <LegendItem status="workbook" label="From workbook" count={counts.workbook} />
        <LegendItem status="manual" label="By hand" count={counts.manual} />
        {counts.partial > 0 && <LegendItem status="partial" label="No generation" count={counts.partial} />}
        <LegendItem status="none" label="No data" count={counts.none} />
        {counts.future > 0 && (
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2.5 w-2.5 rounded-sm bg-muted" />
            Not yet <span className="tabular">{counts.future}</span>
          </span>
        )}
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-sm ring-1 ring-foreground/60" />
          Today
        </span>
      </div>
    </div>
  );
}

function LegendItem({ status, label, count }) {
  return (
    <span className="flex items-center gap-1.5">
      <SourceMarker status={status} />
      {label} <span className="font-medium text-foreground tabular">{count}</span>
    </span>
  );
}
