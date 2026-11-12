import { CheckCircleIcon, InfoIcon, WarningCircleIcon, WarningIcon } from '@phosphor-icons/react';
import { cn } from '@/lib/utils';

// No outlines: a faint fill is enough to set a message apart. Amber only where a person has to act.
const TONES = {
  info: { icon: InfoIcon, box: 'bg-muted/60', icon_: 'text-muted-foreground' },
  attention: { icon: WarningIcon, box: 'bg-attention/[0.08]', icon_: 'text-attention' },
  error: { icon: WarningCircleIcon, box: 'bg-attention/[0.08]', icon_: 'text-attention' },
  success: { icon: CheckCircleIcon, box: 'bg-muted/60', icon_: 'text-foreground' },
};

/** A short message block. `title` is the plain statement, children add detail. */
export function Notice({ tone = 'info', title, children, action, className, icon }) {
  const t = TONES[tone] || TONES.info;
  const Icon = icon || t.icon;
  return (
    <div className={cn('flex gap-3 rounded-lg px-4 py-3 text-sm', t.box, className)} role={tone === 'error' ? 'alert' : undefined}>
      <Icon weight="fill" className={cn('mt-0.5 h-4 w-4 shrink-0', t.icon_)} />
      <div className="min-w-0 flex-1 space-y-1">
        {title && <div className="font-medium leading-snug">{title}</div>}
        {children && <div className="leading-relaxed text-muted-foreground [&_strong]:font-medium [&_strong]:text-foreground">{children}</div>}
        {action && <div className="pt-1.5">{action}</div>}
      </div>
    </div>
  );
}
