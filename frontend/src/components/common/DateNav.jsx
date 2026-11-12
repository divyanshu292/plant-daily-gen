import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { addDays, isIsoDate } from '@/lib/format';

/** Previous day / date box / next day. */
export function DateNav({ value, onChange, max, min, className }) {
  const prev = addDays(value, -1);
  const next = addDays(value, 1);
  return (
    <div className={cn('flex items-center gap-2', className)}>
      <Button
        variant="outline"
        size="icon"
        onClick={() => onChange(prev)}
        disabled={min ? prev < min : false}
        aria-label="Previous day"
      >
        <ChevronLeft />
      </Button>
      <input
        type="date"
        value={value}
        max={max}
        min={min}
        onChange={(e) => isIsoDate(e.target.value) && onChange(e.target.value)}
        aria-label="Date"
        className={cn(
          'h-9 min-w-0 flex-1 rounded-md border border-input bg-background px-3 text-sm font-medium tabular sm:w-44 sm:flex-none',
          'hover:border-foreground/40 focus:outline-none focus:ring-1 focus:ring-ring',
          '[color-scheme:light] dark:[color-scheme:dark]'
        )}
      />
      <Button
        variant="outline"
        size="icon"
        onClick={() => onChange(next)}
        disabled={max ? next > max : false}
        aria-label="Next day"
      >
        <ChevronRight />
      </Button>
    </div>
  );
}
