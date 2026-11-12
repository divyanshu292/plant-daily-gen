import { Card } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { MicroLabel } from '@/components/common/Text';

export function StatTile({ label, value, unit, caption, className }) {
  return (
    <Card className={cn('min-w-0 p-4 md:p-5', className)}>
      <MicroLabel className="leading-snug">{label}</MicroLabel>
      <div className="mt-2 flex flex-wrap items-baseline gap-x-1.5">
        <div className="text-2xl font-semibold tracking-tight tabular md:text-3xl">{value}</div>
        {unit && <div className="text-xs text-muted-foreground">{unit}</div>}
      </div>
      {caption && <div className="mt-1.5 text-[11px] leading-snug text-muted-foreground">{caption}</div>}
    </Card>
  );
}
