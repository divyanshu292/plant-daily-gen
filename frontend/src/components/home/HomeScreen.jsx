import { useEffect, useRef } from 'react';
import { ArrowClockwiseIcon, FileArrowUpIcon, UploadSimpleIcon } from '@phosphor-icons/react';
import { Button } from '@/components/ui/button';
import { Notice } from '@/components/common/Notice';
import { LivePanel } from '@/components/home/LivePanel';
import { LatestReport } from '@/components/home/LatestReport';
import { TargetsSection } from '@/components/home/TargetsSection';
import { WatchList } from '@/components/home/WatchList';
import { TrendList } from '@/components/home/TrendList';
import { useApiData } from '@/lib/hooks';
import { cn } from '@/lib/utils';

// The last analysis, kept across visits so coming back to Home shows it at once
// (dimmed while the fresh one loads) instead of skeletons.
let lastAnalysis = null;

/**
 * Home: live generation first, then what the stored reports say: the latest
 * day, progress against targets, things to look at, and 7-day trends.
 */
export function HomeScreen({ health, navigate }) {
  const analytics = useApiData('/analytics');
  const { reload } = analytics;
  useEffect(() => {
    if (analytics.data) lastAnalysis = analytics.data;
  }, [analytics.data]);

  // An upload or edit elsewhere moves the latest date; fetch the analysis again.
  const latestDate = health?.data?.latestDate;
  const seenLatest = useRef(latestDate);
  useEffect(() => {
    const previous = seenLatest.current;
    seenLatest.current = latestDate;
    if (previous !== undefined && latestDate !== undefined && previous !== latestDate) reload();
  }, [latestDate, reload]);

  const a = analytics.data ?? lastAnalysis;
  const today = a?.today || health?.data?.today;

  let left = null;
  let right = null;
  if (a && a.date) {
    const day = a.days?.find((d) => d.date === a.date);
    const staleItem = a.watch?.find((w) => w.key === 'staleData');
    left = (
      <>
        <LatestReport date={a.date} today={today} day={day} staleItem={staleItem} navigate={navigate} />
        {a.progress && <TargetsSection progress={a.progress} days={a.days || []} />}
      </>
    );
    right = (
      <>
        <WatchList items={(a.watch || []).filter((w) => w !== staleItem)} date={a.date} navigate={navigate} />
        {a.trends?.length > 0 && a.days?.length > 0 && <TrendList trends={a.trends} days={a.days} />}
      </>
    );
  } else if (a) {
    left = <NoData navigate={navigate} />;
  } else if (analytics.error) {
    left = (
      <Notice
        tone="error"
        title="Could not load the analysis"
        action={
          <Button variant="outline" className="h-11" onClick={reload}>
            <ArrowClockwiseIcon weight="bold" aria-hidden="true" />
            Try again
          </Button>
        }
      >
        {analytics.error.message}
      </Notice>
    );
  } else {
    left = <LeftSkeleton />;
    right = <RightSkeleton />;
  }

  // Hold the previous figures while refreshing; dim them only if it takes a moment.
  const dim = cn('transition-opacity', analytics.loading && a ? 'opacity-60 delay-300' : 'delay-0');

  return (
    <div className="lg:grid lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)] lg:gap-x-14">
      <div className="space-y-8">
        <LivePanel />
        <div className={cn('space-y-8', dim)}>
          {a && analytics.error && <ReloadFailed error={analytics.error} onRetry={reload} />}
          {left}
        </div>
      </div>
      {right && <div className={cn('mt-10 space-y-10 lg:mt-0', dim)}>{right}</div>}
    </div>
  );
}

function ReloadFailed({ error, onRetry }) {
  return (
    <Notice
      tone="error"
      title="Showing the last analysis; refreshing it failed"
      action={
        <Button variant="outline" className="h-11" onClick={onRetry}>
          <ArrowClockwiseIcon weight="bold" aria-hidden="true" />
          Try again
        </Button>
      }
    >
      {error.message}
    </Notice>
  );
}

function NoData({ navigate }) {
  return (
    <div className="space-y-4 rounded-lg border border-dashed border-border px-5 py-8 text-center">
      <FileArrowUpIcon weight="duotone" className="mx-auto h-8 w-8 text-muted-foreground" aria-hidden="true" />
      <div className="space-y-1">
        <div className="text-sm font-medium">No daily reports yet</div>
        <p className="text-xs leading-relaxed text-muted-foreground">
          Upload the first daily performance report to see targets, things to look at and trends here.
        </p>
      </div>
      <Button className="h-11" onClick={() => navigate('upload')}>
        <UploadSimpleIcon weight="bold" aria-hidden="true" />
        Upload the first report
      </Button>
    </div>
  );
}

function Bone({ className }) {
  return <div className={cn('animate-pulse rounded-md bg-muted', className)} />;
}

function LeftSkeleton() {
  return (
    <div className="space-y-8" aria-busy="true" aria-label="Loading the analysis">
      <Bone className="h-[52px] rounded-lg" />
      <div className="space-y-5">
        <Bone className="h-3 w-16" />
        {[0, 1].map((i) => (
          <div key={i} className="space-y-2">
            <div className="flex justify-between">
              <Bone className="h-4 w-24" />
              <Bone className="h-4 w-28" />
            </div>
            <Bone className="h-1.5 w-full rounded-full" />
            <Bone className="h-3 w-48" />
          </div>
        ))}
        <Bone className="h-[72px] w-full" />
      </div>
    </div>
  );
}

function RightSkeleton() {
  return (
    <div className="space-y-10" aria-hidden="true">
      <div className="space-y-3">
        <Bone className="h-3 w-14" />
        {[0, 1, 2].map((i) => (
          <div key={i} className="flex gap-3">
            <Bone className="h-4 w-4 rounded-full" />
            <div className="flex-1 space-y-1.5">
              <Bone className="h-4 w-3/4" />
              <Bone className="h-3 w-full" />
            </div>
          </div>
        ))}
      </div>
      <div className="space-y-3">
        <Bone className="h-3 w-14" />
        {[0, 1, 2, 3, 4, 5, 6].map((i) => (
          <Bone key={i} className="h-9 w-full" />
        ))}
      </div>
    </div>
  );
}
