import { ArrowClockwiseIcon, XIcon } from '@phosphor-icons/react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Notice } from '@/components/common/Notice';
import { StatusBadge } from '@/components/common/StatusBadge';
import { SavedResult } from '@/components/upload/SavedResult';
import { ReviewForm } from '@/components/upload/ReviewForm';
import { useElapsed } from '@/lib/hooks';
import { fmtBytes } from '@/lib/image';
import { fmtDateTime } from '@/lib/format';

function Progress({ item, ahead }) {
  const reading = item.state === 'reading';
  const elapsed = useElapsed(item.startedAt, reading);

  let title;
  let detail;
  if (item.state === 'queued') {
    title = 'Waiting';
    detail = ahead > 0 ? `Will be read after the ${ahead === 1 ? 'page' : `${ahead} pages`} ahead of it.` : 'Starting.';
  } else if (item.state === 'preparing') {
    title = 'Preparing the image';
    detail = 'Shrinking it if it is large, so the upload stays under the 4.5 MB limit.';
  } else if (item.state === 'loading') {
    title = 'Loading the saved report';
  } else {
    title = 'Reading the page and checking its sums';
    detail =
      elapsed < 60
        ? 'This usually takes 10 to 40 seconds. You can switch screens; the result will be here when you come back.'
        : 'This is taking longer than usual. The server has not answered yet.';
  }

  return (
    <div className="space-y-3">
      <div className="flex items-baseline justify-between gap-3">
        <div className="text-base font-medium">{title}</div>
        {reading && <div className="shrink-0 whitespace-nowrap text-sm text-muted-foreground tabular">{elapsed} s</div>}
      </div>
      {detail && <p className="text-sm text-muted-foreground">{detail}</p>}
      {item.prepared && (
        <p className="text-xs text-muted-foreground tabular">
          Resized from {item.prepared.from.w} × {item.prepared.from.h} ({fmtBytes(item.prepared.from.bytes)}) to{' '}
          {item.prepared.to.w} × {item.prepared.to.h} ({fmtBytes(item.prepared.to.bytes)}).
        </p>
      )}
      {item.state !== 'queued' && (
        <div className="h-1 overflow-hidden rounded-full bg-muted" role="progressbar" aria-label={title}>
          <div className="h-full w-1/3 animate-indeterminate rounded-full bg-foreground/70" />
        </div>
      )}
    </div>
  );
}

/** One uploaded (or reopened) page: progress, error, saved result or review form. */
export function UploadItem({ item, ahead, queue, navigate }) {
  const report = item.report;
  const subtitle =
    item.kind === 'history' && report?.createdAt
      ? `Uploaded ${fmtDateTime(report.createdAt)}`
      : report?.createdAt
        ? `Read ${fmtDateTime(report.createdAt)}${report.attempts > 1 ? ` · ${report.attempts} attempts` : ''}`
        : null;
  const canRemove = !['preparing', 'reading'].includes(item.state);

  return (
    <Card id={item.key} className="scroll-mt-20">
      <div className="flex items-center gap-3 border-b border-border px-3 py-3 sm:px-4 md:px-6">
        <StatusBadge status={item.state} />
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium" title={item.name}>
            {item.name}
          </div>
          {subtitle && <div className="text-[11px] text-muted-foreground">{subtitle}</div>}
        </div>
        {canRemove && (
          <Button
            variant="ghost"
            size="icon"
            className="-my-1 -mr-2 h-10 w-10 shrink-0 md:my-0 md:mr-0 md:h-8 md:w-8"
            onClick={() => queue.remove(item.key)}
            aria-label={item.state === 'queued' ? 'Cancel this upload' : 'Close'}
            title={item.state === 'queued' ? 'Cancel this upload' : 'Close'}
          >
            <XIcon weight="bold" />
          </Button>
        )}
      </div>

      <div className="p-3 sm:p-4 md:p-6">
        {['queued', 'preparing', 'reading', 'loading'].includes(item.state) && <Progress item={item} ahead={ahead} />}

        {item.state === 'error' && (
          <div className="space-y-3">
            <Notice tone="error" title={item.kind === 'history' ? 'Could not load this report' : 'Not saved'}>
              {item.error}
            </Notice>
            {(item.file || item.reloadId) && (
              <Button variant="outline" size="sm" onClick={() => queue.retry(item.key)}>
                <ArrowClockwiseIcon weight="bold" />
                Try again
              </Button>
            )}
          </div>
        )}

        {item.state === 'saved' && report && <SavedResult report={report} navigate={navigate} />}

        {item.state === 'needs_review' && report && (
          <ReviewForm report={report} onConfirmed={(saved) => queue.markConfirmed(item.key, saved)} />
        )}
      </div>
    </Card>
  );
}
