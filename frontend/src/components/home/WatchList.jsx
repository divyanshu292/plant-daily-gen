import { CaretRightIcon, CheckCircleIcon, InfoIcon, WarningCircleIcon, WarningIcon } from '@phosphor-icons/react';
import { MicroLabel } from '@/components/common/Text';
import { cn } from '@/lib/utils';

const LEVELS = {
  alert: { icon: WarningCircleIcon, className: 'text-attention', label: 'Alert' },
  warn: { icon: WarningIcon, className: 'text-attention', label: 'Warning' },
  info: { icon: InfoIcon, className: 'text-muted-foreground', label: 'Note' },
  good: { icon: CheckCircleIcon, className: 'text-foreground', label: 'Good' },
};

/** Where a watch item takes the engineer: the fix for missing data, else the day's full report. */
function linkFor(item, date) {
  if (item.key === 'staleData') return 'upload';
  if (!date) return null;
  if (item.key === 'missingDays') return `data/${date.slice(0, 7)}`;
  return `daily/${date}`;
}

export function WatchList({ items, date, navigate }) {
  return (
    <section aria-labelledby="watch-heading" className="space-y-2">
      <MicroLabel as="h2" id="watch-heading">
        Look at
      </MicroLabel>
      {items.length === 0 ? (
        <p className="border-y border-border py-3 text-sm text-muted-foreground">Nothing stands out in the latest figures.</p>
      ) : (
        <ul className="divide-y divide-border border-y border-border">
          {items.map((item) => (
            <WatchItem key={`${item.key}-${item.title}`} item={item} to={linkFor(item, date)} navigate={navigate} />
          ))}
        </ul>
      )}
    </section>
  );
}

function WatchItem({ item, to, navigate }) {
  const level = LEVELS[item.level] || LEVELS.info;
  const Icon = level.icon;
  const body = (
    <>
      <Icon weight="fill" className={cn('mt-0.5 h-4 w-4 shrink-0', level.className)} aria-hidden="true" />
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-medium leading-snug">
          <span className="sr-only">{level.label}: </span>
          {item.title}
        </span>
        {item.detail && <span className="mt-0.5 block text-xs leading-relaxed text-muted-foreground">{item.detail}</span>}
      </span>
      {to && <CaretRightIcon weight="bold" className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />}
    </>
  );
  const rowClass = 'flex min-h-[44px] w-full items-start gap-3 py-3 text-left';
  return (
    <li>
      {to ? (
        <button
          type="button"
          onClick={() => navigate(to)}
          className={cn(rowClass, 'transition-colors hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring')}
        >
          {body}
        </button>
      ) : (
        <div className={rowClass}>{body}</div>
      )}
    </li>
  );
}
