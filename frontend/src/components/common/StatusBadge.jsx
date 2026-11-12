import { CircleNotchIcon } from '@phosphor-icons/react';
import { cn } from '@/lib/utils';

const STYLES = {
  saved: { label: 'Saved', className: 'border-transparent bg-foreground text-background' },
  needs_review: { label: 'Needs review', className: 'border-transparent bg-attention text-attention-foreground' },
  error: { label: 'Not read', className: 'border-attention/60 text-attention' },
  queued: { label: 'Waiting', className: 'border-border text-muted-foreground' },
  preparing: { label: 'Preparing', className: 'border-border text-foreground', spin: true },
  reading: { label: 'Reading', className: 'border-border text-foreground', spin: true },
  loading: { label: 'Loading', className: 'border-border text-muted-foreground', spin: true },
};

export function StatusBadge({ status, className }) {
  const s = STYLES[status] || { label: status, className: 'border-border text-muted-foreground' };
  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-md border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-widest',
        s.className,
        className
      )}
    >
      {s.spin && <CircleNotchIcon weight="bold" className="h-3 w-3 animate-spin" />}
      {s.label}
    </span>
  );
}
