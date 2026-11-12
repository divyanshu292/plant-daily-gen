import { useMemo, useState } from 'react';
import { cn } from '@/lib/utils';
import { Segmented } from '@/components/ui/segmented';
import { DASH, fmtByKind, fmtDate } from '@/lib/format';

const UNITS = [
  { key: 'u1', label: 'Unit 1', short: 'U1' },
  { key: 'u2', label: 'Unit 2', short: 'U2' },
  { key: 'stn', label: 'Station', short: 'Stn' },
];
const PERIODS = [
  { value: 'day', label: 'Day' },
  { value: 'month', label: 'Month' },
  { value: 'year', label: 'Year' },
];

// Sections of the report, in the order shown. Rows keep the server's order inside a
// section. A row key not listed here joins the section of the row before it, so a
// row the server adds later still shows up without a change here.
const SECTIONS = [
  { title: 'Generation', keys: ['gen', 'plf', 'loadingFactor', 'avgLoad', 'runningHours', 'availability'] },
  { title: 'Targets', keys: ['target', 'targetPlf', 'askingRate'] },
  {
    title: 'Fuel and efficiency',
    keys: ['apc', 'apcPct', 'coal', 'spCoal', 'oil', 'spOil', 'dm', 'dmPct', 'heatRate', 'h2'],
  },
  {
    title: 'Partial loading',
    keys: ['partialLoadingPct', 'partialLoading', 'stationLoss', 'backingDown', 'deemedGen', 'deemedPlf'],
  },
  {
    title: 'Outages',
    keys: ['forcedOutage', 'forcedOutagePct', 'plannedOutage', 'plannedOutagePct', 'totalOutage', 'totalOutagePct', 'trips', 'btl', 'btlShare'],
  },
  { title: 'Fuel receipt', keys: ['coalReceipt', 'oilReceipt'] },
];
const SECTION_OF = Object.fromEntries(SECTIONS.flatMap((s, i) => s.keys.map((k) => [k, i])));

function toSections(rows) {
  const buckets = SECTIONS.map(() => []);
  const other = [];
  let last = null;
  for (const row of rows) {
    const i = SECTION_OF[row.key] ?? last;
    if (i == null) other.push(row);
    else {
      buckets[i].push(row);
      last = i;
    }
  }
  return [...SECTIONS.map((s, i) => ({ title: s.title, rows: buckets[i] })), { title: 'Other', rows: other }]
    .filter((s) => s.rows.length)
    .map((s) => ({
      ...s,
      rows: s.rows.map((row, i) => {
        const sub = row.label.startsWith('- ');
        // "Forced outage h:mm" then "Forced outage %": the second line only needs its unit.
        const cont = i > 0 && s.rows[i - 1].label === row.label;
        return { row, sub, cont, label: sub ? row.label.slice(2) : row.label };
      }),
    }));
}

/** The cell text, or null when the row has no figure for this unit (shown blank). */
function cellValue(row, unit, period, hasData) {
  const g = row[unit];
  if (!g) return null;
  // With no data for the day the server counts it as zero; show that as empty, not as 0.
  const v = period === 'day' && !hasData ? null : g[period];
  return { text: v == null ? DASH : fmtByKind(v, row.kind, row.decimals), empty: v == null };
}

// Sticky header rows sit under the app header; --sticky-top is set by the screen (see common/sticky.js).
const TOP = 'top-[var(--sticky-top,3.5rem)]';
// The period switch row is 60 px (44 px control + 16 px padding); the column heads go under it, 1 px tucked in.
const TOP_2 = 'top-[calc(var(--sticky-top,3.5rem)_+_59px)]';
// The unit names row on wide screens is h-9.
const TOP_WIDE_2 = 'top-[calc(var(--sticky-top,3.5rem)_+_2.25rem)]';

function RowLabel({ item, className }) {
  const { row, sub, cont, label } = item;
  return (
    <th scope="row" className={cn('py-2.5 pr-2 text-left align-baseline font-normal leading-snug [overflow-wrap:anywhere]', className)}>
      {cont ? (
        <span className={cn('text-[11px] text-muted-foreground', sub && 'pl-3')}>{row.unit}</span>
      ) : (
        <span className={cn('block', sub && 'pl-3 text-muted-foreground')}>
          {label}
          {/* The space lets a long label wrap before its unit. */}
          {row.unit && ' '}
          {row.unit && <span className="ml-0.5 whitespace-nowrap text-[11px] text-muted-foreground">{row.unit}</span>}
        </span>
      )}
    </th>
  );
}

/** Phones: one period at a time, Unit 1 / Unit 2 / Station across. */
function PeriodTable({ sections, hasData, period, onPeriod, coverage }) {
  return (
    <table className="w-full border-separate border-spacing-0 text-sm">
      <thead>
        <tr>
          <th colSpan={4} className={cn('sticky z-20 bg-background py-2 font-normal', TOP)}>
            <Segmented options={PERIODS} value={period} onChange={onPeriod} aria-label="Period" className="md:max-w-md" />
          </th>
        </tr>
        <tr>
          <th
            className={cn(TOP_2, 'sticky z-20 border-b border-border bg-background pb-2 pt-1 text-left text-[11px] font-normal text-muted-foreground tabular')}
          >
            {coverage}
          </th>
          {UNITS.map((u) => (
            <th
              key={u.key}
              scope="col"
              className={cn(TOP_2, 'sticky z-20 border-b border-border bg-background pb-2 pl-2 pt-1 text-right text-[11px] font-medium uppercase tracking-widest text-muted-foreground')}
            >
              <abbr title={u.label} className="no-underline">
                {u.short}
              </abbr>
            </th>
          ))}
        </tr>
      </thead>
      {sections.map((s) => (
        <tbody key={s.title}>
          <tr>
            <th
              colSpan={4}
              scope="colgroup"
              className="pb-1 pt-7 text-left text-[11px] font-medium uppercase tracking-widest text-muted-foreground"
            >
              {s.title}
            </th>
          </tr>
          {s.rows.map((item, i) => {
            const line = i > 0 && !item.cont && 'border-t border-border/60';
            return (
              <tr key={item.row.key}>
                <RowLabel item={item} className={cn('w-full', line, item.cont && 'pt-0')} />
                {UNITS.map((u) => {
                  const c = cellValue(item.row, u.key, period, hasData);
                  return (
                    <td
                      key={u.key}
                      className={cn(
                        'whitespace-nowrap py-2.5 pl-2 text-right align-baseline text-[clamp(12px,3.35vw,13px)] tabular',
                        line,
                        item.cont && 'pt-0',
                        u.key === 'stn' ? 'font-medium' : 'text-foreground/80',
                        c?.empty && 'font-normal text-muted-foreground/50'
                      )}
                    >
                      {c?.text}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      ))}
    </table>
  );
}

/** Wide screens: every unit and period side by side. */
function FullTable({ sections, hasData }) {
  const head = 'sticky z-20 bg-background';
  return (
    <table className="w-full border-separate border-spacing-0 text-sm">
      <thead>
        <tr>
          <th rowSpan={2} className={cn(head, TOP, 'border-b border-border pb-2 align-bottom text-left text-[11px] font-medium uppercase tracking-widest text-muted-foreground')}>
            Particulars
          </th>
          {UNITS.map((u) => (
            <th
              key={u.key}
              colSpan={3}
              scope="colgroup"
              className={cn(head, TOP, 'h-9 pl-5 align-bottom text-right text-[11px] font-semibold uppercase tracking-widest xl:pl-8')}
            >
              {u.label}
            </th>
          ))}
        </tr>
        <tr>
          {UNITS.flatMap((u) =>
            PERIODS.map((p) => (
              <th
                key={`${u.key}-${p.value}`}
                scope="col"
                className={cn(
                  head,
                  TOP_WIDE_2,
                  'border-b border-border pb-2 pt-1 text-right text-[10px] font-medium uppercase tracking-widest text-muted-foreground',
                  p.value === 'day' ? 'pl-5 xl:pl-8' : 'pl-3 xl:pl-4'
                )}
              >
                {p.label}
              </th>
            ))
          )}
        </tr>
      </thead>
      {sections.map((s) => (
        <tbody key={s.title}>
          <tr>
            <th
              colSpan={10}
              scope="colgroup"
              className="pb-1 pt-8 text-left text-[11px] font-medium uppercase tracking-widest text-muted-foreground"
            >
              {s.title}
            </th>
          </tr>
          {s.rows.map((item, i) => {
            const line = i > 0 && !item.cont && 'border-t border-border/60';
            return (
              <tr key={item.row.key} className="group">
                <RowLabel item={item} className={cn('min-w-[11rem] group-hover:bg-muted/40 xl:min-w-[15rem]', line, item.cont && 'pt-0')} />
                {UNITS.flatMap((u) =>
                  PERIODS.map((p) => {
                    const c = cellValue(item.row, u.key, p.value, hasData);
                    return (
                      <td
                        key={`${u.key}-${p.value}`}
                        className={cn(
                          'whitespace-nowrap py-2.5 text-right align-baseline tabular group-hover:bg-muted/40',
                          p.value === 'day' ? 'pl-5 font-medium xl:pl-8' : 'pl-3 text-foreground/75 xl:pl-4',
                          line,
                          item.cont && 'pt-0',
                          c?.empty && 'font-normal text-muted-foreground/50'
                        )}
                      >
                        {c?.text}
                      </td>
                    );
                  })
                )}
              </tr>
            );
          })}
        </tbody>
      ))}
    </table>
  );
}

/**
 * The performance report: rows down the side, Unit 1 / Unit 2 / Station across,
 * each for the day, month to date and year to date. Rendered from the row
 * metadata (kind, decimals) so new rows need no code here. Phones show one
 * period at a time; from lg up every column is shown.
 */
export function PerformanceTable({ report }) {
  const { rows = [], hasData, days, date } = report;
  const [period, setPeriod] = useState('day');
  const sections = useMemo(() => toSections(rows), [rows]);

  const coverage =
    period === 'day'
      ? fmtDate(date, 'short')
      : days
        ? period === 'month'
          ? `${days.month} of ${days.monthLength} days`
          : `${days.year} of ${days.yearLength} days`
        : '';

  return (
    <div className="space-y-3">
      <div className="lg:hidden">
        <PeriodTable sections={sections} hasData={hasData} period={period} onPeriod={setPeriod} coverage={coverage} />
      </div>
      <div className="hidden lg:block">
        <FullTable sections={sections} hasData={hasData} />
      </div>
      {days && (
        <p className="border-t border-border pt-3 text-[11px] leading-relaxed text-muted-foreground">
          Day is {fmtDate(date, 'medium')}. Month covers {days.month} of {days.monthLength} days, year covers {days.year} of{' '}
          {days.yearLength} days since 1 April. Hours are shown as h:mm. A blank cell does not apply to that column.
        </p>
      )}
    </div>
  );
}
