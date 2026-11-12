import { useEffect, useRef } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { fyMonths, fyOfMonth } from '@/lib/format';

const FY_FIRST = 2021;

/** Fiscal-year select (April to March) and a strip of its twelve months. */
export function FyMonthPicker({ month, onChange, todayMonth }) {
  const fy = fyOfMonth(month);
  const lastFy = Math.max(fyOfMonth(todayMonth), fy);
  const years = Array.from({ length: lastFy - FY_FIRST + 1 }, (_, i) => lastFy - i);
  const months = fyMonths(fy);
  const idx = months.findIndex((m) => m.value === month);
  const stripRef = useRef(null);

  // Keep the chosen month in view on narrow screens.
  useEffect(() => {
    const strip = stripRef.current;
    const el = strip?.querySelector('[aria-current="true"]');
    if (!strip || !el) return;
    strip.scrollTo({ left: el.offsetLeft - strip.clientWidth / 2 + el.clientWidth / 2, behavior: 'smooth' });
  }, [month]);

  const pickFy = (next) => {
    // Same month of the chosen year, or April.
    const sameMonth = fyMonths(next).find((m) => m.value.slice(5) === month.slice(5));
    onChange(sameMonth && sameMonth.value <= todayMonth ? sameMonth.value : `${next}-04`);
  };

  const shift = (delta) => {
    const [y, m] = month.split('-').map(Number);
    const d = new Date(y, m - 1 + delta, 1);
    onChange(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`);
  };

  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
      <label className="relative inline-flex w-fit items-center">
        <span className="pointer-events-none absolute left-3 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
          FY
        </span>
        <select
          value={fy}
          onChange={(e) => pickFy(Number(e.target.value))}
          aria-label="Fiscal year"
          className={cn(
            'h-10 cursor-pointer appearance-none rounded-md border border-border bg-card pl-9 pr-9 text-sm font-medium tabular',
            'transition-colors hover:border-foreground/40',
            'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 focus:ring-offset-background'
          )}
        >
          {years.map((y) => (
            <option key={y} value={y}>
              {y}–{String(y + 1).slice(2)}
            </option>
          ))}
        </select>
        <ChevronRight className="pointer-events-none absolute right-3 h-3.5 w-3.5 rotate-90 text-muted-foreground" />
      </label>

      <div className="flex min-w-0 flex-1 items-center gap-2">
        <Button variant="outline" size="icon" onClick={() => shift(-1)} aria-label="Previous month" className="shrink-0">
          <ChevronLeft />
        </Button>
        <div ref={stripRef} className="scroll-thin relative -mx-1 flex min-w-0 flex-1 items-center gap-1 overflow-x-auto px-1 py-0.5">
          {months.map((m) => {
            const active = m.value === month;
            const future = m.value > todayMonth;
            return (
              <button
                key={m.value}
                type="button"
                onClick={() => onChange(m.value)}
                aria-current={active ? 'true' : undefined}
                className={cn(
                  'relative shrink-0 rounded-md px-3 py-2 text-sm font-medium transition-colors md:px-4',
                  active
                    ? 'bg-foreground text-background'
                    : future
                      ? 'text-muted-foreground/50 hover:bg-accent hover:text-accent-foreground'
                      : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                )}
              >
                <span>{m.label}</span>
                <span className="ml-1 text-[10px] opacity-60">{m.value.slice(2, 4)}</span>
              </button>
            );
          })}
        </div>
        <Button
          variant="outline"
          size="icon"
          onClick={() => shift(1)}
          disabled={idx === -1}
          aria-label="Next month"
          className="shrink-0"
        >
          <ChevronRight />
        </Button>
      </div>
    </div>
  );
}
