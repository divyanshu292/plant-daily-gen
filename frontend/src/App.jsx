import { useCallback, useEffect, useMemo, useRef } from 'react';
import { ArrowClockwiseIcon } from '@phosphor-icons/react';
import { Button } from '@/components/ui/button';
import { AppHeader, navFor, TabBar } from '@/components/AppNav';
import { Notice } from '@/components/common/Notice';
import { HomeScreen } from '@/components/home/HomeScreen';
import { UploadScreen } from '@/components/upload/UploadScreen';
import { useUploadQueue } from '@/components/upload/useUploadQueue';
import { DailyScreen } from '@/components/daily/DailyScreen';
import { DataScreen } from '@/components/data/DataScreen';
import { AccountScreen } from '@/components/account/AccountScreen';
import { UsersScreen } from '@/components/users/UsersScreen';
import { useAuth } from '@/lib/auth';
import { useApiData, useHashRoute } from '@/lib/hooks';
import { fmtDate } from '@/lib/format';

export default function App() {
  const { route: asked, navigate, backTo } = useHashRoute();
  const { canEdit, isSuperAdmin } = useAuth();
  const items = useMemo(() => navFor({ canEdit, isSuperAdmin }), [canEdit, isSuperAdmin]);

  // A screen this person may not open (a viewer on #/upload, anyone but the super admin on #/users)
  // shows Home at once, and the address follows without adding a history entry.
  const allowed = items.some((n) => n.screen === asked.screen);
  const route = allowed ? asked : { screen: 'home', arg: null, hash: '#/home' };
  useEffect(() => {
    if (!allowed) navigate('home', { replace: true });
  }, [allowed, navigate]);

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

  // Choosing the screen you are already on scrolls back to its top (and to its first view), as native tab bars do.
  const goScreen = useCallback(
    (screen) => {
      if (screen === route.screen) window.scrollTo({ top: 0, behavior: 'smooth' });
      if (screen !== route.screen || route.arg) navigate(screen);
    },
    [navigate, route.screen, route.arg]
  );

  const nav = { items, screen: route.screen, onNavigate: goScreen, uploading: queue.busy, pendingReview: queue.pendingReview };

  return (
    <div className="min-h-dvh bg-background text-foreground">
      <AppHeader {...nav} />

      <main className="pad-x-safe mx-auto max-w-[1280px] space-y-8 pb-[calc(var(--tabbar-h)+1.5rem)] pt-5 md:pb-10 md:pt-12">
        {health.error && (
          <Notice
            tone="error"
            title="Cannot reach the server"
            action={
              <Button variant="outline" size="sm" onClick={health.reload}>
                <ArrowClockwiseIcon weight="bold" />
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

        {route.screen === 'home' && <HomeScreen health={health} navigate={navigate} />}
        {route.screen === 'upload' && canEdit && <UploadScreen queue={queue} health={health} navigate={navigate} />}
        {route.screen === 'daily' && <DailyScreen arg={route.arg} health={health} navigate={navigate} />}
        {route.screen === 'data' && (
          <DataScreen arg={route.arg} health={health} navigate={navigate} backTo={backTo} onDataChanged={health.reload} />
        )}
        {route.screen === 'users' && isSuperAdmin && <UsersScreen />}
        {route.screen === 'account' && <AccountScreen />}

        <footer className="hidden items-center justify-between gap-4 border-t border-border pt-5 text-[10px] uppercase tracking-widest text-muted-foreground md:flex">
          <span>Tenughat Thermal Power Station · TVNL</span>
          {health.data?.latestDate && <span>Latest data · {fmtDate(health.data.latestDate, 'medium')}</span>}
        </footer>
      </main>

      <TabBar {...nav} />
    </div>
  );
}
