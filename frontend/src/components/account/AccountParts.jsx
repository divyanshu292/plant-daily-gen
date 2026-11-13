// Pieces shared by the Account and Users screens: form fields, the access badge, IST times,
// the activity list, password generation and the "hand these over" card.
import { useState } from 'react';
import {
  CheckCircleIcon,
  CheckIcon,
  ClipboardTextIcon,
  CopyIcon,
  DotOutlineIcon,
  EyeIcon,
  EyeSlashIcon,
  FileXlsIcon,
  KeyIcon,
  PencilSimpleIcon,
  ShieldCheckIcon,
  SignInIcon,
  SignOutIcon,
  SlidersHorizontalIcon,
  TrashIcon,
  UploadSimpleIcon,
  UserCircleIcon,
  UserGearIcon,
  UserMinusIcon,
  UserPlusIcon,
  XIcon,
} from '@phosphor-icons/react';
import { Button } from '@/components/ui/button';
import { badgeVariants } from '@/components/ui/badge';
import { ROLE_LABELS } from '@/lib/auth';
import { cn } from '@/lib/utils';

// ---- access ------------------------------------------------------------------------------

export const ACCESS_TEXT = {
  super_admin: 'Full access, including onboarding people.',
  admin: 'Can upload reports and edit any data.',
  viewer: 'View only: you can see everything but not upload or edit.',
};

/** The same, said about someone else (Users screen). */
export const ACCESS_TEXT_OTHER = {
  admin: 'Can upload reports and edit any data.',
  viewer: 'Can see everything but not upload or edit.',
};

export const ROLE_OPTIONS = [
  { value: 'admin', label: 'Admin' },
  { value: 'viewer', label: 'Viewer' },
];

// Strongest access reads strongest: solid, then filled grey, then outline. No new colours.
const ROLE_VARIANT = { super_admin: 'default', admin: 'secondary', viewer: 'outline' };

export function RoleBadge({ role, className }) {
  // A span (not the div Badge renders) so it can sit inside a button or a sentence.
  return (
    <span className={cn(badgeVariants({ variant: ROLE_VARIANT[role] || 'outline' }), 'shrink-0 whitespace-nowrap', className)}>
      {ROLE_LABELS[role] || role}
    </span>
  );
}

// ---- form fields ---------------------------------------------------------------------------

// Same look as ValueInput: 44 px and 16 px text on phones (iOS zooms into smaller fields).
export const INPUT_CLASS = cn(
  'h-11 w-full min-w-0 rounded-md border border-input bg-background px-3 text-base transition-colors md:h-10 md:text-sm',
  'placeholder:text-muted-foreground/50 hover:border-foreground/30',
  'focus:border-foreground/60 focus:outline-none focus:ring-1 focus:ring-ring disabled:opacity-60'
);
export const INVALID_CLASS = 'border-attention ring-1 ring-attention hover:border-attention';

/** Label above, the control, then either the error (attention) or a muted hint. */
export function Field({ id, label, hint, error, children, className }) {
  return (
    <div className={cn('space-y-1.5', className)}>
      <label htmlFor={id} className="block text-sm font-medium">
        {label}
      </label>
      {children}
      {error ? (
        <p id={`${id}-note`} className="text-xs text-attention">
          {error}
        </p>
      ) : hint ? (
        <p id={`${id}-note`} className="text-xs text-muted-foreground">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

/** Password box with a show/hide button inside its right edge. */
export function PasswordInput({ id, value, onChange, invalid, className, ...props }) {
  const [shown, setShown] = useState(false);
  return (
    <div className={cn('relative', className)}>
      <input
        id={id}
        type={shown ? 'text' : 'password'}
        value={value}
        onChange={onChange}
        autoCapitalize="none"
        autoCorrect="off"
        spellCheck={false}
        aria-invalid={invalid || undefined}
        aria-describedby={`${id}-note`}
        className={cn(INPUT_CLASS, 'pr-12', invalid && INVALID_CLASS)}
        {...props}
      />
      <button
        type="button"
        onClick={() => setShown((s) => !s)}
        aria-label={shown ? 'Hide password' : 'Show password'}
        aria-pressed={shown}
        className="absolute inset-y-0 right-0 flex w-11 items-center justify-center rounded-r-md text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
      >
        {shown ? <EyeSlashIcon weight="bold" className="h-4 w-4" /> : <EyeIcon weight="bold" className="h-4 w-4" />}
      </button>
    </div>
  );
}

// ---- passwords to hand over -----------------------------------------------------------------

// No look-alikes (0/O, 1/l/I) so a password read off a phone screen is typed right first time.
const ALPHABET = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789';

export function generatePassword(length = 12) {
  // Drop bytes past the last whole multiple of the alphabet so every character is equally likely.
  const limit = 256 - (256 % ALPHABET.length);
  const out = [];
  while (out.length < length) {
    for (const b of crypto.getRandomValues(new Uint8Array(length * 2))) {
      if (b < limit && out.length < length) out.push(ALPHABET[b % ALPHABET.length]);
    }
  }
  return out.join('');
}

export async function copyText(text) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // Refused (e.g. not https): fall back to the old way below.
  }
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.setAttribute('readonly', '');
  ta.style.position = 'fixed';
  ta.style.opacity = '0';
  document.body.appendChild(ta);
  ta.select();
  let ok = false;
  try {
    ok = document.execCommand('copy');
  } catch {
    ok = false;
  }
  ta.remove();
  return ok;
}

/** Sign-in details shown once, to be passed on to the person. */
export function HandoverCard({ title, email, password, note, onDismiss }) {
  const [copy, setCopy] = useState(null); // null | 'copied' | 'failed'
  const doCopy = async () => {
    const ok = await copyText(`Email: ${email}\nPassword: ${password}\nSign in at ${window.location.origin}`);
    setCopy(ok ? 'copied' : 'failed');
  };
  return (
    <div role="status" className="rounded-lg bg-muted/60 py-3 pl-4 pr-1.5">
      <div className="flex items-start gap-3">
        <CheckCircleIcon weight="fill" className="mt-0.5 h-4 w-4 shrink-0 text-foreground" />
        <div className="min-w-0 flex-1 space-y-3 pb-1">
          <div className="text-sm font-medium leading-snug">{title}</div>
          <dl className="grid grid-cols-[auto_minmax(0,1fr)] items-baseline gap-x-4 gap-y-1.5 text-sm">
            <dt className="text-xs text-muted-foreground">Email</dt>
            <dd className="select-all break-all font-medium">{email}</dd>
            <dt className="text-xs text-muted-foreground">Password</dt>
            <dd className="select-all break-all font-mono text-[15px] font-medium tracking-wide">{password}</dd>
          </dl>
          {note && <p className="text-xs leading-relaxed text-muted-foreground">{note}</p>}
          <div className="flex flex-wrap items-center gap-3">
            <Button type="button" variant="outline" size="touch" className="bg-transparent" onClick={doCopy}>
              {copy === 'copied' ? <CheckIcon weight="bold" /> : <CopyIcon weight="bold" />}
              {copy === 'copied' ? 'Copied' : 'Copy'}
            </Button>
            {copy === 'failed' && <span className="text-xs text-attention">Could not copy. Select the text instead.</span>}
          </div>
        </div>
        <Button type="button" variant="ghost" size="icon-touch" className="-mt-1.5 shrink-0 rounded-full" onClick={onDismiss} aria-label="Dismiss">
          <XIcon weight="bold" />
        </Button>
      </div>
    </div>
  );
}

// ---- times in IST ---------------------------------------------------------------------------

const TZ = 'Asia/Kolkata';
const dayKeyFmt = new Intl.DateTimeFormat('en-GB', { timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit' });
const timeFmt = new Intl.DateTimeFormat('en-GB', { timeZone: TZ, hour: '2-digit', minute: '2-digit', hour12: false });
const dayFmt = new Intl.DateTimeFormat('en-GB', { timeZone: TZ, day: 'numeric', month: 'short' });
const dayYearFmt = new Intl.DateTimeFormat('en-GB', { timeZone: TZ, day: 'numeric', month: 'short', year: 'numeric' });
// Weekday on its own: en-GB puts a comma after it only when a year follows, which reads unevenly in a list.
const weekdayFmt = new Intl.DateTimeFormat('en-GB', { timeZone: TZ, weekday: 'short' });

function toDate(iso) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** 'YYYY-MM-DD' of the day in India. */
function istDay(d) {
  const p = Object.fromEntries(dayKeyFmt.formatToParts(d).map((x) => [x.type, x.value]));
  return `${p.year}-${p.month}-${p.day}`;
}

function relativeDay(d, now = new Date()) {
  const key = istDay(d);
  if (key === istDay(now)) return 'today';
  // India has no daylight saving, so a day is always 24 h.
  if (key === istDay(new Date(now.getTime() - 86400000))) return 'yesterday';
  return null;
}

export function fmtIstTime(iso) {
  const d = toDate(iso);
  return d ? timeFmt.format(d) : '';
}

/** "12 Nov 2026, 22:31 IST", for tooltips. */
export function fmtIstFull(iso) {
  const d = toDate(iso);
  return d ? `${dayYearFmt.format(d)}, ${timeFmt.format(d)} IST` : '';
}

/** "today, 22:31", "yesterday, 09:10", "10 Nov, 22:31", "10 Nov 2025, 22:31". */
export function fmtIstWhen(iso) {
  const d = toDate(iso);
  if (!d) return '';
  const now = new Date();
  const rel = relativeDay(d, now);
  const day = rel || (istDay(d).slice(0, 4) === istDay(now).slice(0, 4) ? dayFmt.format(d) : dayYearFmt.format(d));
  return `${day}, ${timeFmt.format(d)}`;
}

function dayHeading(d, now) {
  const rel = relativeDay(d, now);
  if (rel) return rel === 'today' ? 'Today' : 'Yesterday';
  const sameYear = istDay(d).slice(0, 4) === istDay(now).slice(0, 4);
  return `${weekdayFmt.format(d)} ${(sameYear ? dayFmt : dayYearFmt).format(d)}`;
}

// ---- activity -------------------------------------------------------------------------------

const ACTION_ICONS = {
  login: SignInIcon,
  logout: SignOutIcon,
  name_changed: PencilSimpleIcon,
  password_changed: KeyIcon,
  report_uploaded: UploadSimpleIcon,
  report_confirmed: CheckCircleIcon,
  entry_edited: PencilSimpleIcon,
  workbook_imported: FileXlsIcon,
  config_changed: SlidersHorizontalIcon,
  logs_pasted: ClipboardTextIcon,
  logs_edited: PencilSimpleIcon,
  logs_removed: TrashIcon,
  user_created: UserPlusIcon,
  user_updated: UserGearIcon,
  user_password_set: KeyIcon,
  user_deleted: UserMinusIcon,
  account_created: UserCircleIcon,
  role_changed: ShieldCheckIcon,
  password_set: KeyIcon,
};

/** Activity entries (newest first, as the API sends them) grouped by day in IST. */
export function ActivityList({ items, pageSize = 15, className }) {
  const [shown, setShown] = useState(pageSize);
  if (!items?.length) return <div className={cn('py-6 text-center text-sm text-muted-foreground', className)}>Nothing yet</div>;

  const now = new Date();
  const groups = [];
  for (const a of items.slice(0, shown)) {
    const d = toDate(a.at);
    const key = d ? istDay(d) : 'unknown';
    const last = groups[groups.length - 1];
    if (last && last.key === key) last.items.push(a);
    else groups.push({ key, label: d ? dayHeading(d, now) : 'Unknown time', items: [a] });
  }

  return (
    <div className={className}>
      <div className="divide-y divide-border">
        {groups.map((g) => (
          <section key={g.key} className="py-2.5 first:pt-1 last:pb-1">
            <h4 className="pb-1 text-[11px] font-medium uppercase tracking-widest text-muted-foreground tabular">{g.label}</h4>
            <ol>
              {g.items.map((a, i) => {
                const Icon = ACTION_ICONS[a.action] || DotOutlineIcon;
                return (
                  <li key={`${a.at}-${i}`} className="flex items-start gap-3 py-1.5 text-sm leading-snug">
                    <time dateTime={a.at} title={fmtIstFull(a.at)} className="w-11 shrink-0 text-muted-foreground tabular">
                      {fmtIstTime(a.at)}
                    </time>
                    <Icon weight="bold" className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                    <span className="min-w-0 flex-1 break-words">{a.text}</span>
                  </li>
                );
              })}
            </ol>
          </section>
        ))}
      </div>
      {items.length > shown && (
        <Button type="button" variant="ghost" size="touch" className="-ml-3 mt-1" onClick={() => setShown((n) => n + pageSize * 2)}>
          Show more ({items.length - shown} older)
        </Button>
      )}
    </div>
  );
}
