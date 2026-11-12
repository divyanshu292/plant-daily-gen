import { CaretRightIcon, UploadSimpleIcon, WarningIcon } from '@phosphor-icons/react';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/lib/auth';
import { addDays, fmtDate, fmtNum, parseIso } from '@/lib/format';

function daysBetween(fromIso, toIso) {
  return Math.round((parseIso(toIso) - parseIso(fromIso)) / 86_400_000);
}

/** "11 Nov has no report yet." / "11–13 Nov have no reports yet." for the days after `date`, before today. */
function missingText(date, today) {
  const first = addDays(date, 1);
  const last = addDays(today, -1);
  if (first === last) return `${fmtDate(first, 'short')} has no report yet.`;
  const from = first.slice(0, 7) === last.slice(0, 7) ? String(Number(first.slice(8))) : fmtDate(first, 'short');
  return `${from}–${fmtDate(last, 'short')} have no reports yet.`;
}

/**
 * How old the latest report is. The page for a day is printed the next morning,
 * so data running to yesterday is current; two days or more is stale.
 */
export function staleness(date, today, staleItem) {
  const age = date && today ? daysBetween(date, today) : null;
  const stale = !!staleItem || (age != null && age >= 2);
  return { age, stale };
}

/** "10 Nov · 7.32 MU · PLF 72.6 %", opening that day's report; plus an upload prompt when stale (for those who can upload). */
export function LatestReport({ date, today, day, staleItem, navigate }) {
  const { canEdit } = useAuth();
  const { age, stale } = staleness(date, today, staleItem);

  return (
    <section aria-label="Latest report" className="space-y-2">
      <button
        type="button"
        onClick={() => navigate(`daily/${date}`)}
        className="flex min-h-[52px] w-full items-center gap-3 rounded-lg border border-border bg-card px-4 py-2 text-left transition-colors hover:bg-accent/60 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
      >
        <span className="min-w-0 flex-1">
          <span className="block text-[10px] font-medium uppercase tracking-widest text-muted-foreground">Latest report</span>
          <span className="block truncate text-sm font-medium tabular">
            {fmtDate(date, 'short')}
            {day?.gen != null && (
              <>
                <span className="text-muted-foreground"> · </span>
                {fmtNum(day.gen, 2)} MU
              </>
            )}
            {day?.plf != null && (
              <>
                <span className="text-muted-foreground"> · </span>
                PLF {fmtNum(day.plf, 1)} %
              </>
            )}
          </span>
        </span>
        <CaretRightIcon weight="bold" className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
      </button>

      {stale && (
        <div className="space-y-3 rounded-lg border border-attention/40 bg-attention/[0.07] p-3 sm:flex sm:items-center sm:gap-3 sm:space-y-0 sm:py-2 sm:pr-2">
          <div className="flex min-w-0 flex-1 gap-3 sm:pl-1">
            <WarningIcon weight="fill" className="mt-0.5 h-4 w-4 shrink-0 text-attention" aria-hidden="true" />
            <div className="min-w-0 text-sm leading-snug">
              <div className="font-medium">
                {staleItem?.title || (age != null ? `Latest data is ${age} days old` : 'Latest data is out of date')}
              </div>
              {(staleItem?.detail || (!staleItem && age >= 2)) && (
                <div className="mt-0.5 text-xs text-muted-foreground">{staleItem?.detail || missingText(date, today)}</div>
              )}
            </div>
          </div>
          {canEdit && (
            <Button variant="outline" className="h-11 w-full shrink-0 border-attention/40 bg-transparent sm:w-auto" onClick={() => navigate('upload')}>
              <UploadSimpleIcon weight="bold" aria-hidden="true" />
              Upload report
            </Button>
          )}
        </div>
      )}
    </section>
  );
}
