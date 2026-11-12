import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';

// ---- hash route: #/ (home), #/upload, #/daily/2026-11-03, #/data/2026-11, #/data/2026-11-03 ----

export const SCREENS = ['home', 'upload', 'daily', 'data'];

/** Anything that is not a known screen (#/, #/home, #/whatever) is the home screen. */
function parseHash(hash) {
  const parts = hash.replace(/^#\/?/, '').split('/').filter(Boolean);
  if (!SCREENS.includes(parts[0])) return { screen: 'home', arg: null, hash: '#/home' };
  return { screen: parts[0], arg: parts[1] || null, hash: `#/${parts.join('/')}` };
}

export function useHashRoute() {
  const [route, setRoute] = useState(() => parseHash(window.location.hash));

  useEffect(() => {
    const sync = () => setRoute(parseHash(window.location.hash));
    window.addEventListener('popstate', sync);
    window.addEventListener('hashchange', sync);
    return () => {
      window.removeEventListener('popstate', sync);
      window.removeEventListener('hashchange', sync);
    };
  }, []);

  /** navigate('daily/2026-11-03'); { replace: true } keeps the history entry. */
  const navigate = useCallback((path, { replace = false } = {}) => {
    const hash = `#/${path.replace(/^[#/]+/, '')}`;
    if (hash === window.location.hash) return;
    const from = window.location.hash || '#/home';
    if (replace) window.history.replaceState(window.history.state, '', hash);
    else window.history.pushState({ from }, '', hash);
    setRoute(parseHash(hash));
  }, []);

  /** Go back if the previous entry is `hash` (keeps history tidy), else replace with it. */
  const backTo = useCallback(
    (path) => {
      const hash = `#/${path.replace(/^[#/]+/, '')}`;
      if (window.history.state?.from === hash) window.history.back();
      else navigate(path, { replace: true });
    },
    [navigate]
  );

  return { route, navigate, backTo };
}

// ---- theme ------------------------------------------------------------------------------

export function useTheme() {
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

// ---- data loading -----------------------------------------------------------------------

/**
 * GET a JSON path. Data is cleared when the path changes (so a month view never
 * shows another month's rows) but kept during reload(). With { keep: true } the
 * previous path's data stays visible until the new one arrives.
 */
export function useApiData(path, { keep = false } = {}) {
  // dataPath: the path `data` belongs to (may lag behind `path` while loading with keep)
  const [state, setState] = useState({ path, dataPath: null, data: null, error: null, loading: !!path });
  const [nonce, setNonce] = useState(0);
  const keepRef = useRef(keep);
  keepRef.current = keep;

  useEffect(() => {
    if (!path) {
      setState({ path, dataPath: null, data: null, error: null, loading: false });
      return undefined;
    }
    let cancelled = false;
    setState((s) =>
      s.path === path || keepRef.current
        ? { ...s, path, loading: true, error: null }
        : { path, dataPath: null, data: null, error: null, loading: true }
    );
    api(path)
      .then((data) => !cancelled && setState({ path, dataPath: path, data, error: null, loading: false }))
      .catch(
        (error) =>
          !cancelled &&
          setState((s) => ({ ...s, path, error, loading: false, ...(s.dataPath !== path && { data: null, dataPath: null }) }))
      );
    return () => {
      cancelled = true;
    };
  }, [path, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  const setData = useCallback(
    (next) => setState((s) => ({ ...s, data: typeof next === 'function' ? next(s.data) : next })),
    []
  );
  const current = state.path === path;
  return {
    data: current || keep ? state.data : null,
    error: current ? state.error : null,
    loading: current ? state.loading : !!path,
    reload,
    setData,
  };
}

/** Seconds since `startedAt` (ms), ticking once a second while `active`. */
export function useElapsed(startedAt, active = true) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active || !startedAt) return undefined;
    setNow(Date.now());
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [startedAt, active]);
  return startedAt ? Math.max(0, Math.floor((now - startedAt) / 1000)) : 0;
}

const dialogStack = [];

/**
 * Close on Escape (only the topmost dialog) and stop the page behind from
 * scrolling while a dialog is open.
 */
export function useDialog(onClose) {
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    const entry = { close: () => closeRef.current?.() };
    dialogStack.push(entry);
    const onKey = (e) => {
      if (e.key === 'Escape' && dialogStack[dialogStack.length - 1] === entry) entry.close();
    };
    window.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      dialogStack.splice(dialogStack.indexOf(entry), 1);
      document.body.style.overflow = prev;
    };
  }, []);
}
