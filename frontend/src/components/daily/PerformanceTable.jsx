import { cn } from '@/lib/utils';
import { DASH, fmtByKind, fmtDate } from '@/lib/format';

const GROUPS = [
  { key: 'u1', label: 'Unit 1' },
  { key: 'u2', label: 'Unit 2' },
  { key: 'stn', label: 'Station' },
];
const PERIODS = [
  { key: 'day', label: 'Day' },
  { key: 'month', label: 'Month' },
  { key: 'year', label: 'Year' },
];

function Cell({ group, period, row, hasData, last }) {
  const first = period.key === 'day';
  const base = cn(
    'px-3 py-2 text-right tabular whitespace-nowrap group-hover:bg-muted/50',
    first && 'border-l border-border',
    !last && 'border-b border-border/60'
  );
  if (!group) return <td className={cn(base, 'bg-muted/30')} aria-label="not applicable" />;
  // With no data for the day the server counts it as zero; show that as empty, not as 0.
  const value = first && !hasData ? null : group[period.key];
  return (
    <td className={cn(base, first ? 'font-medium' : 'text-foreground/80', value == null && 'text-muted-foreground/50')}>
      {value == null ? DASH : fmtByKind(value, row.kind, row.decimals)}
    </td>
  );
}

/**
 * The performance report: rows down the side, Unit 1 / Unit 2 / Station across,
 * each split into the day, month to date and year to date. Rendered from the
 * row metadata (kind, decimals) so new rows need no code here.
 */
export function PerformanceTable({ report }) {
  const { rows = [], hasData, days, date } = report;
  return (
    <div className="space-y-2">
      <p className="text-[11px] text-muted-foreground lg:hidden">Scroll the table sideways for Unit 2 and Station.</p>
      <div className="overflow-x-auto rounded-xl border border-border bg-card scroll-thin">
        <table className="w-full min-w-[860px] border-separate border-spacing-0 text-[13px] md:text-sm">
          <thead>
            <tr>
              <th
                rowSpan={2}
                className="sticky left-0 z-20 border-b border-r border-border bg-card px-3 py-2 text-left align-bottom text-[11px] font-medium uppercase tracking-widest text-muted-foreground md:px-4"
              >
                Particulars
              </th>
              {GROUPS.map((g) => (
                <th
                  key={g.key}
                  colSpan={3}
                  className="border-l border-border px-3 pb-1 pt-3 text-center text-[11px] font-semibold uppercase tracking-widest"
                >
                  {g.label}
                </th>
              ))}
            </tr>
            <tr>
              {GROUPS.flatMap((g) =>
                PERIODS.map((p) => (
                  <th
                    key={`${g.key}-${p.key}`}
                    className={cn(
                      'border-b border-border px-3 pb-2 pt-1 text-right text-[10px] font-medium uppercase tracking-widest text-muted-foreground',
                      p.key === 'day' && 'border-l'
                    )}
                  >
                    {p.label}
                  </th>
                ))
              )}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => {
              const sub = row.label.startsWith('- ');
              const label = sub ? row.label.slice(2) : row.label;
              const last = i === rows.length - 1;
              return (
                <tr key={row.key} className="group">
                  <th
                    scope="row"
                    className={cn(
                      'sticky left-0 z-10 w-[8.5rem] min-w-[8.5rem] border-r border-border bg-card px-3 py-2 text-left font-normal group-hover:bg-muted md:w-auto md:min-w-[14rem] md:px-4',
                      !last && 'border-b border-border/60'
                    )}
                  >
                    <div className={cn('leading-snug', sub && 'pl-3 text-muted-foreground')}>{label}</div>
                    <div className={cn('text-[11px] text-muted-foreground', sub && 'pl-3')}>{row.unit}</div>
                  </th>
                  {GROUPS.flatMap((g) =>
                    PERIODS.map((p) => (
                      <Cell
                        key={`${g.key}-${p.key}`}
                        group={row[g.key]}
                        period={p}
                        row={row}
                        hasData={hasData}
                        last={last}
                      />
                    ))
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {days && (
        <p className="text-[11px] leading-relaxed text-muted-foreground">
          Day is {fmtDate(date, 'medium')}. Month covers {days.month} of {days.monthLength} days, year covers {days.year} of{' '}
          {days.yearLength} days since 1 April. Hours are shown as h:mm. A shaded cell does not apply to that column.
        </p>
      )}
    </div>
  );
}

