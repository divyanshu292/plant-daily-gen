import { cn } from '@/lib/utils';
import { PRINTED_ROWS, rawCell } from '@/lib/fields';
import { fmtHours, fmtNum, printedDecimals, printedNumber } from '@/lib/format';

const COLUMNS = ['Unit 1', 'Unit 2', 'Station'];

function correctedText(entryValue, printed, kind) {
  if (kind === 'hours') return fmtHours(entryValue);
  return fmtNum(entryValue, printedDecimals(printed)).replace(/,/g, '');
}

function SlotCell({ slot, raw, entry, showCorrections, kind }) {
  if (!slot) return <td className="border-l border-border/60 px-1.5 py-2 sm:px-3" />;
  const printed = rawCell(raw, slot.cell);
  const stored = slot.field ? entry?.[slot.field] : undefined;
  const printedValue = printedNumber(printed);
  const corrected =
    showCorrections &&
    stored != null &&
    (printedValue == null || Math.abs(printedValue - stored) > 1e-9);
  const pct = slot.pct ? rawCell(raw, slot.pct) : null;
  const split = slot.split ? rawCell(raw, slot.split) : null;
  const blank = printed == null || printed === '';

  return (
    <td className="border-l border-border/60 px-1.5 py-2 text-right align-top sm:px-3">
      {slot.sub && <div className="text-[9px] uppercase tracking-wide text-muted-foreground sm:text-[10px] sm:tracking-wider">{slot.sub}</div>}
      {corrected ? (
        <>
          <div className="font-medium tabular">{correctedText(stored, printed, kind)}</div>
          <div className="text-[10px] text-muted-foreground">
            read as <span className="line-through tabular">{blank ? 'blank' : printed}</span>
          </div>
        </>
      ) : (
        <div className={cn('tabular', blank ? 'text-muted-foreground/50' : 'font-medium')}>{blank ? '—' : printed}</div>
      )}
      {(pct || split) && (
        <div className="text-[11px] text-muted-foreground tabular">
          {pct ? `${pct.replace(/%$/, '')}%` : `(${split})`}
        </div>
      )}
    </td>
  );
}

/**
 * Rows 4 to 15, 28 and 31 of the page, as read. With showCorrections, cells the
 * person corrected before saving show the stored value and what was read.
 */
export function PrintedForm({ raw, entry, showCorrections = false }) {
  if (!raw) return null;
  return (
    <div className="overflow-x-auto rounded-lg border border-border scroll-thin">
      <table className="w-full border-collapse text-[12.5px] sm:text-sm">
        <thead>
          <tr className="border-b border-border bg-muted/40 text-[9px] font-medium uppercase tracking-wide text-muted-foreground sm:text-[10px] sm:tracking-widest">
            <th className="hidden w-10 px-3 py-2 text-left font-medium sm:table-cell">No.</th>
            <th className="px-2 py-2 text-left font-medium sm:px-3">
              Particulars
            </th>
            <th className="hidden px-3 py-2 text-left font-medium md:table-cell">Unit</th>
            {COLUMNS.map((c) => (
              <th key={c} className="border-l border-border/60 px-1.5 py-2 text-right font-medium sm:px-3">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {PRINTED_ROWS.map((row) => (
            <tr key={row.no} className="border-b border-border/60 last:border-0">
              <td className="hidden px-3 py-2 align-top text-muted-foreground tabular sm:table-cell">{row.no}</td>
              <td className="px-2 py-2 align-top hyphens-auto sm:px-3">
                <div className="leading-snug">{row.label}</div>
                <div className="text-[11px] text-muted-foreground md:hidden">{row.unit}</div>
              </td>
              <td className="hidden px-3 py-2 align-top text-muted-foreground md:table-cell">{row.unit}</td>
              {row.slots.map((slot, i) => (
                <SlotCell key={i} slot={slot} raw={raw} entry={entry} showCorrections={showCorrections} kind={row.kind} />
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
