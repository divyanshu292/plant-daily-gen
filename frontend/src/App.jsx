import { useCallback, useEffect, useRef } from 'react';
import { RotateCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { AppHeader } from '@/components/AppHeader';
import { Notice } from '@/components/common/Notice';
import { UploadScreen } from '@/components/upload/UploadScreen';
import { useUploadQueue } from '@/components/upload/useUploadQueue';
import { DailyScreen } from '@/components/daily/DailyScreen';
import { DataScreen } from '@/components/data/DataScreen';
import { useApiData, useHashRoute } from '@/lib/hooks';
import { fmtDate } from '@/lib/format';

export default function App() {
  const { route, navigate, backTo } = useHashRoute();
  const health = useApiData('/health');
  const queue = useUploadQueue();

  // A saved upload or review can move the latest date.
  const firstVersion = useRef(queue.version);
  useEffect(() => {
    if (queue.version !== firstVersion.current) health.reload();
  }, [queue.version, health.reload]);

  // Warn before leaving while a page is still being read.
  useEffect(() => {
    if (!queue.busy) return undefined;
    const warn = (e) => {
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [queue.busy]);

  // New screen starts at the top.
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [route.screen]);

  const goScreen = useCallback((screen) => navigate(screen), [navigate]);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <AppHeader
        screen={route.screen}
        onNavigate={goScreen}
        uploading={queue.busy}
        pendingReview={queue.pendingReview}
      />

      <main className="mx-auto max-w-[1280px] space-y-8 px-4 py-6 md:px-8 md:py-12">
        {health.error && (
          <Notice
            tone="error"
            title="Cannot reach the server"
            action={
              <Button variant="outline" size="sm" onClick={health.reload}>
                <RotateCw />
                Try again
              </Button>
            }
          >
            {health.error.message}
          </Notice>
        )}
        {health.data && !health.data.database && (
          <Notice tone="error" title="The server cannot reach its database">
            Uploads and stored data will fail until the database connection is fixed.
          </Notice>
        )}

        {route.screen === 'upload' && <UploadScreen queue={queue} health={health} navigate={navigate} />}
        {route.screen === 'daily' && <DailyScreen arg={route.arg} health={health} navigate={navigate} />}
        {route.screen === 'data' && (
          <DataScreen arg={route.arg} health={health} navigate={navigate} backTo={backTo} onDataChanged={health.reload} />
        )}

        <footer className="flex flex-col items-start justify-between gap-2 border-t border-border pt-6 text-[11px] uppercase tracking-widest text-muted-foreground sm:flex-row sm:items-center">
          <span>Tenughat Thermal Power Station · TVNL</span>
          {health.data?.latestDate && <span>Latest data · {fmtDate(health.data.latestDate, 'medium')}</span>}
        </footer>
      </main>
    </div>
  );
}
