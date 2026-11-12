import { CaretDownIcon, CaretLeftIcon, CaretRightIcon } from '@phosphor-icons/react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { addDays, fmtDate, isIsoDate } from '@/lib/format';

/**
 * Previous day / date / next day. The arrows are 44 px; the date in the middle
 * opens the system date picker (a native date input lies over it).
 */
export function DateNav({ value, onChange, max, min, className }) {
  const prev = addDays(value, -1);
  const next = addDays(value, 1);
  return (
    <div className={cn('flex items-center gap-2', className)}>
      <Button
        variant="outline"
        size="icon"
        className="h-11 w-11 shrink-0 rounded-full"
        onClick={() => onChange(prev)}
        disabled={min ? prev < min : false}
        aria-label="Previous day"
      >
        <CaretLeftIcon weight="bold" />
      </Button>
      <label
        className={cn(
          'relative flex h-11 min-w-0 flex-1 cursor-pointer items-center justify-center gap-1.5 rounded-full px-3 transition-colors md:w-52 md:flex-none',
          'hover:bg-accent focus-within:ring-1 focus-within:ring-ring'
        )}
      >
        <span className="truncate text-[15px] font-medium tabular">{fmtDate(value, 'weekdayYear')}</span>
        <CaretDownIcon weight="bold" className="h-3 w-3 shrink-0 text-muted-foreground" />
        <input
          type="date"
          value={value}
          max={max}
          min={min}
          onChange={(e) => isIsoDate(e.target.value) && onChange(e.target.value)}
          onClick={(e) => {
            try {
              e.currentTarget.showPicker?.();
            } catch {
              // Some browsers refuse outside a direct gesture; the input still works by keyboard.
            }
          }}
          aria-label="Date"
          className="absolute inset-0 h-full w-full cursor-pointer appearance-none opacity-0 [color-scheme:light] dark:[color-scheme:dark]"
        />
      </label>
      <Button
        variant="outline"
        size="icon"
        className="h-11 w-11 shrink-0 rounded-full"
        onClick={() => onChange(next)}
        disabled={max ? next > max : false}
        aria-label="Next day"
      >
        <CaretRightIcon weight="bold" />
      </Button>
    </div>
  );
}
