import { useState } from 'react';
import { Check, ChevronDown, TriangleAlert, X } from 'lucide-react';
import { cn } from '@/lib/utils';

export function CheckRow({ check }) {
  const warn = check.severity !== 'error';
  const Icon = check.ok ? Check : warn ? TriangleAlert : X;
  return (
    <li className="flex gap-2.5 py-2">
      <Icon
        className={cn(
          'mt-0.5 h-3.5 w-3.5 shrink-0',
          check.ok ? 'text-muted-foreground' : 'text-attention'
        )}
        aria-label={check.ok ? 'Passed' : warn ? 'Warning' : 'Failed'}
      />
      <div className="min-w-0 text-sm">
        <div className={cn('leading-snug', !check.ok && 'font-medium')}>
          {check.label}
          {!check.ok && warn && (
            <span className="ml-2 text-[10px] font-medium uppercase tracking-widest text-muted-foreground">
              warning only
            </span>
          )}
        </div>
        {check.detail && <div className="text-xs text-muted-foreground tabular">{check.detail}</div>}
      </div>
    </li>
  );
}

/** "31 of 31 checks passed", failed ones listed, the rest behind a toggle. */
export function ChecksSummary({ checks = [], note }) {
  const [open, setOpen] = useState(false);
  if (!checks.length) return null;
  const failed = checks.filter((c) => !c.ok);
  const passed = checks.length - failed.length;
  const title =
    failed.length === 0 ? `All ${checks.length} checks passed` : `${passed} of ${checks.length} checks passed`;

  return (
    <div className="rounded-lg border border-border">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-accent/50"
      >
        {failed.length === 0 ? (
          <Check className="h-4 w-4 shrink-0" />
        ) : (
          <TriangleAlert className="h-4 w-4 shrink-0 text-attention" />
        )}
        <div className="min-w-0 flex-1">
          <div className="text-sm font-medium">{title}</div>
          <div className="text-xs text-muted-foreground">
            {note || 'Totals, ratios and month-to-date figures on the page, re-worked from the values read.'}
          </div>
        </div>
        <span className="hidden text-xs text-muted-foreground sm:inline">{open ? 'Hide' : 'Show all'}</span>
        <ChevronDown className={cn('h-4 w-4 shrink-0 text-muted-foreground transition-transform', open && 'rotate-180')} />
      </button>
      {(open || failed.length > 0) && (
        <ul className="divide-y divide-border/60 border-t border-border px-4">
          {(open ? [...failed, ...checks.filter((c) => c.ok)] : failed).map((c, i) => (
            <CheckRow key={`${c.id}-${i}`} check={c} />
          ))}
        </ul>
      )}
    </div>
  );
}
