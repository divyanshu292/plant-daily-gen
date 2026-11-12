import { useRef, useState } from 'react';
import { CircleNotchIcon, EyeIcon, EyeSlashIcon } from '@phosphor-icons/react';
import { Button } from '@/components/ui/button';
import { Notice } from '@/components/common/Notice';
import { MicroLabel } from '@/components/common/Text';
import { STATION, ThemeToggle } from '@/components/AppNav';
import { api } from '@/lib/api';

// Same look as the app's other fields (see ValueInput); 16 px text so iOS does not zoom in.
const INPUT =
  'h-11 w-full min-w-0 rounded-md border border-input bg-background px-3 text-base transition-colors md:text-sm ' +
  'placeholder:text-muted-foreground/40 hover:border-foreground/30 focus:border-foreground/60 focus:outline-none focus:ring-1 focus:ring-ring';

/** Page frame for the signed-out states: the app's brand bar, then one narrow column. */
export function AuthShell({ children }) {
  return (
    <div className="flex min-h-dvh flex-col bg-background text-foreground">
      <header className="pt-[env(safe-area-inset-top)]">
        <div className="pad-x-safe mx-auto flex h-12 max-w-[1280px] items-center gap-3 md:h-14">
          <div className="flex min-w-0 items-baseline gap-2.5">
            <span className="text-[15px] font-semibold tracking-tight md:text-sm">TTPS</span>
            <span className="truncate text-[10px] font-medium uppercase tracking-widest text-muted-foreground">{STATION}</span>
          </div>
          <div className="-mr-3 ml-auto flex items-center md:mr-0">
            <ThemeToggle />
          </div>
        </div>
      </header>
      {/* Phones: near the top, where the keyboard leaves it visible. Wider screens: in the middle. */}
      <main className="pad-x-safe flex flex-1 flex-col pb-[calc(1.5rem+env(safe-area-inset-bottom))] pt-8 md:items-center md:justify-center md:pb-24 md:pt-0">
        <div className="w-full max-w-sm">{children}</div>
      </main>
    </div>
  );
}

function errorText(err) {
  if (err?.status === 401) return 'Wrong email or password';
  return err?.message || 'Could not sign in. Try again.';
}

/**
 * Email and password. There is no sign-up: the super admin creates every account.
 * `note`: why the person is here again (their session ended). `onSignedIn(answer)`: the login answer.
 */
export function LoginScreen({ note, onSignedIn }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const passwordRef = useRef(null);

  const submit = async (e) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const data = await api('/auth/login', { method: 'POST', json: { email: email.trim(), password } });
      await onSignedIn(data);
    } catch (err) {
      setError(errorText(err));
      // A wrong password is the usual mistake: put the cursor back there.
      if (err?.status === 401) {
        passwordRef.current?.focus();
        passwordRef.current?.select();
      }
    } finally {
      setBusy(false); // harmless once signed in, when this screen is gone
    }
  };

  return (
    <AuthShell>
      <div className="space-y-2">
        <MicroLabel>Daily system report</MicroLabel>
        <h1 className="text-3xl font-semibold leading-[1.05] tracking-tight md:text-5xl">Sign in</h1>
      </div>

      {(error || note) && (
        <Notice tone={error ? 'error' : 'info'} title={error || note} className="mt-6" />
      )}

      <form className="mt-8 space-y-5" onSubmit={submit}>
        <div className="space-y-1.5">
          <MicroLabel as="label" htmlFor="login-email" className="block">
            Email
          </MicroLabel>
          <input
            id="login-email"
            name="email"
            type="email"
            autoComplete="username"
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
            enterKeyHint="next"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className={INPUT}
          />
        </div>

        <div className="space-y-1.5">
          <MicroLabel as="label" htmlFor="login-password" className="block">
            Password
          </MicroLabel>
          <div className="relative">
            <input
              ref={passwordRef}
              id="login-password"
              name="password"
              type={showPassword ? 'text' : 'password'}
              autoComplete="current-password"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              enterKeyHint="go"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={`${INPUT} pr-12`}
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              aria-label={showPassword ? 'Hide password' : 'Show password'}
              aria-pressed={showPassword}
              aria-controls="login-password"
              className="absolute inset-y-0 right-0 flex w-11 items-center justify-center rounded-r-md text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-ring"
            >
              {showPassword ? <EyeSlashIcon weight="fill" className="h-5 w-5" /> : <EyeIcon weight="fill" className="h-5 w-5" />}
            </button>
          </div>
        </div>

        <Button type="submit" className="h-11 w-full disabled:opacity-70" disabled={busy}>
          {busy && <CircleNotchIcon weight="bold" className="animate-spin" />}
          {busy ? 'Signing in' : 'Sign in'}
        </Button>
      </form>

      <p className="mt-6 text-xs text-muted-foreground">Ask the super admin for an account.</p>
    </AuthShell>
  );
}
