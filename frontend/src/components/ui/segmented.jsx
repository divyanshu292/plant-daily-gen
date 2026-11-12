import { cn } from '@/lib/utils';

/**
 * A row of mutually exclusive choices (Day | Month | Year).
 * options: [{ value, label }]. 44 px tall so it is easy to hit with a thumb.
 */
export function Segmented({ options, value, onChange, className, 'aria-label': ariaLabel }) {
  return (
    <div role="radiogroup" aria-label={ariaLabel} className={cn('flex h-11 rounded-lg bg-muted p-1', className)}>
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(o.value)}
            className={cn(
              'min-w-0 flex-1 truncate rounded-md px-2 text-[13px] font-medium transition-colors',
              'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring',
              active ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'
            )}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
