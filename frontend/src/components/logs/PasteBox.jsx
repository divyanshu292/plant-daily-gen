import { useEffect, useRef, useState } from 'react';
import {
  ArrowClockwiseIcon,
  CalendarBlankIcon,
  CheckCircleIcon,
  CircleNotchIcon,
  ClipboardTextIcon,
  ClockIcon,
  PencilSimpleIcon,
  PlusIcon,
  WarningCircleIcon,
  XIcon,
} from '@phosphor-icons/react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { MicroLabel } from '@/components/common/Text';
import { useElapsed } from '@/lib/hooks';
import { fmtDate, fmtDayList, isIsoDate } from '@/lib/format';
import { cn } from '@/lib/utils';

const plural = (n, word) => `${n.toLocaleString('en-IN')} ${word}${n === 1 ? '' : 's'}`;

function Reading({ startedAt }) {
  const seconds = useElapsed(startedAt);
  return <span className="tabular">Reading · {seconds} s</span>;
}

/** One paste in the list under the box: waiting, being read, saved, or not read. */
function PasteItem({ item, date, queue, onEdit, navigate }) {
  const { state, result } = item;
  const days = result?.days || [];
  const values = days.reduce((n, d) => n + d.values, 0);
  const toCheck = days.reduce((n, d) => n + d.toCheck, 0);
  const undated = days.reduce((n, d) => n + d.undated, 0);
  const elsewhere = days.filter((d) => d.date !== date);

  const Icon = { queued: ClockIcon, reading: CircleNotchIcon, saved: CheckCircleIcon, error: WarningCircleIcon }[state];
  return (
    <li className="flex gap-3 py-2.5">
      <Icon
        weight={state === 'reading' ? 'bold' : 'fill'}
        className={cn(
          'mt-0.5 h-4 w-4 shrink-0',
          state === 'reading' && 'animate-spin',
          state === 'error' || toCheck > 0 ? 'text-attention' : state === 'saved' ? 'text-foreground' : 'text-muted-foreground'
        )}
      />
      <div className="min-w-0 flex-1 space-y-1 text-sm leading-snug">
        <div className="flex items-baseline justify-between gap-3">
          <span className="min-w-0 truncate font-mono text-xs text-muted-foreground">{item.title || 'Pasted text'}</span>
          {(state === 'saved' || state === 'error') && (
            <button
              type="button"
              onClick={() => queue.remove(item.key)}
              className="-my-2 -mr-2 flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
              aria-label="Take off the list"
            >
              <XIcon weight="bold" className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
        {state === 'queued' && <p className="text-muted-foreground">Waiting its turn</p>}
        {state === 'reading' && (
          <p className="text-muted-foreground">
            <Reading startedAt={item.startedAt} />
          </p>
        )}
        {state === 'saved' && (
          <>
            <p className="font-medium">
              {plural(values, 'value')} for {fmtDayList(days.map((d) => d.date))}
              {toCheck > 0 && <span className="text-attention"> · {toCheck} to check</span>}
            </p>
            {undated > 0 && (
              <p className="text-xs text-muted-foreground">
                {plural(undated, 'section')} with no date written went under {fmtDate(item.usedDate || days[0]?.date, 'short')}.
              </p>
            )}
            {result.notes?.map((n) => (
              <p key={n} className="text-xs text-attention">
                {n}
              </p>
            ))}
            {elsewhere.length > 0 && (
              <Button variant="ghost" size="sm" className="-ml-3 h-9" onClick={() => navigate(`logs/${elsewhere[elsewhere.length - 1].date}`, { replace: true })}>
                <CalendarBlankIcon weight="bold" />
                Go to {fmtDate(elsewhere[elsewhere.length - 1].date, 'short')}
              </Button>
            )}
          </>
        )}
        {state === 'error' && (
          <>
            <p role="alert" className="text-attention">
              {item.error}
            </p>
            <div className="flex flex-wrap gap-x-1">
              <Button variant="ghost" size="sm" className="-ml-3 h-9" onClick={() => queue.retry(item.key)}>
                <ArrowClockwiseIcon weight="bold" />
                Try again
              </Button>
              <Button variant="ghost" size="sm" className="h-9" onClick={() => onEdit(item)}>
                <PencilSimpleIcon weight="bold" />
                Back in the box
              </Button>
            </div>
          </>
        )}
      </div>
    </li>
  );
}

/**
 * Where an admin pastes the WhatsApp messages: a whole day at once or piece by
 * piece as they come, without waiting for the one before to be read. Each piece
 * is filed under the date written in it (or WhatsApp's stamp); one with neither
 * goes under the day shown under the box (see useLogQueue), which can be changed.
 * `empty`: whether the day on screen has no readings (undefined while loading).
 */
export function PasteBox({ date, empty, queue, navigate }) {
  const [open, setOpen] = useState(empty === true);
  const [text, setText] = useState('');
  const [chosen, setChosen] = useState(null); // a day picked for undated pieces; null follows the screen
  const [clipboardError, setClipboardError] = useState(null);
  const [canReadClipboard] = useState(() => typeof navigator !== 'undefined' && !!navigator.clipboard?.readText);
  const box = useRef(null);
  const undatedDay = chosen || queue.followDay || date;
  const hasItems = queue.items.length > 0;

  useEffect(() => {
    queue.setScreenDay(date);
  }, [queue.setScreenDay, date]);

  // A day with nothing yet opens the box by itself; a day with readings keeps it out of the way,
  // unless something is typed in it or pastes are on the list.
  const keepOpen = useRef(false);
  keepOpen.current = !!text.trim() || hasItems;
  useEffect(() => {
    if (empty !== undefined && !keepOpen.current) setOpen(empty);
  }, [empty, date]);

  const submit = (e) => {
    e?.preventDefault();
    if (!text.trim()) return;
    queue.add(text, chosen);
    setText('');
    box.current?.focus();
  };

  // One tap: what WhatsApp copied goes straight on the list.
  const fromClipboard = async () => {
    setClipboardError(null);
    try {
      const pasted = await navigator.clipboard.readText();
      if (pasted.trim()) queue.add(pasted, chosen);
      else setClipboardError('Nothing is copied. Copy the messages in WhatsApp first.');
    } catch {
      setClipboardError('The browser would not share what is copied. Paste it into the box instead.');
      box.current?.focus();
    }
  };

  const edit = (item) => {
    setText((t) => (t.trim() ? `${t.replace(/\s+$/, '')}\n\n${item.text}` : item.text));
    queue.remove(item.key);
    box.current?.focus();
  };

  const finished = queue.items.filter((i) => i.state === 'saved' || i.state === 'error').length;

  if (!open && !hasItems) {
    return (
      <Button variant="outline" size="touch" className="w-full sm:w-auto" onClick={() => setOpen(true)}>
        <PlusIcon weight="bold" />
        Paste messages
      </Button>
    );
  }

  return (
    <Card className="px-4 py-4 md:px-5">
      <form onSubmit={submit} className="space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 space-y-1">
            <MicroLabel as="label" htmlFor="log-paste">
              Paste the WhatsApp messages
            </MicroLabel>
            <p className="text-xs leading-relaxed text-muted-foreground">
              A whole day at once, or piece by piece as they come. Paste the next one while the last is read: they add up.
            </p>
          </div>
          {!empty && !hasItems && (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="-mr-2 -mt-2 h-11 w-11 shrink-0 text-muted-foreground md:h-8 md:w-8"
              onClick={() => setOpen(false)}
              aria-label="Close"
            >
              <XIcon weight="bold" />
            </Button>
          )}
        </div>

        <textarea
          id="log-paste"
          ref={box}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) submit(e);
          }}
          rows={5}
          spellCheck={false}
          autoCapitalize="off"
          autoCorrect="off"
          placeholder={'Mill- 2A   11-11-2026\nLPD-Main-2.3/B.S-19,26/HPD- 30,41,45,41 …'}
          className={cn(
            // 16 px text below md: iOS zooms the page into any smaller input.
            'block max-h-[50dvh] min-h-[7.5rem] w-full resize-y rounded-md border border-input bg-background px-3 py-2.5 font-mono text-base leading-snug md:text-[13px]',
            'placeholder:text-muted-foreground/40 hover:border-foreground/30',
            'focus:border-foreground/60 focus:outline-none focus:ring-1 focus:ring-ring'
          )}
        />

        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          {canReadClipboard && (
            <Button type="button" variant="outline" size="touch" onClick={fromClipboard}>
              <ClipboardTextIcon weight="bold" />
              Save what is copied
            </Button>
          )}
          <Button type="submit" size="touch" disabled={!text.trim()}>
            Read and save
          </Button>
        </div>
        {clipboardError && (
          <p role="alert" className="text-xs text-attention">
            {clipboardError}
          </p>
        )}

        {/* The day for pieces with no date of their own: a native date input lies over the day. */}
        <p className="text-xs leading-6 text-muted-foreground">
          A piece with no date goes under{' '}
          <label className="relative -my-2 inline-block cursor-pointer rounded-md px-1 py-2 font-medium text-foreground underline decoration-dotted underline-offset-4 hover:bg-accent focus-within:ring-1 focus-within:ring-ring">
            {fmtDate(undatedDay, 'weekday')}
            <input
              type="date"
              value={undatedDay}
              onChange={(e) => isIsoDate(e.target.value) && setChosen(e.target.value)}
              onClick={(e) => {
                try {
                  e.currentTarget.showPicker?.();
                } catch {
                  // Some browsers refuse outside a direct gesture; the input still works by keyboard.
                }
              }}
              aria-label="Day for pieces with no date"
              className="absolute inset-0 h-full w-full cursor-pointer appearance-none opacity-0 [color-scheme:light] dark:[color-scheme:dark]"
            />
          </label>{' '}
          {chosen ? (
            <button type="button" onClick={() => setChosen(null)} className="rounded-md px-1 underline underline-offset-4 hover:text-foreground">
              undo
            </button>
          ) : queue.followDay ? (
            '(the date of the last piece)'
          ) : (
            '(the day on screen)'
          )}
        </p>

        {hasItems && (
          <div className="border-t border-border pt-1">
            <ul className="divide-y divide-border/60">
              {queue.items.map((item) => (
                <PasteItem key={item.key} item={item} date={date} queue={queue} onEdit={edit} navigate={navigate} />
              ))}
            </ul>
            {finished > 1 && (
              <Button type="button" variant="ghost" size="sm" className="-ml-3 h-9 text-muted-foreground" onClick={queue.clearFinished}>
                Clear the list
              </Button>
            )}
          </div>
        )}
      </form>
    </Card>
  );
}
