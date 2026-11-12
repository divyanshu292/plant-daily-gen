import { useMemo, useState } from 'react';
import { CaretRightIcon } from '@phosphor-icons/react';
import { cn } from '@/lib/utils';
import { Segmented } from '@/components/ui/segmented';
import { SourceMarker } from '@/components/data/CoverageCalendar';
import { add, dayStatus, STATUS_TEXT } from '@/lib/entries';
import { DASH, fmtDate, fmtHours, fmtNum, monthDays, parseIso } from '@/lib/format';

// Each column: how to get the value from an entry, and how to show it. `short` heads the column on phones.
const COLUMNS = [
  { key: 'u1Gen', group: 'Generation', label: 'U1', short: 'U1', unit: 'MU', get: (e) => e.u1Gen, dp: 2 },
  { key: 'u2Gen', group: 'Generation', label: 'U2', short: 'U2', unit: 'MU', get: (e) => e.u2Gen, dp: 2 },
  { key: 'gen', group: 'Generation', label: 'Stn', short: 'Stn', unit: 'MU', get: (e) => add(e.u1Gen, e.u2Gen), dp: 2, strong: true },
  { key: 'coal', label: 'Coal', short: 'Coal', unit: 'MT', get: (e) => add(e.u1Coal, e.u2Coal), dp: 2 },
  { key: 'oil', label: 'Oil', short: 'Oil', unit: 'KL', get: (e) => add(e.u1Oil, e.u2Oil), dp: 2 },
  { key: 'apc', label: 'Aux power', short: 'Aux', unit: 'MU', get: (e) => e.apc, dp: 3 },
  { key: 'dm', label: 'DM water', short: 'DM', unit: 'm³', get: (e) => add(e.u1Dm, e.u2Dm), dp: 0 },
  { key: 'bd', label: 'Backing down', short: 'BD', unit: 'MU', get: (e) => add(e.u1Bd, e.u2Bd), dp: 3 },
  { key: 'coalReceipt', label: 'Coal receipt', short: 'Coal in', unit: 'MT', get: (e) => e.coalReceipt, dp: 2 },
  { key: 'oilReceipt', label: 'Oil receipt', short: 'Oil in', unit: 'KL', get: (e) => e.oilReceipt, dp: 3 },
  { key: 'outage', label: 'Outage', short: 'Outage', unit: 'h:mm', get: (e) => add(e.u1Fo, e.u2Fo, e.u1Po, e.u2Po), hours: true },
  { key: 'h2', label: 'H₂', short: 'H₂', unit: 'cyl.', get: (e) => add(e.u1H2, e.u2H2), dp: 0 },
];
const BY_KEY = Object.fromEntries(COLUMNS.map((c) => [c.key, c]));

// Phones show one group of columns at a time, so every figure fits without sideways scrolling.
const VIEWS = [
  { value: 'gen', label: 'Generation', cols: ['u1Gen', 'u2Gen', 'gen'] },
  { value: 'fuel', label: 'Fuel', cols: ['coal', 'oil', 'coalReceipt', 'oilReceipt'] },
  { value: 'other', label: 'Aux & outage', cols: ['apc', 'dm', 'bd', 'outage', 'h2'] },
];

const fmt = (col, v) => (v == null ? DASH : col.hours ? fmtHours(v) : fmtNum(v, col.dp));
const weekday = (iso) => parseIso(iso).toLocaleDateString('en-GB', { weekday: 'short' });

/** Phones: date, then the chosen group's columns. Headings stay in view under the app header. */
function CompactTable({ days, byDate, today, selected, onPick, totals }) {
  const [view, setView] = useState('gen');
  const cols = VIEWS.find((v) => v.value === view).cols.map((k) => BY_KEY[k]);
  const span = cols.length + 1;

  // 13 px figures, a touch smaller on phones narrower than 390 px so a month of totals still fits.
  return (
    <table className="w-full border-separate border-spacing-0 text-[clamp(12px,3.35vw,13px)]">
      <thead>
        <tr>
          <th colSpan={span} className="sticky top-[var(--sticky-top,3.5rem)] z-20 bg-background py-2 font-normal">
            <Segmented options={VIEWS} value={view} onChange={setView} aria-label="Columns" className="md:max-w-md" />
          </th>
        </tr>
        <tr>
          <th
            scope="col"
            className="sticky top-[calc(var(--sticky-top,3.5rem)_+_59px)] z-20 border-b border-border bg-background pb-2 pt-1 text-left align-bottom text-[11px] font-medium uppercase tracking-widest text-muted-foreground"
          >
            Day
          </th>
          {cols.map((c) => (
            <th
              key={c.key}
              scope="col"
              title={c.label}
              className="sticky top-[calc(var(--sticky-top,3.5rem)_+_59px)] z-20 border-b border-border bg-background pb-2 pl-1.5 pt-1 min-[380px]:pl-2 text-right align-bottom font-normal leading-tight"
            >
              <div className="text-xs font-medium text-foreground">{c.short}</div>
              <div className="text-[10px] text-muted-foreground">{c.unit}</div>
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {days.map((iso) => {
          const entry = byDate[iso];
          const status = dayStatus(entry, iso, today);
          const isSelected = iso === selected;
          const cell = cn('border-b border-border/60 py-3', isSelected && 'bg-accent');
          return (
            <tr key={iso} onClick={() => onPick(iso)} className="cursor-pointer active:bg-muted">
              <th scope="row" className={cn(cell, 'pr-2 text-left font-normal')}>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onPick(iso);
                  }}
                  aria-label={`${fmtDate(iso, 'weekday')}: ${STATUS_TEXT[status]}`}
                  className="-my-3 flex h-11 items-center gap-2 whitespace-nowrap text-left focus-visible:underline focus-visible:outline-none"
                >
                  <span className="flex w-2.5 justify-center">
                    <SourceMarker status={status} />
                  </span>
                  <span className="flex flex-col leading-none">
                    <span className="font-semibold tabular">{Number(iso.slice(8))}</span>
                    <span className="mt-1 text-[10px] text-muted-foreground">{weekday(iso)}</span>
                  </span>
                </button>
              </th>
              {entry ? (
                cols.map((c) => {
                  const v = c.get(entry);
                  return (
                    <td
                      key={c.key}
                      className={cn(
                        cell,
                        'whitespace-nowrap pl-1.5 text-right tabular min-[380px]:pl-2',
                        c.strong ? 'font-medium' : 'text-foreground/80',
                        v == null && 'font-normal text-muted-foreground/50'
                      )}
                    >
                      {fmt(c, v)}
                    </td>
                  );
                })
              ) : (
                <td colSpan={cols.length} className={cn(cell, 'pl-2 text-right text-attention')}>
                  <span className="inline-flex items-center gap-1">
                    No data · enter values
                    <CaretRightIcon weight="bold" className="h-3 w-3" />
                  </span>
                </td>
              )}
            </tr>
          );
        })}
      </tbody>
      <tfoot>
        <tr>
          <th scope="row" className="pt-3 text-left text-[11px] font-medium uppercase tracking-widest text-muted-foreground">
            Total
          </th>
          {cols.map((c) => (
            <td key={c.key} className="whitespace-nowrap pl-1.5 pt-3 text-right font-semibold tabular min-[380px]:pl-2">
              {fmt(c, totals[c.key])}
            </td>
          ))}
        </tr>
      </tfoot>
    </table>
  );
}

/** Wide screens: every column. Scrolls sideways inside its box if the window is narrow. */
function FullTable({ days, byDate, today, selected, onPick, totals }) {
  const th = 'px-3 text-right text-[10px] font-medium uppercase tracking-widest text-muted-foreground whitespace-nowrap';
  return (
    <div className="scroll-thin overflow-x-auto">
      <table className="w-full min-w-[960px] border-separate border-spacing-0 text-sm">
        <thead>
          <tr>
            <th
              rowSpan={2}
              className="sticky left-0 z-20 border-b border-border bg-background py-2 pr-3 text-left align-bottom text-[11px] font-medium uppercase tracking-widest text-muted-foreground"
            >
              Date
            </th>
            <th colSpan={3} className={cn(th, 'pb-0 pt-2 text-center text-foreground')}>
              Generation <span className="normal-case tracking-normal text-muted-foreground">MU</span>
            </th>
            {COLUMNS.slice(3).map((c) => (
              <th key={c.key} rowSpan={2} className={cn(th, 'border-b border-border py-2 align-bottom')}>
                <div className="text-foreground">{c.label}</div>
                <div className="normal-case tracking-normal">{c.unit}</div>
              </th>
            ))}
          </tr>
          <tr>
            {COLUMNS.slice(0, 3).map((c) => (
              <th key={c.key} className={cn(th, 'border-b border-border pb-2 pt-1')}>
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
            const cell = cn('border-b border-border/60 group-hover:bg-muted/60', isSelected && 'bg-accent');
            return (
              <tr key={iso} onClick={() => onPick(iso)} className="group cursor-pointer">
                <th scope="row" className={cn(cell, 'sticky left-0 z-10 whitespace-nowrap bg-background py-2 pr-3 text-left font-normal')}>
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
                  COLUMNS.map((c) => {
                    const v = c.get(entry);
                    return (
                      <td
                        key={c.key}
                        className={cn(
                          cell,
                          'whitespace-nowrap px-3 py-2 text-right tabular',
                          c.strong ? 'font-medium' : 'text-foreground/80',
                          v == null && 'font-normal text-muted-foreground/50'
                        )}
                      >
                        {fmt(c, v)}
                      </td>
                    );
                  })
                ) : (
                  <td colSpan={COLUMNS.length} className={cn(cell, 'px-3 py-2 text-attention')}>
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
              className="sticky left-0 z-10 bg-background py-3 pr-3 text-left text-[11px] font-medium uppercase tracking-widest text-muted-foreground"
            >
              Month total
            </th>
            {COLUMNS.map((c) => (
              <td key={c.key} className="whitespace-nowrap px-3 py-3 text-right font-semibold tabular">
                {fmt(c, totals[c.key])}
              </td>
            ))}
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

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
    return <div className="rounded-lg bg-muted/60 px-4 py-8 text-center text-sm text-muted-foreground">This month has not started yet.</div>;
  }

  const props = { days, byDate, today, selected, onPick, totals };
  return (
    <>
      <div className="lg:hidden">
        <CompactTable {...props} />
      </div>
      <div className="hidden lg:block">
        <FullTable {...props} />
      </div>
    </>
  );
}
