import { useEffect, useRef } from 'react';
import { CaretDownIcon, CaretLeftIcon, CaretRightIcon } from '@phosphor-icons/react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { fyMonths, fyOfMonth } from '@/lib/format';

const FY_FIRST = 2021;

function sameMonthIn(fy, month, todayMonth) {
  // Same month of the chosen year, or April.
  const sameMonth = fyMonths(fy).find((m) => m.value.slice(5) === month.slice(5));
  return sameMonth && sameMonth.value <= todayMonth ? sameMonth.value : `${fy}-04`;
}

/**
 * Fiscal-year choice. A native select lies invisibly over the label, so phones get
 * their own picker; its 16 px text keeps iOS from zooming in.
 */
export function FySelect({ month, onChange, todayMonth, className }) {
  const fy = fyOfMonth(month);
  const lastFy = Math.max(fyOfMonth(todayMonth), fy);
  const years = Array.from({ length: lastFy - FY_FIRST + 1 }, (_, i) => lastFy - i);
  return (
    <label
      className={cn(
        'relative inline-flex h-11 shrink-0 cursor-pointer items-center gap-1.5 rounded-full bg-muted px-4 text-[13px] font-medium tabular transition-colors md:h-9',
        'hover:bg-accent focus-within:ring-1 focus-within:ring-ring',
        className
      )}
    >
      <span className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">FY</span>
      <span>
        {fy}–{String(fy + 1).slice(2)}
      </span>
      <CaretDownIcon weight="bold" className="h-3 w-3 text-muted-foreground" />
      <select
        value={fy}
        onChange={(e) => onChange(sameMonthIn(Number(e.target.value), month, todayMonth))}
        aria-label="Fiscal year"
        className="absolute inset-0 h-full w-full cursor-pointer appearance-none text-base opacity-0"
      >
        {years.map((y) => (
          <option key={y} value={y}>
            {y}–{String(y + 1).slice(2)}
          </option>
        ))}
      </select>
    </label>
  );
}

/**
 * Previous / next month and a strip of the fiscal year's twelve months (April to March).
 * With fySelect (the default) the fiscal-year choice sits in front of the strip.
 */
export function FyMonthPicker({ month, onChange, todayMonth, fySelect = true }) {
  const fy = fyOfMonth(month);
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

  const shift = (delta) => {
    const [y, m] = month.split('-').map(Number);
    const d = new Date(y, m - 1 + delta, 1);
    onChange(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`);
  };

  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
      {fySelect && <FySelect month={month} onChange={onChange} todayMonth={todayMonth} className="w-fit" />}

      <div className="-mx-1 flex min-w-0 flex-1 items-center gap-1 md:-ml-3 md:flex-initial">
        <Button
          variant="ghost"
          size="icon-touch"
          onClick={() => shift(-1)}
          aria-label="Previous month"
          className="shrink-0 rounded-full"
        >
          <CaretLeftIcon weight="bold" />
        </Button>
        <div
          ref={stripRef}
          className="relative flex min-w-0 flex-1 snap-x items-center gap-1 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        >
          {months.map((m) => {
            const active = m.value === month;
            const future = m.value > todayMonth;
            return (
              <button
                key={m.value}
                type="button"
                onClick={() => onChange(m.value)}
                aria-current={active ? 'true' : undefined}
                aria-label={`${m.label} ${m.value.slice(0, 4)}`}
                className={cn(
                  'relative h-11 shrink-0 snap-center rounded-full px-3.5 text-sm font-medium transition-colors md:h-9',
                  'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring',
                  active
                    ? 'bg-foreground text-background'
                    : future
                      ? 'text-muted-foreground/40 hover:bg-accent hover:text-accent-foreground'
                      : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                )}
              >
                {m.label}
                {/* January to March fall in the next calendar year. */}
                {m.value.slice(0, 4) !== String(fy) && <span className="ml-1 text-[10px] opacity-60">{m.value.slice(2, 4)}</span>}
              </button>
            );
          })}
        </div>
        <Button
          variant="ghost"
          size="icon-touch"
          onClick={() => shift(1)}
          disabled={idx === -1}
          aria-label="Next month"
          className="shrink-0 rounded-full"
        >
          <CaretRightIcon weight="bold" />
        </Button>
      </div>
    </div>
  );
}
