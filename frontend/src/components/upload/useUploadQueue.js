import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { prepareImage } from '@/lib/image';

let seq = 0;
const newKey = () => `item-${Date.now().toString(36)}-${(seq++).toString(36)}`;

const IMAGE_NAME = /\.(jpe?g|png|webp|heic|heif|gif|bmp|tiff?)$/i;
export const WORKING = ['queued', 'preparing', 'reading', 'loading'];

/**
 * Pages chosen for upload, read one after another, plus earlier reports opened
 * from the history list. Lives in App so an upload keeps going (and its result
 * stays) while the person looks at another screen.
 *
 * item: { key, kind: 'upload'|'history', name, file, state, report, error, startedAt, prepared }
 * state: queued | preparing | reading | loading | saved | needs_review | error
 */
export function useUploadQueue() {
  const [items, setItems] = useState([]);
  const [version, setVersion] = useState(0); // bumps whenever stored data may have changed
  const [tick, setTick] = useState(0);
  const running = useRef(false);
  const itemsRef = useRef(items);
  itemsRef.current = items;

  const patch = useCallback((key, changes) => {
    setItems((list) => list.map((i) => (i.key === key ? { ...i, ...changes } : i)));
  }, []);

  const addFiles = useCallback((fileList) => {
    const files = Array.from(fileList || []);
    if (!files.length) return 0;
    const added = files.map((file) => {
      const isImage = file.type?.startsWith('image/') || IMAGE_NAME.test(file.name || '');
      if (isImage) return { key: newKey(), kind: 'upload', file, name: file.name || 'image', state: 'queued' };
      return {
        key: newKey(),
        kind: 'upload',
        file: null,
        name: file.name || 'file',
        state: 'error',
        error: 'This is not an image. Upload a photo or screenshot (JPG or PNG) of the report page.',
      };
    });
    setItems((list) => [...list, ...added]);
    return added.length;
  }, []);

  // Read queued pages one at a time.
  useEffect(() => {
    if (running.current) return;
    const next = items.find((i) => i.state === 'queued');
    if (!next) return;
    running.current = true;
    (async () => {
      try {
        patch(next.key, { state: 'preparing', error: null, report: null });
        const prepared = await prepareImage(next.file);
        patch(next.key, {
          state: 'reading',
          startedAt: Date.now(),
          prepared: prepared.resized ? { from: prepared.from, to: prepared.to } : null,
        });
        const form = new FormData();
        form.append('file', prepared.file, prepared.file.name);
        const report = await api('/reports', { method: 'POST', body: form });
        patch(next.key, { state: report.status === 'saved' ? 'saved' : 'needs_review', report });
        setVersion((v) => v + 1);
      } catch (err) {
        patch(next.key, { state: 'error', error: err?.message || 'The upload failed.' });
      } finally {
        running.current = false;
        setTick((t) => t + 1);
      }
    })();
  }, [items, tick, patch]);

  /** Show an earlier report (from the history list). Returns the item key. */
  const openReport = useCallback(
    (summary) => {
      const existing = itemsRef.current.find((i) => i.report?.id === summary.id);
      if (existing) return existing.key;
      const key = newKey();
      setItems((list) => [
        ...list,
        { key, kind: 'history', name: summary.fileName || 'Uploaded page', state: 'loading', report: summary },
      ]);
      api(`/reports/${summary.id}`)
        .then((report) => patch(key, { state: report.status === 'saved' ? 'saved' : 'needs_review', report }))
        .catch((err) => patch(key, { state: 'error', error: err.message, reloadId: summary.id }));
      return key;
    },
    [patch]
  );

  const retry = useCallback(
    (key) => {
      const item = itemsRef.current.find((i) => i.key === key);
      if (!item) return;
      if (item.file) {
        patch(key, { state: 'queued', error: null, report: null, startedAt: null });
      } else if (item.reloadId) {
        patch(key, { state: 'loading', error: null });
        api(`/reports/${item.reloadId}`)
          .then((report) => patch(key, { state: report.status === 'saved' ? 'saved' : 'needs_review', report }))
          .catch((err) => patch(key, { state: 'error', error: err.message }));
      }
    },
    [patch]
  );

  const remove = useCallback((key) => setItems((list) => list.filter((i) => i.key !== key)), []);

  const clearFinished = useCallback(
    () => setItems((list) => list.filter((i) => WORKING.includes(i.state) || i.state === 'needs_review')),
    []
  );

  const markConfirmed = useCallback(
    (key, report) => {
      patch(key, { state: 'saved', report });
      setVersion((v) => v + 1);
    },
    [patch]
  );

  const busy = items.some((i) => i.kind === 'upload' && WORKING.includes(i.state));
  const pendingReview = items.filter((i) => i.state === 'needs_review').length;

  return useMemo(
    () => ({ items, version, busy, pendingReview, addFiles, openReport, retry, remove, clearFinished, markConfirmed }),
    [items, version, busy, pendingReview, addFiles, openReport, retry, remove, clearFinished, markConfirmed]
  );
}
