import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { ArrowClockwiseIcon, CircleNotchIcon } from '@phosphor-icons/react';
import { Button } from '@/components/ui/button';
import { Notice } from '@/components/common/Notice';
import { AuthShell, LoginScreen } from '@/components/auth/LoginScreen';
import { ACCESS_CHANGED_EVENT, api, SIGNED_OUT_EVENT } from '@/lib/api';

export const ROLE_LABELS = { super_admin: 'Super admin', admin: 'Admin', viewer: 'Viewer' };

const SESSION_ENDED = 'Your session ended. Sign in again.';

const AuthContext = createContext({
  user: null,
  setUser: () => {},
  logout: async () => {},
  canEdit: false,
  isSuperAdmin: false,
});

// Answers that carry a user are { user: {...} }; a bare user is accepted too.
function userOf(data) {
  const u = data?.user ?? data;
  return u && typeof u === 'object' && u.id && u.role ? u : null;
}

/**
 * Asks the server who is signed in, then shows the app (signed in), the login
 * screen (signed out) or a "cannot reach the server" message. The app itself
 * mounts only when signed in, so nothing polls or loads for a signed-out visitor,
 * and signing out unmounts it with everything it held (the upload queue too).
 */
export function AuthProvider({ children }) {
  // status: checking | signedIn | signedOut | unreachable
  const [state, setState] = useState({ status: 'checking' });
  const [retrying, setRetrying] = useState(false);
  const signingOut = useRef(false);

  const check = useCallback(async (signal) => {
    try {
      const user = userOf(await api('/auth/me', { signal }));
      setState(user ? { status: 'signedIn', user } : { status: 'signedOut' });
    } catch (err) {
      if (err?.name === 'AbortError') return;
      setState(err?.status === 401 ? { status: 'signedOut' } : { status: 'unreachable', error: err });
    }
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    check(ctrl.signal);
    return () => ctrl.abort();
  }, [check]);

  const retry = useCallback(async () => {
    setRetrying(true);
    await check();
    setRetrying(false);
  }, [check]);

  // Server down at first: try again by itself when the phone gets its connection back.
  const unreachable = state.status === 'unreachable';
  useEffect(() => {
    if (!unreachable) return undefined;
    window.addEventListener('online', retry);
    return () => window.removeEventListener('online', retry);
  }, [unreachable, retry]);

  // Any API call answered 401 (lib/api.js): the session expired, was ended elsewhere or the account was removed.
  useEffect(() => {
    const onSignedOut = () => {
      if (signingOut.current) return; // our own sign-out; no "session ended" note for that
      setState((s) => (s.status === 'signedIn' ? { status: 'signedOut', note: SESSION_ENDED } : s));
    };
    window.addEventListener(SIGNED_OUT_EVENT, onSignedOut);
    return () => window.removeEventListener(SIGNED_OUT_EVENT, onSignedOut);
  }, []);

  // The super admin may change someone's access while they are signed in. Ask again
  // after a 403 and when the app comes back to the front, so the tabs and edit
  // controls follow (a 401 here is handled by the signed-out listener above).
  const signedInNow = state.status === 'signedIn';
  useEffect(() => {
    if (!signedInNow) return undefined;
    const refresh = async () => {
      if (document.hidden) return;
      try {
        const user = userOf(await api('/auth/me'));
        if (user) setState((s) => (s.status === 'signedIn' ? { ...s, user } : s));
      } catch {
        // Offline or the server hiccuped: keep what we have.
      }
    };
    window.addEventListener(ACCESS_CHANGED_EVENT, refresh);
    document.addEventListener('visibilitychange', refresh);
    return () => {
      window.removeEventListener(ACCESS_CHANGED_EVENT, refresh);
      document.removeEventListener('visibilitychange', refresh);
    };
  }, [signedInNow]);

  // Each state starts at the top of the page.
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [state.status]);

  const setUser = useCallback((next) => {
    const user = userOf(next);
    if (user) setState((s) => (s.status === 'signedIn' ? { ...s, user } : s));
  }, []);

  /**
   * Ends this session on the server, then shows the login screen. Rejects (with
   * the ApiError) when the server could not be told, because the cookie is HttpOnly
   * and only the server can clear it: the person stays signed in and can try again.
   */
  const logout = useCallback(async () => {
    signingOut.current = true;
    try {
      await api('/auth/logout', { method: 'POST' });
    } catch (err) {
      if (err?.status !== 401) throw err;
    } finally {
      signingOut.current = false;
    }
    // The next person to sign in on this phone starts at Home, not on this one's Account.
    window.history.replaceState(null, '', '#/home');
    setState({ status: 'signedOut' });
  }, []);

  const signedIn = useCallback(
    async (answer) => {
      const user = userOf(answer);
      if (user) setState({ status: 'signedIn', user });
      else await check(); // signed in, but the answer did not carry the user: ask for it
    },
    [check]
  );

  const role = state.user?.role;
  const value = useMemo(
    () => ({
      user: state.user ?? null,
      setUser,
      logout,
      canEdit: role === 'admin' || role === 'super_admin',
      isSuperAdmin: role === 'super_admin',
    }),
    [state.user, role, setUser, logout]
  );

  if (state.status === 'signedIn') return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
  if (state.status === 'signedOut') return <LoginScreen note={state.note} onSignedIn={signedIn} />;
  if (state.status === 'unreachable') return <Unreachable error={state.error} retrying={retrying} onRetry={retry} />;
  return <Checking />;
}

export function useAuth() {
  return useContext(AuthContext);
}

/** While /auth/me is on its way: a blank page, with a quiet mark only if it takes a moment (no spinner flash). */
function Checking() {
  return (
    <div className="flex min-h-dvh items-center justify-center bg-background text-foreground" aria-busy="true">
      <div className="animate-[fade-in_0.4s_ease-out_0.6s_both] text-center">
        <div className="text-[15px] font-semibold tracking-tight">TTPS</div>
        <div className="mt-1 text-[10px] font-medium uppercase tracking-widest text-muted-foreground">Connecting</div>
      </div>
    </div>
  );
}

/** The server did not answer (or answered with an error), so whether anyone is signed in is unknown. */
function Unreachable({ error, retrying, onRetry }) {
  const offline = !error?.status;
  return (
    <AuthShell>
      <Notice
        tone="error"
        title={offline ? 'Cannot reach the server' : 'The server could not check your sign-in'}
        action={
          <Button variant="outline" size="touch" onClick={onRetry} disabled={retrying} className="disabled:opacity-70">
            {retrying ? <CircleNotchIcon weight="bold" className="animate-spin" /> : <ArrowClockwiseIcon weight="bold" />}
            {retrying ? 'Trying again' : 'Try again'}
          </Button>
        }
      >
        {offline ? 'Check the connection and try again.' : error.message}
      </Notice>
    </AuthShell>
  );
}
