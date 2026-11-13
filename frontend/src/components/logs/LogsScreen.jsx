import { useEffect, useRef, useState } from 'react';
import { ArrowClockwiseIcon, ArrowsLeftRightIcon, CalendarDotsIcon, CircleNotchIcon } from '@phosphor-icons/react';
import { Button } from '@/components/ui/button';
import { Segmented } from '@/components/ui/segmented';
import { Notice } from '@/components/common/Notice';
import { MicroLabel } from '@/components/common/Text';
import { DateNav } from '@/components/common/DateNav';
import { LogSection } from '@/components/logs/LogSection';
import { PasteBox } from '@/components/logs/PasteBox';
import { api } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { useApiData } from '@/lib/hooks';
import { addDays, fmtDate, isIsoDate, localTodayIso } from '@/lib/format';
import { cn } from '@/lib/utils';

const plural = (n, word) => `${n.toLocaleString('en-IN')} ${word}${n === 1 ? '' : 's'}`;

/** "Mill 2A, Mill 2C and ESP 2" */
function nameList(names) {
  return names.length > 1 ? `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}` : names[0];
}

/**
 * The readings staff send on WhatsApp, a day at a time: an admin pastes the
 * day's messages, they are filed under a fixed set of fields, and every value
 * is shown beside the same value on another day.
 */
export function LogsScreen({ arg, health, navigate, queue }) {
  const { canEdit } = useAuth(); // view-only access reads; it does not paste, correct or remove
  const today = health.data?.today || localTodayIso();
  const date = isIsoDate(arg) ? arg : null;
  // The day to compare with. null: for each section, the last earlier day it was reported.
  const [other, setOther] = useState(null);
  // all | changed | check. null: "changed" when the day differs from the other one, else "all".
  const [picked, setPicked] = useState(null);

  // With no date in the address the server answers with the latest day that has readings.
  const day = useApiData(date ? `/logs?date=${date}${other ? `&with=${other}` : ''}` : '/logs', { keep: true });
  useEffect(() => {
    if (!date && day.data?.date) navigate(`logs/${day.data.date}`, { replace: true });
  }, [date, day.data, navigate]);

  // Another day starts from the usual comparison and the usual rows.
  useEffect(() => {
    setOther(null);
    setPicked(null);
  }, [date]);

  const setDate = (d) => navigate(`logs/${d}`, { replace: true });
  const data = day.data && (!date || day.data.date === date) ? day.data : null;
  const sections = data?.sections || [];
  const { setData, reload } = day;

  // After each saved paste: show it if it filled this day, else go to the day it filled.
  const lastSaved = useRef(queue.saved.version);
  useEffect(() => {
    if (queue.saved.version === lastSaved.current) return;
    lastSaved.current = queue.saved.version;
    const dates = queue.saved.days.map((d) => d.date);
    if (!dates.length) return;
    if (!date || dates.includes(date)) reload();
    else navigate(`logs/${dates[dates.length - 1]}`, { replace: true });
  }, [queue.saved, date, reload, navigate]);

  const actionsFor = (id) => ({
    edit: async (key, value) => setData(await api(`/logs/${date}/${id}`, { method: 'PUT', json: { key, value, with: other || undefined } })),
    checked: async () => setData(await api(`/logs/${date}/${id}`, { method: 'PUT', json: { checked: true, with: other || undefined } })),
    remove: async () => setData(await api(`/logs/${date}/${id}${other ? `?with=${other}` : ''}`, { method: 'DELETE' })),
  });

  const values = sections.reduce((n, s) => n + s.counts.values + s.extra.length, 0);
  const changed = sections.reduce((n, s) => n + s.counts.changed, 0);
  const toCheck = sections.reduce((n, s) => n + s.counts.toCheck, 0);
  const compared = sections.some((s) => s.previousDate);
  const comparedDates = [...new Set(sections.map((s) => s.previousDate).filter(Boolean))].sort();
  const options = [
    { value: 'all', label: `All · ${values}` },
    ...(compared ? [{ value: 'changed', label: `Changed · ${changed}` }] : []),
    ...(toCheck > 0 ? [{ value: 'check', label: `To check · ${toCheck}` }] : []),
  ];
  // A choice that no longer applies (the last thing to check was checked) falls back to the usual one.
  const mode = options.some((o) => o.value === picked) ? picked : changed > 0 ? 'changed' : 'all';
  const visible = sections.filter((s) =>
    mode === 'changed' ? s.counts.changed > 0 : mode === 'check' ? s.counts.toCheck > 0 : true
  );
  const latest = data?.latest;

  return (
    <div className="space-y-6 md:space-y-8">
      <section className="space-y-3 md:flex md:items-end md:justify-between md:gap-6 md:space-y-0">
        <div className="min-w-0 space-y-2">
          <MicroLabel>Logs · readings sent on WhatsApp</MicroLabel>
          {/* On phones the date navigator below is the title. */}
          <h1 className="sr-only md:not-sr-only md:text-5xl md:font-semibold md:leading-[1.05] md:tracking-tight">
            {date ? fmtDate(date, 'long') : 'Logs'}
          </h1>
        </div>
        {date && <DateNav value={date} onChange={setDate} max={addDays(today, 1)} className="-mx-1 md:mx-0 md:shrink-0" />}
        {date && latest && date !== latest && (
          <div className="flex justify-center md:hidden">
            <Button variant="ghost" size="touch" className="text-muted-foreground" onClick={() => setDate(latest)}>
              <CalendarDotsIcon weight="bold" />
              Latest day with readings · {fmtDate(latest, 'short')}
            </Button>
          </div>
        )}
      </section>

      {date && latest && date !== latest && (
        <div className="-mt-4 hidden md:block">
          <Button variant="ghost" size="sm" className="-ml-3 text-muted-foreground" onClick={() => setDate(latest)}>
            <CalendarDotsIcon weight="bold" />
            Go to the latest day with readings ({fmtDate(latest, 'short')})
          </Button>
        </div>
      )}

      {canEdit && date && <PasteBox date={date} empty={data ? sections.length === 0 : undefined} queue={queue} navigate={navigate} />}

      {day.error && (
        <Notice
          tone="error"
          title="Could not load the readings"
          action={
            <Button variant="outline" size="touch" onClick={reload}>
              <ArrowClockwiseIcon weight="bold" />
              Try again
            </Button>
          }
        >
          {day.error.message}
        </Notice>
      )}

      {!data && day.loading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <CircleNotchIcon weight="bold" className="h-4 w-4 animate-spin" /> Loading the readings
        </div>
      )}

      {data && sections.length === 0 && (
        <Notice
          tone="info"
          title={`No readings for ${fmtDate(date, 'medium')}.`}
          action={
            (data.earlier || data.later) && (
              <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
                {data.earlier && (
                  <Button variant="outline" size="touch" className="bg-transparent" onClick={() => setDate(data.earlier)}>
                    Earlier: {fmtDate(data.earlier, 'weekday')}
                  </Button>
                )}
                {data.later && (
                  <Button variant="outline" size="touch" className="bg-transparent" onClick={() => setDate(data.later)}>
                    Later: {fmtDate(data.later, 'weekday')}
                  </Button>
                )}
              </div>
            )
          }
        >
          {canEdit ? 'Paste the messages dated this day and they will show here.' : 'Nothing has been pasted for this day yet.'}
        </Notice>
      )}

      {data && sections.length > 0 && (
        <div className={cn('space-y-4 transition-opacity', day.loading && 'opacity-60')}>
          <div className="space-y-3">
            <p className="text-sm leading-relaxed text-muted-foreground">
              <span className="font-medium text-foreground tabular">
                {plural(values, 'value')} in {plural(sections.length, 'section')}
              </span>
              {compared ? (
                <>
                  {' · '}
                  {changed > 0 ? (
                    <span className="font-medium text-foreground tabular">{changed} changed</span>
                  ) : (
                    'nothing changed'
                  )}{' '}
                  {other
                    ? `against ${fmtDate(other, 'medium')}`
                    : `since ${comparedDates.length === 1 ? fmtDate(comparedDates[0], 'medium') : 'the last day each was reported'}`}
                </>
              ) : other ? (
                ` · none of these were reported on ${fmtDate(other, 'medium')}`
              ) : (
                ' · no earlier day to compare with yet'
              )}
            </p>

            <div className="flex flex-wrap items-center gap-2">
              {/* The other day: a native date input lies over the pill. */}
              <label className="relative inline-flex h-11 cursor-pointer items-center gap-2 rounded-full border border-input px-4 text-sm font-medium transition-colors hover:bg-accent focus-within:ring-1 focus-within:ring-ring md:h-9 md:text-xs">
                <ArrowsLeftRightIcon weight="bold" className="h-4 w-4 shrink-0 text-muted-foreground md:h-3.5 md:w-3.5" />
                {other ? `Compared with ${fmtDate(other, 'weekday')}` : 'Compare with another day'}
                <input
                  type="date"
                  value={other || ''}
                  max={today}
                  onChange={(e) => {
                    const v = e.target.value;
                    if (isIsoDate(v) && v !== date) setOther(v);
                  }}
                  onClick={(e) => {
                    try {
                      e.currentTarget.showPicker?.();
                    } catch {
                      // Some browsers refuse outside a direct gesture; the input still works by keyboard.
                    }
                  }}
                  aria-label="Day to compare with"
                  className="absolute inset-0 h-full w-full cursor-pointer appearance-none opacity-0 [color-scheme:light] dark:[color-scheme:dark]"
                />
              </label>
              {other && (
                <Button variant="ghost" size="touch" className="text-muted-foreground" onClick={() => setOther(null)}>
                  Back to the day before
                </Button>
              )}
            </div>

            {options.length > 1 && <Segmented options={options} value={mode} onChange={setPicked} aria-label="Which values to show" className="md:max-w-md" />}
          </div>

          {data.absent.length > 0 && (
            <Notice tone="info" title={`Not here yet: ${plural(data.absent.length, 'section')} that came on ${fmtDate(data.absent[0].date, 'short')}`}>
              {nameList(data.absent.map((a) => a.name))}.
            </Notice>
          )}

          {visible.length === 0 && (
            <p className="py-6 text-center text-sm text-muted-foreground">
              {mode === 'changed' ? 'Every value is the same as on the other day.' : 'Nothing left to check.'}
            </p>
          )}

          <div className="space-y-3">
            {visible.map((s) => (
              <LogSection
                // Remounted when the rows shown change, so sections start open where there is something to look at.
                key={`${s.id}-${mode}`}
                section={s}
                mode={mode}
                startOpen={mode !== 'all'}
                canEdit={canEdit}
                actions={actionsFor(s.id)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
