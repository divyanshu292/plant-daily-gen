import { cn } from '@/lib/utils';
import { MicroLabel } from '@/components/common/Text';

/** A headline figure: small label, large number, one line of context. No box; whitespace separates tiles. */
export function StatTile({ label, value, unit, caption, className }) {
  return (
    <div className={cn('min-w-0', className)}>
      <MicroLabel className="leading-snug">{label}</MicroLabel>
      <div className="mt-1.5 flex flex-wrap items-baseline gap-x-1.5">
        <div className="text-[28px] font-semibold leading-none tracking-tight tabular md:text-3xl">{value}</div>
        {unit && <div className="text-xs text-muted-foreground">{unit}</div>}
      </div>
      {caption && <div className="mt-2 text-[11px] leading-snug text-muted-foreground">{caption}</div>}
    </div>
  );
}
