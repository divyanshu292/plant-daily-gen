import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight, Check, Loader2, Moon, Sun, TriangleAlert } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { apiFetch } from '@/lib/api';
import LiveGeneration from '@/components/LiveGeneration';
import DataTable from '@/components/DataTable';

const MONTHS = [
  { value: '2026-04', label: 'Apr' },
  { value: '2026-05', label: 'May' },
  { value: '2026-06', label: 'Jun' },
  { value: '2026-07', label: 'Jul' },
  { value: '2026-08', label: 'Aug' },
  { value: '2026-09', label: 'Sep' },
  { value: '2026-10', label: 'Oct' },
  { value: '2026-11', label: 'Nov' },
  { value: '2026-12', label: 'Dec' },
  { value: '2027-01', label: 'Jan' },
  { value: '2027-02', label: 'Feb' },
  { value: '2027-03', label: 'Mar' },
];

function daysInMonth(ym) {
  const [y, m] = ym.split('-').map(Number);
  return new Date(y, m, 0).getDate();
}
function isoDate(ym, day) {
  return `${ym}-${String(day).padStart(2, '0')}`;
}
function formatNum(n) {
  if (n == null || Number.isNaN(n)) return '0';
  const rounded = Math.round(n * 100) / 100;
  return rounded.toLocaleString('en-IN');
}

export default function App() {
  const [month, setMonth] = useState(() => {
    const now = new Date();
    const ym = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
    return MONTHS.find((m) => m.value === ym)?.value || '2026-04';
  });
  const [entries, setEntries] = useState({});
  const [status, setStatus] = useState('idle');
  const [loading, setLoading] = useState(false);
  const saveTimers = useRef({});
  const statusTimer = useRef();

  useEffect(() => {
    setLoading(true);
    apiFetch(`/entries?month=${month}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(r)))
      .then((list) => {
        const map = {};
        list.forEach((e) => {
          map[e.date] = e;
        });
        setEntries(map);
      })
      .catch(() => setStatus('error'))
      .finally(() => setLoading(false));
  }, [month]);

  const flashStatus = (next) => {
    setStatus(next);
    clearTimeout(statusTimer.current);
    if (next === 'saved') {
      statusTimer.current = setTimeout(() => setStatus('idle'), 1400);
    }
  };

  const updateCell = useCallback((date, key, value) => {
    const num = value === '' ? null : Number(value);
    if (value !== '' && Number.isNaN(num)) return;

    setEntries((prev) => ({
      ...prev,
      [date]: { ...(prev[date] || { date }), [key]: num },
    }));

    clearTimeout(saveTimers.current[date]);
    saveTimers.current[date] = setTimeout(() => {
      flashStatus('saving');
      apiFetch(`/entries/${date}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [key]: num }),
      })
        .then((r) => (r.ok ? r.json() : Promise.reject(r)))
        .then(() => flashStatus('saved'))
        .catch(() => flashStatus('error'));
    }, 500);
  }, []);

  const rows = useMemo(() => {
    const n = daysInMonth(month);
    return Array.from({ length: n }, (_, i) => isoDate(month, i + 1));
  }, [month]);

  const monthStats = useMemo(() => {
    let genU1 = 0, genU2 = 0, tripU1 = 0, tripU2 = 0, filled = 0;
    rows.forEach((d) => {
      const e = entries[d];
      if (!e) return;
      if (e.u1Gen != null || e.u2Gen != null) filled++;
      genU1 += e.u1Gen ?? 0;
      genU2 += e.u2Gen ?? 0;
      tripU1 += e.u1Trip ?? 0;
      tripU2 += e.u2Trip ?? 0;
    });
    return {
      filled,
      total: rows.length,
      genTotal: genU1 + genU2,
      tripTotal: tripU1 + tripU2,
    };
  }, [rows, entries]);

  const monthIdx = MONTHS.findIndex((m) => m.value === month);
  const currentMonthLabel = MONTHS[monthIdx];
  const year = month.split('-')[0];

  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* TOP BAR */}
      <header className="sticky top-0 z-40 border-b border-border bg-background/85 backdrop-blur-xl">
        <div className="mx-auto flex h-14 max-w-[1280px] items-center justify-between px-4 md:px-8">
          <div className="flex items-center gap-3">
            <span className="text-sm font-semibold tracking-tight">TTPS</span>
            <Badge variant="outline" className="hidden sm:inline-flex">
              Daily Data
            </Badge>
          </div>
          <div className="flex items-center gap-4">
            <SaveIndicator status={status} loading={loading} />
            <ThemeToggle />
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1280px] space-y-10 px-4 py-8 md:space-y-14 md:px-8 md:py-14">
        {/* HERO */}
        <section className="space-y-3">
          <div className="text-[11px] font-medium uppercase tracking-widest text-muted-foreground">
            Tenughat Thermal Power Station · Lalpania, Bokaro
          </div>
          <h1 className="text-4xl font-semibold leading-[1.05] tracking-tight md:text-6xl">
            Daily Generation
            <br />
            <span className="text-muted-foreground">Log · FY {year.slice(2)}–{(Number(year) + 1).toString().slice(2)}</span>
          </h1>
        </section>

        {/* LIVE GENERATION */}
        <LiveGeneration />

        {/* MONTH PICKER + STATS */}
        <section className="space-y-6">
          <MonthStrip value={month} onChange={setMonth} />

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <StatCard
              label="Progress"
              value={`${monthStats.filled}`}
              unit={`/${monthStats.total} days`}
            />
            <StatCard
              label="Station Gen"
              value={formatNum(monthStats.genTotal)}
              unit="MU"
            />
            <StatCard
              label="Total Trips"
              value={formatNum(monthStats.tripTotal)}
              unit="U1 + U2"
            />
          </div>
        </section>

        {/* DATA TABLE */}
        <section className="space-y-3">
          <div className="flex items-end justify-between">
            <div>
              <div className="text-[11px] font-medium uppercase tracking-widest text-muted-foreground">
                Data entry · {currentMonthLabel?.label} {year}
              </div>
              <div className="mt-1 text-xs text-muted-foreground/80">
                STN values auto-computed · edits save automatically
              </div>
            </div>
          </div>
          <DataTable rows={rows} entries={entries} onUpdate={updateCell} />
        </section>

        <footer className="flex flex-col items-start justify-between gap-2 border-t border-border pt-6 text-[11px] uppercase tracking-widest text-muted-foreground sm:flex-row sm:items-center">
          <span>Tenughat Thermal Power Station</span>
          <span>Fiscal year 2026–27</span>
        </footer>
      </main>
    </div>
  );
}

function MonthStrip({ value, onChange }) {
  const idx = MONTHS.findIndex((m) => m.value === value);
  const year = value.split('-')[0];
  const prev = () => idx > 0 && onChange(MONTHS[idx - 1].value);
  const next = () => idx < MONTHS.length - 1 && onChange(MONTHS[idx + 1].value);

  return (
    <div className="flex items-center gap-3">
      <Button
        variant="outline"
        size="icon"
        onClick={prev}
        disabled={idx === 0}
        aria-label="Previous month"
      >
        <ChevronLeft />
      </Button>

      <div className="scroll-thin -mx-1 flex flex-1 items-center gap-1 overflow-x-auto px-1">
        {MONTHS.map((m) => (
          <button
            key={m.value}
            onClick={() => onChange(m.value)}
            className={cn(
              'relative shrink-0 rounded-md px-4 py-2 text-sm font-medium transition-colors',
              m.value === value
                ? 'bg-foreground text-background'
                : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
            )}
          >
            <span>{m.label}</span>
            <span className="ml-1.5 text-[10px] opacity-60">
              {m.value.slice(2, 4)}
            </span>
          </button>
        ))}
      </div>

      <Button
        variant="outline"
        size="icon"
        onClick={next}
        disabled={idx === MONTHS.length - 1}
        aria-label="Next month"
      >
        <ChevronRight />
      </Button>
    </div>
  );
}

function StatCard({ label, value, unit }) {
  return (
    <Card className="p-5">
      <div className="text-[11px] font-medium uppercase tracking-widest text-muted-foreground">
        {label}
      </div>
      <div className="mt-2 flex items-baseline gap-2">
        <div className="text-3xl font-semibold tracking-tight tabular">{value}</div>
        <div className="text-xs text-muted-foreground">{unit}</div>
      </div>
    </Card>
  );
}

function useTheme() {
  const [theme, setTheme] = useState(() => {
    if (typeof window === 'undefined') return 'dark';
    return localStorage.getItem('ttps-theme') || 'dark';
  });

  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle('dark', theme === 'dark');
    root.setAttribute('data-theme', theme);
    localStorage.setItem('ttps-theme', theme);
    document
      .querySelector('meta[name="theme-color"]')
      ?.setAttribute('content', theme === 'dark' ? '#000000' : '#ffffff');
  }, [theme]);

  return [theme, setTheme];
}

function ThemeToggle() {
  const [theme, setTheme] = useTheme();
  const next = theme === 'dark' ? 'light' : 'dark';
  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={() => setTheme(next)}
      aria-label={`Switch to ${next} mode`}
      className="h-8 w-8"
    >
      {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </Button>
  );
}

function SaveIndicator({ status, loading }) {
  if (status === 'idle' && !loading) return null;
  let icon = null;
  let text = '';
  let className = 'text-muted-foreground';

  if (status === 'saving' || (loading && status === 'idle')) {
    icon = <Loader2 className="h-3 w-3 animate-spin" />;
    text = loading ? 'Loading' : 'Saving';
  } else if (status === 'saved') {
    icon = <Check className="h-3 w-3" />;
    text = 'Saved';
    className = 'text-foreground';
  } else if (status === 'error') {
    icon = <TriangleAlert className="h-3 w-3" />;
    text = 'Save failed';
    className = 'text-foreground';
  }

  return (
    <div className={cn('flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-widest', className)}>
      {icon}
      {text}
    </div>
  );
}
