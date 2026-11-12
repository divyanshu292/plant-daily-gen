import { useMemo } from 'react';
import { cn } from '@/lib/utils';
import { SourceMarker } from '@/components/data/CoverageCalendar';
import { add, dayStatus, STATUS_TEXT } from '@/lib/entries';
import { DASH, fmtDate, fmtHours, fmtNum, monthDays } from '@/lib/format';

// Each column: how to get the value from an entry, and how to show it.
const COLUMNS = [
  { key: 'u1Gen', group: 'Generation', label: 'U1', unit: 'MU', get: (e) => e.u1Gen, dp: 2 },
  { key: 'u2Gen', group: 'Generation', label: 'U2', unit: 'MU', get: (e) => e.u2Gen, dp: 2 },
  { key: 'gen', group: 'Generation', label: 'Stn', unit: 'MU', get: (e) => add(e.u1Gen, e.u2Gen), dp: 2, strong: true },
  { key: 'coal', label: 'Coal', unit: 'MT', get: (e) => add(e.u1Coal, e.u2Coal), dp: 2 },
  { key: 'oil', label: 'Oil', unit: 'KL', get: (e) => add(e.u1Oil, e.u2Oil), dp: 2 },
  { key: 'apc', label: 'Aux power', unit: 'MU', get: (e) => e.apc, dp: 3 },
  { key: 'dm', label: 'DM water', unit: 'm³', get: (e) => add(e.u1Dm, e.u2Dm), dp: 0 },
  { key: 'bd', label: 'Backing down', unit: 'MU', get: (e) => add(e.u1Bd, e.u2Bd), dp: 3 },
  { key: 'coalReceipt', label: 'Coal receipt', unit: 'MT', get: (e) => e.coalReceipt, dp: 2 },
  { key: 'oilReceipt', label: 'Oil receipt', unit: 'KL', get: (e) => e.oilReceipt, dp: 3 },
  { key: 'outage', label: 'Outage', unit: 'h:mm', get: (e) => add(e.u1Fo, e.u2Fo, e.u1Po, e.u2Po), hours: true },
  { key: 'h2', label: 'H₂', unit: 'cyl.', get: (e) => add(e.u1H2, e.u2H2), dp: 0 },
];

const fmt = (col, v) => (v == null ? DASH : col.hours ? fmtHours(v) : fmtNum(v, col.dp));

/** The month's days (up to today) with the main columns. Station sums for coal, oil etc. */
export function MonthTable({ month, byDate, today, selected, onPick }) {
  const days = useMemo(() => monthDays(month).filter((d) => d < today || byDate[d]), [month, today, byDate]);
  const totals = useMemo(
    () =>
      Object.fromEntries(
        COLUMNS.map((c) => [c.key, add(...days.map((d) => (byDate[d] ? c.get(byDate[d]) : null)))])
      ),
    [days, byDate]
  );

  if (!days.length) {
    return (
      <div className="rounded-xl border border-border bg-card px-4 py-8 text-center text-sm text-muted-foreground">
        This month has not started yet.
      </div>
    );
  }

  const th = 'px-3 text-right text-[10px] font-medium uppercase tracking-widest text-muted-foreground whitespace-nowrap';

  return (
    <div className="space-y-2">
    <p className="text-[11px] text-muted-foreground lg:hidden">Scroll the table sideways for more columns.</p>
    <div className="overflow-x-auto rounded-xl border border-border bg-card scroll-thin">
      <table className="w-full min-w-[1040px] border-separate border-spacing-0 text-[13px] md:text-sm">
        <thead>
          <tr>
            <th
              rowSpan={2}
              className="sticky left-0 z-20 border-b border-r border-border bg-card px-3 py-2 text-left align-bottom text-[11px] font-medium uppercase tracking-widest text-muted-foreground"
            >
              Date
            </th>
            <th colSpan={3} className={cn(th, 'border-l border-border pb-0 pt-3 text-center text-foreground')}>
              Generation <span className="normal-case tracking-normal text-muted-foreground">MU</span>
            </th>
            {COLUMNS.slice(3).map((c) => (
              <th key={c.key} rowSpan={2} className={cn(th, 'border-b border-l border-border/60 py-2 align-bottom')}>
                <div className="text-foreground">{c.label}</div>
                <div className="normal-case tracking-normal">{c.unit}</div>
              </th>
            ))}
          </tr>
          <tr>
            {COLUMNS.slice(0, 3).map((c, i) => (
              <th key={c.key} className={cn(th, 'border-b border-border pb-2 pt-1', i === 0 && 'border-l')}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {days.map((iso) => {
            const entry = byDate[iso];
            const status = dayStatus(entry, iso, today);
            const isSelected = iso === selected;
            return (
              <tr
                key={iso}
                onClick={() => onPick(iso)}
                className={cn('group cursor-pointer', isSelected && '[&>*]:bg-accent')}
              >
                <th
                  scope="row"
                  className="sticky left-0 z-10 whitespace-nowrap border-b border-r border-border/60 bg-card px-3 py-2 text-left font-normal group-hover:bg-muted"
                >
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      onPick(iso);
                    }}
                    className="flex items-center gap-2 text-left focus-visible:underline focus-visible:outline-none"
                    title={STATUS_TEXT[status]}
                  >
                    <SourceMarker status={status} />
                    <span className="font-medium tabular">{fmtDate(iso, 'weekday')}</span>
                  </button>
                </th>
                {entry ? (
                  COLUMNS.map((c, i) => {
                    const v = c.get(entry);
                    return (
                      <td
                        key={c.key}
                        className={cn(
                          'whitespace-nowrap border-b border-border/60 px-3 py-2 text-right tabular group-hover:bg-muted/50',
                          (i === 0 || i >= 3) && 'border-l',
                          i === 0 ? 'border-l-border' : 'border-l-border/60',
                          c.strong && 'font-medium',
                          v == null && 'text-muted-foreground/50'
                        )}
                      >
                        {fmt(c, v)}
                      </td>
                    );
                  })
                ) : (
                  <td
                    colSpan={COLUMNS.length}
                    className="border-b border-l border-border/60 px-3 py-2 text-attention group-hover:bg-muted/50"
                  >
                    No data. Select to enter values.
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
        <tfoot>
          <tr>
            <th
              scope="row"
              className="sticky left-0 z-10 border-r border-t border-border bg-card px-3 py-2.5 text-left text-[11px] font-medium uppercase tracking-widest text-muted-foreground"
            >
              Month total
            </th>
            {COLUMNS.map((c, i) => (
              <td
                key={c.key}
                className={cn(
                  'whitespace-nowrap border-t border-border bg-muted/30 px-3 py-2.5 text-right font-semibold tabular',
                  (i === 0 || i >= 3) && 'border-l border-l-border/60'
                )}
              >
                {fmt(c, totals[c.key])}
              </td>
            ))}
          </tr>
        </tfoot>
      </table>
    </div>
    </div>
  );
}
