import { useEffect, useState } from 'react';
import { Card } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { apiFetch } from '@/lib/api';

const POLL_MS = 2_000;

const IST_FORMATTER = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Asia/Kolkata',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
});

function useNowIST() {
  const [now, setNow] = useState(() => IST_FORMATTER.format(new Date()));
  useEffect(() => {
    const id = setInterval(() => setNow(IST_FORMATTER.format(new Date())), 1000);
    return () => clearInterval(id);
  }, []);
  return now;
}

export default function LiveGeneration() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);
  const now = useNowIST();

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const res = await apiFetch('/live-generation');
        if (!res.ok) throw new Error();
        const json = await res.json();
        if (cancelled) return;
        setData(json);
        setError(false);
      } catch {
        if (!cancelled) setError(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    const id = setInterval(load, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const u1 = data?.[0];
  const u2 = data?.[1];

  return (
    <section className="space-y-4">
      <div className="flex items-end justify-between">
        <div>
          <div className="text-[11px] font-medium uppercase tracking-widest text-muted-foreground">
            Live Generation
          </div>
          <div className="mt-1 text-xs text-muted-foreground/80">
            Now · <span className="tabular">{now} IST</span>
          </div>
        </div>
        <LiveDot state={error ? 'error' : loading ? 'loading' : 'live'} />
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 md:gap-4">
        <UnitTile label="Unit 1" reading={u1} error={error} />
        <UnitTile label="Unit 2" reading={u2} error={error} />
      </div>
    </section>
  );
}

function UnitTile({ label, reading, error }) {
  const value = reading?.readings?.power;
  const unit = reading?.units?.power || 'MW';
  const hasValue = typeof value === 'number';

  return (
    <Card className="relative overflow-hidden p-6 md:p-8">
      <div className="flex items-start justify-between">
        <div>
          <div className="text-[11px] font-medium uppercase tracking-widest text-muted-foreground">
            {label}
          </div>
          <div className="mt-1 text-[11px] text-muted-foreground/70">
            Station power reading
          </div>
        </div>
        <div className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-widest text-muted-foreground">
          <span
            className={cn(
              'h-1.5 w-1.5 rounded-full',
              error ? 'bg-muted-foreground/40' : 'bg-foreground'
            )}
          />
          {error ? 'Stale' : 'Live'}
        </div>
      </div>

      <div className="mt-10 flex items-baseline gap-3">
        <span className="text-[clamp(48px,10vw,96px)] font-semibold leading-[0.9] tracking-tight tabular">
          {hasValue ? value : '—'}
        </span>
        <span className="text-lg font-medium text-muted-foreground">{unit}</span>
      </div>

      <div className="pointer-events-none absolute right-0 top-0 h-full w-1/2 bg-gradient-to-l from-foreground/[0.015] to-transparent" />
    </Card>
  );
}

function LiveDot({ state }) {
  const label =
    state === 'error' ? 'Connection lost' : state === 'loading' ? 'Connecting…' : 'Polling · 2s';
  return (
    <div className="flex items-center gap-2 text-[10px] font-medium uppercase tracking-widest text-muted-foreground">
      <span className="relative flex h-2 w-2">
        {state === 'live' && (
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-foreground/70" />
        )}
        <span
          className={cn(
            'relative inline-flex h-2 w-2 rounded-full',
            state === 'error' ? 'bg-muted-foreground/40' : 'bg-foreground'
          )}
        />
      </span>
      {label}
    </div>
  );
}
