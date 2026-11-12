import { useEffect, useState } from 'react';
import {
  CloudArrowUpIcon,
  DatabaseIcon,
  FileTextIcon,
  HouseIcon,
  MoonIcon,
  SunIcon,
  UserCircleIcon,
  UsersThreeIcon,
} from '@phosphor-icons/react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useTheme } from '@/lib/hooks';

// `need`: who sees the tab. Upload writes data (admins and the super admin); Users is the super admin's alone.
const NAV = [
  { screen: 'home', label: 'Home', short: 'Home', icon: HouseIcon },
  { screen: 'upload', label: 'Upload', short: 'Upload', icon: CloudArrowUpIcon, need: 'edit' },
  { screen: 'daily', label: 'Daily report', short: 'Report', icon: FileTextIcon },
  { screen: 'data', label: 'Data', short: 'Data', icon: DatabaseIcon },
  { screen: 'users', label: 'Users', short: 'Users', icon: UsersThreeIcon, need: 'superAdmin' },
  { screen: 'account', label: 'Account', short: 'Account', icon: UserCircleIcon },
];

/** The tabs a person has: 4 for a viewer, 5 for an admin, 6 for the super admin. */
export function navFor({ canEdit, isSuperAdmin }) {
  return NAV.filter((n) => (n.need === 'edit' ? canEdit : n.need === 'superAdmin' ? isSuperAdmin : true));
}

export const STATION = 'Tenughat · 2 × 210 MW';

function linkProps(screen, onNavigate) {
  return {
    href: `#/${screen}`,
    onClick: (e) => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return; // let "open in new tab" work
      e.preventDefault();
      onNavigate(screen);
    },
  };
}

/** Upload's badge: a dot while a page is being read, in the attention colour while one waits for review. */
function UploadDot({ uploading, pendingReview, className }) {
  if (!uploading && !(pendingReview > 0)) return null;
  const text = pendingReview > 0 ? 'A page is waiting for review' : 'A page is being read';
  return (
    <>
      <span
        aria-hidden
        title={text}
        className={cn(
          'absolute h-2 w-2 rounded-full ring-2 ring-background',
          pendingReview > 0 ? 'bg-attention' : 'bg-foreground',
          uploading && 'animate-pulse',
          className
        )}
      />
      <span className="sr-only">({text})</span>
    </>
  );
}

export function ThemeToggle() {
  const [theme, setTheme] = useTheme();
  const next = theme === 'dark' ? 'light' : 'dark';
  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={() => setTheme(next)}
      aria-label={`Switch to ${next} mode`}
      className="h-11 w-11 shrink-0 text-muted-foreground hover:text-foreground md:h-8 md:w-8"
    >
      {theme === 'dark' ? <SunIcon weight="fill" /> : <MoonIcon weight="fill" />}
    </Button>
  );
}

/**
 * Top bar. On a phone it is slim: brand, where you are, theme toggle (the tab bar
 * does the navigating). From md up it carries the segmented nav as well.
 */
export function AppHeader({ items, screen, onNavigate, uploading, pendingReview }) {
  const current = items.find((n) => n.screen === screen);
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/80 pt-[env(safe-area-inset-top)] backdrop-blur-xl backdrop-saturate-[1.8]">
      <div className="pad-x-safe mx-auto flex h-12 max-w-[1280px] items-center gap-3 md:h-14">
        <a {...linkProps('home', onNavigate)} className="flex min-w-0 items-baseline gap-2.5" aria-label="TTPS home">
          <span className="text-[15px] font-semibold tracking-tight md:text-sm">TTPS</span>
          <span className="truncate text-[10px] font-medium uppercase tracking-widest text-muted-foreground md:hidden">
            {screen === 'home' ? STATION : current?.label}
          </span>
          <span className="hidden text-[10px] font-medium uppercase tracking-widest text-muted-foreground lg:inline">
            {STATION}
          </span>
        </a>

        <nav className="hidden min-w-0 flex-1 pl-4 md:flex" aria-label="Main">
          <div className="inline-flex rounded-lg border border-border p-0.5">
            {items.map(({ screen: s, label, icon: Icon }) => {
              const active = s === screen;
              return (
                <a
                  key={s}
                  {...linkProps(s, onNavigate)}
                  aria-current={active ? 'page' : undefined}
                  className={cn(
                    'relative inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
                    active ? 'bg-foreground text-background' : 'text-muted-foreground hover:text-foreground'
                  )}
                >
                  <Icon weight="fill" className="h-3.5 w-3.5" />
                  {label}
                  {s === 'upload' && (
                    <UploadDot uploading={uploading} pendingReview={pendingReview} className="-right-0.5 -top-0.5" />
                  )}
                </a>
              );
            })}
          </div>
        </nav>

        <div className="-mr-3 ml-auto flex items-center md:mr-0">
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}

/**
 * Scrolling down shrinks the phone tab bar; scrolling up, reaching the top or tapping a tab
 * restores it. A little hysteresis so a wobbling finger does not make it flicker.
 */
function useMinimizeOnScroll() {
  const [minimized, setMinimized] = useState(false);
  useEffect(() => {
    let last = window.scrollY;
    let frame = 0;
    const update = () => {
      frame = 0;
      const max = document.documentElement.scrollHeight - window.innerHeight;
      const y = Math.min(Math.max(window.scrollY, 0), Math.max(max, 0)); // ignore the rubber band
      if (y < 48) {
        setMinimized(false);
        last = y;
        return;
      }
      if (Math.abs(y - last) < 16) return;
      setMinimized(y > last);
      last = y;
    };
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(update);
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => {
      window.removeEventListener('scroll', onScroll);
      if (frame) cancelAnimationFrame(frame);
    };
  }, []);
  return [minimized, setMinimized];
}

/**
 * Phone navigation, in the iOS 26 manner: a floating Liquid Glass capsule above the home
 * indicator, content visible beneath it, and a lens that slides to the active tab.
 * Hidden from md up, where the header carries the nav.
 */
export function TabBar({ items, screen, onNavigate, uploading, pendingReview }) {
  const [minimized, setMinimized] = useMinimizeOnScroll();
  const count = items.length; // 4 to 6, by role
  const index = Math.max(0, items.findIndex((n) => n.screen === screen));
  const go = (s) => {
    setMinimized(false);
    onNavigate(s);
  };

  return (
    <nav
      aria-label="Main"
      data-min={minimized}
      className={cn(
        'group glass fixed z-40 mx-auto max-w-[420px] rounded-full md:hidden',
        'bottom-[var(--tabbar-bottom)] left-[max(1rem,env(safe-area-inset-left))] right-[max(1rem,env(safe-area-inset-right))]',
        'h-[62px] transition-[height] duration-300 ease-spring data-[min=true]:h-12 motion-reduce:transition-none'
      )}
    >
      {/* The lens: one pill that slides between tabs. Same width as a tab (the list has px-1).
          Inline styles because the tab count depends on the role and Tailwind cannot build classes at run time. */}
      <span
        aria-hidden
        className="glass-lens absolute bottom-1 left-1 top-1 rounded-full transition-transform duration-300 ease-spring motion-reduce:transition-none"
        style={{ width: `calc((100% - 0.5rem) / ${count})`, transform: `translateX(${index * 100}%)` }}
      />
      <ul className="relative grid h-full px-1" style={{ gridTemplateColumns: `repeat(${count}, minmax(0, 1fr))` }}>
        {items.map(({ screen: s, short, icon: Icon }) => {
          const active = s === screen;
          return (
            <li key={s} className="min-w-0">
              <a
                {...linkProps(s, go)}
                aria-current={active ? 'page' : undefined}
                className={cn(
                  'group/tab flex h-full select-none flex-col items-center justify-center rounded-full transition-colors duration-200',
                  '[-webkit-tap-highlight-color:transparent] [-webkit-touch-callout:none]',
                  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring',
                  active ? 'text-foreground' : 'text-muted-foreground active:text-foreground'
                )}
              >
                <span className="relative transition-transform duration-150 group-active/tab:scale-90 motion-reduce:transition-none">
                  <Icon weight="fill" className="h-[25px] w-[25px]" />
                  {s === 'upload' && (
                    <UploadDot uploading={uploading} pendingReview={pendingReview} className="-right-1 -top-0.5" />
                  )}
                </span>
                {/* Six tabs leave about 46 px each on a 320 px phone: one line, clipped rather than wrapped. */}
                <span
                  className={cn(
                    'mt-[3px] max-h-3 max-w-full overflow-hidden whitespace-nowrap px-0.5 text-[10px] font-medium leading-3 tracking-normal transition-[opacity,max-height,margin] duration-300 ease-spring',
                    'group-data-[min=true]:mt-0 group-data-[min=true]:max-h-0 group-data-[min=true]:opacity-0 motion-reduce:transition-none',
                    active && 'font-semibold'
                  )}
                >
                  {short}
                </span>
              </a>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
