import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { cn } from '@/lib/utils';

const METRICS = [
  { key: 'Gen', label: 'GEN' },
  { key: 'Trip', label: 'TRIP' },
  { key: 'Btl', label: 'BTL' },
  { key: 'Fo', label: 'FO' },
  { key: 'Po', label: 'PO' },
];

export const COLUMNS = METRICS.flatMap(({ key, label }) => [
  { key: `u1${key}`, label: `U1 ${label}` },
  { key: `u2${key}`, label: `U2 ${label}` },
  { key: `stn${key}`, label: `STN ${label}`, computed: true },
]);

function displayDate(iso) {
  const [y, m, d] = iso.split('-');
  return `${d}/${m}/${y}`;
}
function weekdayShort(iso) {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d).toLocaleDateString('en-US', { weekday: 'short' });
}
function formatNum(n) {
  if (n == null || Number.isNaN(n)) return '';
  const rounded = Math.round(n * 100) / 100;
  return rounded.toLocaleString('en-IN');
}

export default function DataTable({ rows, entries, onUpdate }) {
  return (
    <div className="relative rounded-xl border border-border bg-card">
      <div className="max-h-[70vh] overflow-auto scroll-thin">
        <Table className="min-w-[960px]">
          <TableHeader>
            <TableRow className="border-b border-border">
              <TableHead className="sticky left-0 top-0 z-30 h-12 bg-card pl-5 pr-4 text-foreground">
                Date
              </TableHead>
              {COLUMNS.map((c) => (
                <TableHead
                  key={c.key}
                  className={cn(
                    'sticky top-0 z-20 bg-card text-center',
                    c.computed && 'text-foreground'
                  )}
                >
                  {c.label}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((date) => {
              const entry = entries[date] || {};
              return (
                <TableRow key={date} className="group">
                  <TableCell className="sticky left-0 z-10 whitespace-nowrap border-r border-border bg-card pl-5 pr-4 py-3">
                    <div className="text-sm font-medium leading-none tabular">
                      {displayDate(date)}
                    </div>
                    <div className="mt-1 text-[10px] uppercase tracking-widest text-muted-foreground">
                      {weekdayShort(date)}
                    </div>
                  </TableCell>

                  {COLUMNS.map((col) => {
                    if (col.computed) {
                      const suffix = col.key.replace('stn', '');
                      const u1 = entry['u1' + suffix];
                      const u2 = entry['u2' + suffix];
                      const hasValue = u1 != null || u2 != null;
                      const sum = (u1 ?? 0) + (u2 ?? 0);
                      return (
                        <TableCell
                          key={col.key}
                          className="border-l border-border/40 bg-muted/30 px-4 py-3 text-center text-sm font-medium tabular"
                        >
                          {hasValue ? formatNum(sum) : ''}
                        </TableCell>
                      );
                    }
                    return (
                      <TableCell key={col.key} className="border-l border-border/40 p-0">
                        <input
                          type="number"
                          step="any"
                          inputMode="decimal"
                          value={entry[col.key] ?? ''}
                          onChange={(e) => onUpdate(date, col.key, e.target.value)}
                          placeholder="—"
                          className={cn(
                            'no-spin block h-12 w-full min-w-[88px] bg-transparent px-3 text-center text-sm tabular',
                            'placeholder:text-muted-foreground/35',
                            'focus:bg-accent focus:text-accent-foreground focus:outline-none',
                            'focus:ring-1 focus:ring-ring focus:ring-inset'
                          )}
                        />
                      </TableCell>
                    );
                  })}
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
