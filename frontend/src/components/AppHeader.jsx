import { CalendarDays, FileText, ImageUp, Moon, Sun } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useTheme } from '@/lib/hooks';

const NAV = [
  { screen: 'upload', label: 'Upload', short: 'Upload', icon: ImageUp },
  { screen: 'daily', label: 'Daily report', short: 'Report', icon: FileText },
  { screen: 'data', label: 'Data', short: 'Data', icon: CalendarDays },
];

function ThemeToggle() {
  const [theme, setTheme] = useTheme();
  const next = theme === 'dark' ? 'light' : 'dark';
  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={() => setTheme(next)}
      aria-label={`Switch to ${next} mode`}
      className="h-8 w-8 shrink-0"
    >
      {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </Button>
  );
}

export function AppHeader({ screen, onNavigate, uploading, pendingReview }) {
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/85 backdrop-blur-xl">
      <div className="mx-auto flex h-14 max-w-[1280px] items-center gap-3 px-3 sm:px-4 md:px-8">
        <a
          href="#/upload"
          onClick={(e) => {
            e.preventDefault();
            onNavigate('upload');
          }}
          className="flex shrink-0 items-baseline gap-2"
        >
          <span className="text-sm font-semibold tracking-tight">TTPS</span>
          <span className="hidden text-[10px] font-medium uppercase tracking-widest text-muted-foreground lg:inline">
            Tenughat · 2 × 210 MW
          </span>
        </a>

        <nav className="flex min-w-0 flex-1 justify-center sm:justify-start sm:pl-4" aria-label="Main">
          <div className="inline-flex rounded-lg border border-border p-0.5">
            {NAV.map(({ screen: s, label, short, icon: Icon }) => {
              const active = s === screen;
              const badge = s === 'upload' && (uploading || pendingReview > 0);
              return (
                <a
                  key={s}
                  href={`#/${s}`}
                  aria-current={active ? 'page' : undefined}
                  onClick={(e) => {
                    e.preventDefault();
                    onNavigate(s);
                  }}
                  className={cn(
                    'relative inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors sm:px-3',
                    active ? 'bg-foreground text-background' : 'text-muted-foreground hover:text-foreground'
                  )}
                >
                  <Icon className="hidden h-3.5 w-3.5 min-[400px]:inline" />
                  <span className="sm:hidden">{short}</span>
                  <span className="hidden sm:inline">{label}</span>
                  {badge && (
                    <span
                      className={cn(
                        'absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full',
                        pendingReview > 0 ? 'bg-attention' : 'bg-foreground',
                        uploading && 'animate-pulse',
                        active && 'ring-2 ring-background'
                      )}
                      title={pendingReview > 0 ? 'A page is waiting for review' : 'A page is being read'}
                    />
                  )}
                </a>
              );
            })}
          </div>
        </nav>

        <ThemeToggle />
      </div>
    </header>
  );
}
