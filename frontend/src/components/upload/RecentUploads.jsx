import { useState } from 'react';
import { ArrowClockwiseIcon, CaretRightIcon, CircleNotchIcon } from '@phosphor-icons/react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Notice } from '@/components/common/Notice';
import { SectionTitle } from '@/components/common/Text';
import { StatusBadge } from '@/components/common/StatusBadge';
import { fmtDate, fmtDateTime } from '@/lib/format';

const PAGE = 8;

/** Reports already uploaded, newest first. Opening one shows its result card above. */
export function RecentUploads({ reports, onOpen }) {
  const [shown, setShown] = useState(PAGE);
  const list = reports.data || [];

  return (
    <section className="space-y-3">
      <SectionTitle title="Recent uploads" hint="Open one to see what was read, or to finish a review.">
        {reports.loading && <CircleNotchIcon weight="bold" className="h-4 w-4 animate-spin text-muted-foreground" />}
      </SectionTitle>

      {reports.error && (
        <Notice
          tone="error"
          title="Could not load recent uploads"
          action={
            <Button variant="outline" size="sm" onClick={reports.reload}>
              <ArrowClockwiseIcon weight="bold" />
              Try again
            </Button>
          }
        >
          {reports.error.message}
        </Notice>
      )}

      {!reports.error && !reports.loading && list.length === 0 && (
        <Card className="px-4 py-6 text-center text-sm text-muted-foreground">No pages uploaded yet.</Card>
      )}

      {list.length > 0 && (
        <Card className="divide-y divide-border overflow-hidden">
          {list.slice(0, shown).map((r) => (
            <button
              key={r.id}
              type="button"
              onClick={() => onOpen(r)}
              className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-accent/50 focus-visible:bg-accent/50 focus-visible:outline-none md:px-5"
            >
              <StatusBadge status={r.status} className="w-[104px] justify-center" />
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium">
                  {r.dataDate ? `Data for ${fmtDate(r.dataDate, 'weekdayYear')}` : 'Date not read'}
                </div>
                <div className="truncate text-xs text-muted-foreground">
                  {r.reportDate ? `Page dated ${fmtDate(r.reportDate, 'short')}` : 'Page date not read'}
                  <span className="hidden sm:inline"> · {r.fileName}</span>
                </div>
              </div>
              <div className="hidden shrink-0 text-right text-xs text-muted-foreground tabular sm:block">
                {fmtDateTime(r.createdAt)}
                {r.confirmedAt && <div>reviewed</div>}
              </div>
              <CaretRightIcon weight="bold" className="h-4 w-4 shrink-0 text-muted-foreground" />
            </button>
          ))}
        </Card>
      )}

      {list.length > shown && (
        <Button variant="ghost" size="sm" onClick={() => setShown((n) => n + PAGE * 2)}>
          Show more ({list.length - shown} older)
        </Button>
      )}
    </section>
  );
}
