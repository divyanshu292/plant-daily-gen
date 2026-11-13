import { useCallback, useEffect, useRef } from 'react';
import { InfoIcon } from '@phosphor-icons/react';
import { Button } from '@/components/ui/button';
import { PageHeading, SectionTitle } from '@/components/common/Text';
import { DropZone } from '@/components/upload/DropZone';
import { PhonePicker } from '@/components/upload/PhonePicker';
import { UploadItem } from '@/components/upload/UploadItem';
import { RecentUploads } from '@/components/upload/RecentUploads';
import { WORKING } from '@/components/upload/useUploadQueue';
import { useApiData } from '@/lib/hooks';
import { fmtDate } from '@/lib/format';

function scrollToItem(key) {
  requestAnimationFrame(() => document.getElementById(key)?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
}

function pastedName(file, index, count) {
  if (file.name && !/^image\.(png|jpe?g|gif|webp)$/i.test(file.name)) return file.name;
  const ext = (file.type.split('/')[1] || 'png').replace('jpeg', 'jpg');
  const d = new Date();
  const stamp = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}-${String(d.getHours()).padStart(2, '0')}${String(d.getMinutes()).padStart(2, '0')}${String(d.getSeconds()).padStart(2, '0')}`;
  return `pasted-${stamp}${count > 1 ? `-${index + 1}` : ''}.${ext}`;
}

export function UploadScreen({ queue, health, navigate }) {
  const reports = useApiData('/reports?limit=60');
  const { addFiles, openReport, version } = queue;
  const firstVersion = useRef(version);

  // Refresh the history whenever an upload or a review finishes.
  useEffect(() => {
    if (version !== firstVersion.current) reports.reload();
  }, [version, reports.reload]);

  const add = useCallback(
    (files) => {
      const before = queue.items.length;
      if (addFiles(files) > 0 && before === 0) {
        requestAnimationFrame(() =>
          document.getElementById('this-session')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
        );
      }
    },
    [addFiles, queue.items.length]
  );

  // Paste a screenshot anywhere on this screen; drop files anywhere too.
  useEffect(() => {
    const onPaste = (e) => {
      const files = Array.from(e.clipboardData?.files || []).filter((f) => f.type.startsWith('image/'));
      if (!files.length) return;
      e.preventDefault();
      add(files.map((f, i) => new File([f], pastedName(f, i, files.length), { type: f.type })));
    };
    const onDragOver = (e) => e.preventDefault();
    const onDrop = (e) => {
      e.preventDefault();
      if (e.dataTransfer?.files?.length) add(e.dataTransfer.files);
    };
    window.addEventListener('paste', onPaste);
    window.addEventListener('dragover', onDragOver);
    window.addEventListener('drop', onDrop);
    return () => {
      window.removeEventListener('paste', onPaste);
      window.removeEventListener('dragover', onDragOver);
      window.removeEventListener('drop', onDrop);
    };
  }, [add]);

  const open = useCallback((summary) => scrollToItem(openReport(summary)), [openReport]);

  const items = queue.items;
  const queued = items.filter((i) => i.state === 'queued');
  const finished = items.filter((i) => !WORKING.includes(i.state) && i.state !== 'needs_review').length;

  return (
    <div className="space-y-8 md:space-y-12">
      <PageHeading
        eyebrow="Daily System Report"
        title="Upload the report page"
        subtitle="Each morning's page carries the previous day's figures. They are read from the image, the page's own sums are worked out again, and the day is saved when everything agrees."
      />

      <div className="space-y-3">
        {health.data?.latestDate && (
          <p className="text-xs text-muted-foreground">
            Latest day with data: <span className="font-medium text-foreground">{fmtDate(health.data.latestDate, 'weekdayYear')}</span>
          </p>
        )}
        <PhonePicker onFiles={add} className="md:hidden" />
        <div className="hidden md:block">
          <DropZone onFiles={add} />
        </div>
        {health.data && !health.data.extraction?.configured && (
          <p className="flex gap-2 text-xs leading-relaxed text-muted-foreground">
            <InfoIcon weight="fill" className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>
              The page reader is not configured on this server (no GEMINI_API_KEY). A development server answers with
              sample pages; anywhere else uploads will fail until the key is set.
            </span>
          </p>
        )}
      </div>

      {items.length > 0 && (
        <section id="this-session" className="scroll-mt-20 space-y-3">
          <SectionTitle
            title={`This session · ${items.length} ${items.length === 1 ? 'page' : 'pages'}`}
            hint={queue.busy ? 'Pages are read one at a time, in the order you added them.' : undefined}
          >
            {finished > 0 && (
              <Button variant="ghost" size="sm" onClick={queue.clearFinished}>
                Clear finished
              </Button>
            )}
          </SectionTitle>
          <div className="space-y-4">
            {items.map((item) => (
              <UploadItem
                key={item.key}
                item={item}
                ahead={item.state === 'queued' ? queued.indexOf(item) + items.filter((i) => ['preparing', 'reading'].includes(i.state)).length : 0}
                queue={queue}
                navigate={navigate}
              />
            ))}
          </div>
        </section>
      )}

      <RecentUploads reports={reports} onOpen={open} />
    </div>
  );
}
