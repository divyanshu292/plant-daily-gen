import { useCallback, useEffect, useMemo } from 'react';
import { ArrowClockwiseIcon, CircleNotchIcon, UploadSimpleIcon } from '@phosphor-icons/react';
import { Button } from '@/components/ui/button';
import { Notice } from '@/components/common/Notice';
import { MicroLabel, SectionTitle } from '@/components/common/Text';
import { StatTile } from '@/components/common/StatTile';
import { STICKY_TOP } from '@/components/common/sticky';
import { FyMonthPicker, FySelect } from '@/components/data/FyMonthPicker';
import { CoverageCalendar } from '@/components/data/CoverageCalendar';
import { MonthTable } from '@/components/data/MonthTable';
import { DayDetail } from '@/components/data/DayDetail';
import { ImportWorkbook } from '@/components/data/ImportWorkbook';
import { useAuth } from '@/lib/auth';
import { useApiData } from '@/lib/hooks';
import { add, dayStatus } from '@/lib/entries';
import { fmtDayList, fmtNum, isIsoDate, isMonth, localTodayIso, monthDays, monthLabel } from '@/lib/format';
import { cn } from '@/lib/utils';

export function DataScreen({ arg, health, navigate, backTo, onDataChanged }) {
  const { canEdit } = useAuth(); // view-only access: no upload, typing or import here
  const today = health.data?.today || localTodayIso();
  const day = isIsoDate(arg) ? arg : null;
  const month = day ? day.slice(0, 7) : isMonth(arg) ? arg : (health.data?.latestDate || today).slice(0, 7);

  useEffect(() => {
    if (!arg && (health.data || health.error)) navigate(`data/${month}`, { replace: true });
  }, [arg, health.data, health.error, month, navigate]);

  const entries = useApiData(`/entries?month=${month}`);
  const byDate = useMemo(() => Object.fromEntries((entries.data || []).map((e) => [e.date, e])), [entries.data]);

  const stats = useMemo(() => {
    const due = monthDays(month).filter((d) => dayStatus(null, d, today) !== 'future');
    const missing = due.filter((d) => ['none', 'partial'].includes(dayStatus(byDate[d], d, today)));
    const list = entries.data || [];
    return {
      due: due.length,
      withData: due.length - missing.length,
      missing,
      u1: add(...list.map((e) => e.u1Gen)),
      u2: add(...list.map((e) => e.u2Gen)),
    };
  }, [month, today, byDate, entries.data]);

  const pick = useCallback((iso) => navigate(`data/${iso}`), [navigate]);
  const close = useCallback(() => backTo(`data/${month}`), [backTo, month]);
  const toMonth = useCallback((m) => navigate(`data/${m}`, { replace: true }), [navigate]);

  const onSaved = useCallback(
    (date, field, updated) => {
      entries.setData((list) => {
        const rows = list || [];
        const i = rows.findIndex((e) => e.date === date);
        if (i === -1) return [...rows, updated].sort((a, b) => a.date.localeCompare(b.date));
        // Merge only this field: answers to overlapping saves can arrive out of order.
        const next = [...rows];
        next[i] = {
          ...next[i],
          [field]: updated[field] ?? null,
          source: updated.source,
          reportId: updated.reportId,
          updatedAt: updated.updatedAt,
        };
        return next;
      });
      onDataChanged?.();
    },
    [entries.setData, onDataChanged]
  );

  const loaded = !!entries.data;

  return (
    <div className={cn('space-y-10', STICKY_TOP)}>
      <section className="space-y-4 md:space-y-6">
        <div className="space-y-2">
          <MicroLabel>Stored data</MicroLabel>
          <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-3">
            <h1 className="text-3xl font-semibold leading-[1.05] tracking-tight md:text-5xl">{monthLabel(month)}</h1>
            <FySelect month={month} onChange={toMonth} todayMonth={today.slice(0, 7)} />
          </div>
        </div>
        <FyMonthPicker month={month} todayMonth={today.slice(0, 7)} onChange={toMonth} fySelect={false} />
      </section>

      {entries.error && (
        <Notice
          tone="error"
          title="Could not load this month"
          action={
            <Button variant="outline" size="touch" onClick={entries.reload}>
              <ArrowClockwiseIcon weight="bold" />
              Try again
            </Button>
          }
        >
          {entries.error.message}
        </Notice>
      )}

      {!loaded && entries.loading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <CircleNotchIcon weight="bold" className="h-4 w-4 animate-spin" /> Loading {monthLabel(month)}
        </div>
      )}

      {loaded && (
        <>
          <div className="grid gap-10 lg:grid-cols-[minmax(0,7fr)_minmax(0,4fr)] lg:gap-12">
            {/* Phones: the month's figures first, then the calendar. Wide screens: calendar on the left. */}
            <div className="space-y-5 lg:col-start-2 lg:row-start-1 lg:pt-9">
              <div className="grid grid-cols-2 gap-x-6 gap-y-7">
                <StatTile
                  label="Days with data"
                  value={stats.withData}
                  unit={`of ${stats.due}`}
                  caption={
                    stats.due === 0
                      ? 'The month has not started.'
                      : stats.missing.length
                        ? `${stats.missing.length} missing`
                        : 'Every day so far has data.'
                  }
                />
                <StatTile
                  label="Generation"
                  value={fmtNum(add(stats.u1, stats.u2) ?? 0, 2)}
                  unit="MU"
                  caption={`Station. Unit 1 ${fmtNum(stats.u1 ?? 0, 2)}, Unit 2 ${fmtNum(stats.u2 ?? 0, 2)}`}
                />
              </div>
              {stats.missing.length > 0 && (
                <Notice
                  tone="attention"
                  title={`No data for ${stats.missing.length} day${stats.missing.length === 1 ? '' : 's'}`}
                  action={
                    canEdit && (
                      <Button variant="outline" size="touch" className="bg-transparent" onClick={() => navigate('upload')}>
                        <UploadSimpleIcon weight="bold" />
                        Upload pages
                      </Button>
                    )
                  }
                >
                  {fmtDayList(stats.missing)}. Each day&apos;s figures are on the next morning&apos;s page.
                  {canEdit && ' You can also select a day and type the values.'}
                </Notice>
              )}
            </div>

            <section className="space-y-4 lg:col-start-1 lg:row-start-1">
              <SectionTitle
                title="Coverage"
                hint={canEdit ? 'Select a day to see or change its values.' : 'Select a day to see its values.'}
              />
              <CoverageCalendar month={month} byDate={byDate} today={today} selected={day} onPick={pick} />
            </section>
          </div>

          <section id="month-days" className="space-y-2">
            <SectionTitle
              title={`Days · ${monthLabel(month, 'short')}`}
              hint={`Coal, oil, DM water, backing down (BD), outage and H₂ are Unit 1 + Unit 2. Outage is forced plus planned. Select a row to ${canEdit ? 'edit' : 'see the day'}.`}
            />
            <MonthTable month={month} byDate={byDate} today={today} selected={day} onPick={pick} />
          </section>
        </>
      )}

      {canEdit && (
        <ImportWorkbook
          onImported={() => {
            entries.reload();
            onDataChanged?.();
          }}
        />
      )}

      {day && (
        <DayDetail
          date={day}
          entry={byDate[day]}
          loaded={loaded}
          today={today}
          onClose={close}
          onSaved={onSaved}
          onNavigate={(iso) => navigate(`data/${iso}`, { replace: true })}
        />
      )}
    </div>
  );
}
