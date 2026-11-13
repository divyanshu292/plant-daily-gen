import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from '@/lib/api';

let seq = 0;
const newKey = () => `paste-${Date.now().toString(36)}-${(seq++).toString(36)}`;

/** The first line with something on it, to tell pastes apart in the list. */
function firstLine(text) {
  return (text.split('\n').find((l) => l.trim()) || '').trim().slice(0, 80);
}

// A piece with no date of its own goes under the date of the last dated piece,
// if that was pasted this recently; otherwise under the day on screen.
const FOLLOW_MS = 20 * 60 * 1000;
const following = (last) => (last && Date.now() - last.at < FOLLOW_MS ? last.date : null);

/**
 * Pastes for the Logs tab. A day's messages come in several pieces, so a person
 * pastes one, then the next, without waiting: each is read in its turn, one at
 * a time. Lives in App, so the pastes keep going (and their results stay) while
 * the person looks at another screen.
 *
 * A piece with no date written in it (the second half of a message, say) goes
 * under the day chosen for it, else the date of the last dated piece pasted
 * (they come together), else the day on screen. Worked out when its turn comes,
 * not when it is pasted, so it follows a dated piece still being read ahead of it.
 *
 * item: { key, text, title, date (chosen, or null), state, result, error, startedAt, usedDate }
 * state: queued | reading | saved | error
 */
export function useLogQueue() {
  const [items, setItems] = useState([]);
  const [saved, setSaved] = useState({ version: 0, days: [] }); // the days the last saved paste filled
  const [lastDated, setLastDated] = useState(null); // { date, at } of the last paste with a date in it
  const [tick, setTick] = useState(0);
  const running = useRef(false);
  const screenDay = useRef(null);
  const lastDatedRef = useRef(null);

  const patch = useCallback((key, changes) => {
    setItems((list) => list.map((i) => (i.key === key ? { ...i, ...changes } : i)));
  }, []);

  const add = useCallback((text, date = null) => {
    if (!text.trim()) return;
    setItems((list) => [...list, { key: newKey(), text, title: firstLine(text), date, state: 'queued' }]);
  }, []);

  const setScreenDay = useCallback((date) => {
    screenDay.current = date;
  }, []);

  // One paste at a time, in the order they were added.
  useEffect(() => {
    if (running.current) return;
    const next = items.find((i) => i.state === 'queued');
    if (!next) return;
    running.current = true;
    const usedDate = next.date || following(lastDatedRef.current) || screenDay.current;
    patch(next.key, { state: 'reading', startedAt: Date.now(), usedDate, error: null });
    api('/logs', { method: 'POST', json: { text: next.text, date: usedDate || undefined } })
      .then((result) => {
        const dated = (result.days || []).filter((d) => d.sections > d.undated);
        if (dated.length) {
          // Set on the ref at once: the next piece may start before the app draws again.
          lastDatedRef.current = { date: dated[dated.length - 1].date, at: Date.now() };
          setLastDated(lastDatedRef.current);
        }
        patch(next.key, { state: 'saved', result });
        setSaved((s) => ({ version: s.version + 1, days: result.days || [] }));
      })
      .catch((err) => patch(next.key, { state: 'error', error: err.message }))
      .finally(() => {
        running.current = false;
        setTick((t) => t + 1);
      });
  }, [items, tick, patch]);

  const retry = useCallback((key) => patch(key, { state: 'queued', error: null }), [patch]);
  const remove = useCallback((key) => setItems((list) => list.filter((i) => i.key !== key)), []);
  const clearFinished = useCallback(() => setItems((list) => list.filter((i) => i.state === 'queued' || i.state === 'reading')), []);

  const busy = items.some((i) => i.state === 'queued' || i.state === 'reading');
  // The day an undated piece pasted now would go under, unless one is chosen (for the box to say).
  const followDay = following(lastDated);
  return useMemo(
    () => ({ items, add, retry, remove, clearFinished, setScreenDay, followDay, busy, saved }),
    [items, add, retry, remove, clearFinished, setScreenDay, followDay, busy, saved]
  );
}
