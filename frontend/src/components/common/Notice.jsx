import { CircleAlert, CircleCheck, Info, TriangleAlert } from 'lucide-react';
import { cn } from '@/lib/utils';

const TONES = {
  info: { icon: Info, box: 'border-border bg-muted/40', icon_: 'text-muted-foreground' },
  attention: { icon: TriangleAlert, box: 'border-attention/40 bg-attention/[0.07]', icon_: 'text-attention' },
  error: { icon: CircleAlert, box: 'border-attention/40 bg-attention/[0.07]', icon_: 'text-attention' },
  success: { icon: CircleCheck, box: 'border-border bg-muted/40', icon_: 'text-foreground' },
};

/** A short message block. `title` is the plain statement, children add detail. */
export function Notice({ tone = 'info', title, children, action, className, icon }) {
  const t = TONES[tone] || TONES.info;
  const Icon = icon || t.icon;
  return (
    <div className={cn('flex gap-3 rounded-lg border px-4 py-3 text-sm', t.box, className)} role={tone === 'error' ? 'alert' : undefined}>
      <Icon className={cn('mt-0.5 h-4 w-4 shrink-0', t.icon_)} />
      <div className="min-w-0 flex-1 space-y-1">
        {title && <div className="font-medium leading-snug">{title}</div>}
        {children && <div className="leading-relaxed text-muted-foreground [&_strong]:font-medium [&_strong]:text-foreground">{children}</div>}
        {action && <div className="pt-1">{action}</div>}
      </div>
    </div>
  );
}
