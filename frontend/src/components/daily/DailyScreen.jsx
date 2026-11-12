import { useEffect, useMemo, useState } from 'react';
import { ArrowClockwiseIcon, CalendarDotsIcon, CircleNotchIcon, ImageIcon, UploadSimpleIcon } from '@phosphor-icons/react';
import { Button } from '@/components/ui/button';
import { Notice } from '@/components/common/Notice';
import { MicroLabel } from '@/components/common/Text';
import { StatTile } from '@/components/common/StatTile';
import { DateNav } from '@/components/common/DateNav';
import { STICKY_TOP } from '@/components/common/sticky';
import { IMAGE_RETENTION_DAYS, ImageViewer, imageKept } from '@/components/common/ImageViewer';
import { PerformanceTable } from '@/components/daily/PerformanceTable';
import { apiUrl } from '@/lib/api';
import { useApiData } from '@/lib/hooks';
import { addDays, fmtDate, fmtDayList, fmtNum, isIsoDate, localTodayIso } from '@/lib/format';
import { cn } from '@/lib/utils';

function stockCaption(stock) {
  if (!stock) return 'No stock figure on record yet.';
  if (stock.source === 'report') return `As printed on the page for ${fmtDate(stock.asOf, 'short')}.`;
  return `Worked out from the ${fmtDate(stock.asOf, 'medium')} figure, plus receipts, minus consumption.`;
}

function stationDay(rows, key) {
  return rows?.find((r) => r.key === key)?.stn?.day ?? null;
}

export function DailyScreen({ arg, health, navigate }) {
  const today = health.data?.today || localTodayIso();
  const fallback = health.data?.latestDate || today;
  const date = isIsoDate(arg) ? arg : null;
  const [viewing, setViewing] = useState(false);

  // No date in the address yet: show the latest day with data.
  useEffect(() => {
    if (!date && (health.data || health.error)) navigate(`daily/${fallback}`, { replace: true });
  }, [date, health.data, health.error, fallback, navigate]);

  const perf = useApiData(date ? `/performance/${date}` : null, { keep: true });
  const reports = useApiData(date ? `/reports?date=${date}` : null);
  // The recorded live feed for the day, shown only when it covers the whole day. Errors are ignored.
  const liveDay = useApiData(date ? `/live/day?date=${date}` : null);
  const feedMu = liveDay.data?.complete && liveDay.data.date === date ? liveDay.data.energy?.stn : null;

  const report = useMemo(() => {
    const forDay = (reports.data || []).filter((r) => r.dataDate === date);
    return forDay.find((r) => r.status === 'saved') || forDay[0] || null;
  }, [reports.data, date]);

  const setDate = (d) => navigate(`daily/${d}`, { replace: true });
  const p = perf.data;
  const missingMonth = p?.missing?.month || [];
  const genDay = stationDay(p?.rows, 'gen');
  const plfDay = stationDay(p?.rows, 'plf');
  const latest = health.data?.latestDate;

  return (
    <div className={cn('space-y-8 md:space-y-10', STICKY_TOP)}>
      <section className="space-y-3 md:flex md:items-end md:justify-between md:gap-6 md:space-y-0">
        <div className="min-w-0 space-y-2">
          <MicroLabel>
            Daily report{p?.fy ? ` · FY ${p.fy}–${String(p.fy + 1).slice(2)}` : ''}
          </MicroLabel>
          {/* On phones the date navigator below is the title. */}
          <h1 className="sr-only md:not-sr-only md:text-5xl md:font-semibold md:leading-[1.05] md:tracking-tight">
            {date ? fmtDate(date, 'long') : 'Daily report'}
          </h1>
        </div>
        {date && <DateNav value={date} onChange={setDate} max={today} className="-mx-1 md:mx-0 md:shrink-0" />}
        {date && latest && date !== latest && (
          <div className="flex justify-center md:hidden">
            <Button variant="ghost" size="touch" className="text-muted-foreground" onClick={() => setDate(latest)}>
              <CalendarDotsIcon weight="bold" />
              Latest day with data · {fmtDate(latest, 'short')}
            </Button>
          </div>
        )}
      </section>

      {date && latest && date !== latest && (
        <div className="-mt-6 hidden md:block">
          <Button variant="ghost" size="sm" className="-ml-3 text-muted-foreground" onClick={() => setDate(latest)}>
            <CalendarDotsIcon weight="bold" />
            Go to the latest day with data ({fmtDate(latest, 'short')})
          </Button>
        </div>
      )}

      {perf.error && (
        <Notice
          tone="error"
          title="Could not load the report"
          action={
            <Button variant="outline" size="touch" onClick={perf.reload}>
              <ArrowClockwiseIcon weight="bold" />
              Try again
            </Button>
          }
        >
          {perf.error.message}
        </Notice>
      )}

      {!p && perf.loading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <CircleNotchIcon weight="bold" className="h-4 w-4 animate-spin" /> Working out the figures
        </div>
      )}

      {p && (
        <div className={cn('space-y-10 transition-opacity', perf.loading && 'opacity-60')}>
          {(!p.hasData || missingMonth.length > 0 || p.missing?.year > 0) && (
            <div className="space-y-2">
              {!p.hasData && (
                <Notice
                  tone="attention"
                  title={`No data is stored for ${fmtDate(date, 'medium')}.`}
                  action={
                    <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
                      <Button variant="outline" size="touch" className="bg-transparent" onClick={() => navigate('upload')}>
                        <UploadSimpleIcon weight="bold" />
                        Upload the page dated {fmtDate(addDays(date, 1), 'short')}
                      </Button>
                      <Button variant="ghost" size="touch" onClick={() => navigate(`data/${date}`)}>
                        Enter values by hand
                      </Button>
                    </div>
                  }
                >
                  The day columns are left empty. Month and year figures count this day as zero.
                </Notice>
              )}
              {missingMonth.length > 0 && !(missingMonth.length === 1 && missingMonth[0] === date && !p.hasData) && (
                <Notice tone="attention" title="Month and year figures are incomplete">
                  No data for {fmtDayList(missingMonth)}
                  {p.missing.year > missingMonth.length && `, and ${p.missing.year - missingMonth.length} more day${p.missing.year - missingMonth.length === 1 ? '' : 's'} earlier in the year`}
                  . Those days count as zero until their pages are uploaded or entered.
                </Notice>
              )}
              {missingMonth.length === 0 && p.missing?.year > 0 && (
                <Notice tone="attention" title="Year figures are incomplete">
                  {p.missing.year} day{p.missing.year === 1 ? '' : 's'} since 1 April {p.missing.year === 1 ? 'has' : 'have'} no data and
                  count as zero.
                </Notice>
              )}
            </div>
          )}

          <div className="space-y-6">
            <div className="grid grid-cols-2 gap-x-6 gap-y-7 lg:grid-cols-4">
              <StatTile
                label="Generation"
                value={p.hasData ? fmtNum(genDay, 2) : '—'}
                unit="MU"
                caption={p.hasData ? `Station, Unit 1 + Unit 2, on ${fmtDate(date, 'short')}` : 'No data for the day'}
              />
              <StatTile
                label="PLF"
                value={p.hasData ? fmtNum(plfDay, 2) : '—'}
                unit="%"
                caption={p.hasData ? 'Station plant load factor for the day' : 'No data for the day'}
              />
              <StatTile
                label="Coal stock"
                value={p.stocks?.coal ? fmtNum(p.stocks.coal.value, 2) : '—'}
                unit="MT"
                caption={stockCaption(p.stocks?.coal)}
              />
              <StatTile
                label="Oil stock"
                value={p.stocks?.oil ? fmtNum(p.stocks.oil.value, 3) : '—'}
                unit="KL"
                caption={stockCaption(p.stocks?.oil)}
              />
            </div>

            {typeof feedMu === 'number' && (
              <p className="-mt-2 text-xs text-muted-foreground tabular">
                Live feed estimate <span className="font-medium text-foreground">{fmtNum(feedMu, 2)} MU</span>
                {p.hasData && genDay != null && ` (page ${fmtNum(genDay, 2)})`}
              </p>
            )}

            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="text-xs leading-relaxed text-muted-foreground">
                {p.gcv ? (
                  <>
                    Heat rate uses GCV <span className="font-medium text-foreground tabular">{fmtNum(p.gcv.value, 0)} kcal/kg</span>, the lab
                    figure for {fmtDate(p.gcv.date, 'medium')}.
                  </>
                ) : (
                  'No GCV on record, so heat rate cannot be worked out.'
                )}
              </div>
              {report && !imageKept(report) ? (
                <span className="text-xs text-muted-foreground">
                  The uploaded page was deleted {IMAGE_RETENTION_DAYS} days after upload; its figures are kept.
                </span>
              ) : report ? (
                <Button variant="outline" size="touch" className="shrink-0" onClick={() => setViewing(true)}>
                  <ImageIcon weight="bold" />
                  View the uploaded page
                  {report.status !== 'saved' && ' (not saved yet)'}
                </Button>
              ) : (
                reports.data && (
                  <span className="text-xs text-muted-foreground">
                    No page uploaded for this day{p.hasData ? '; its data came from the workbook or by hand.' : '.'}
                  </span>
                )
              )}
            </div>
          </div>

          <PerformanceTable report={p} />

          {p.notes?.length > 0 && (
            <section className="space-y-3">
              <MicroLabel as="h2">Notes</MicroLabel>
              <ul className="space-y-2 text-sm leading-relaxed text-muted-foreground">
                {p.notes.map((n) => (
                  <li key={n} className="flex gap-2.5">
                    <span aria-hidden className="mt-[0.6em] h-1 w-1 shrink-0 rounded-full bg-muted-foreground/60" />
                    <span>{n}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}

      {viewing && report && (
        <ImageViewer
          src={apiUrl(`/reports/${report.id}/image`)}
          title={`Page dated ${fmtDate(report.reportDate, 'medium')} · data for ${fmtDate(report.dataDate, 'medium')}`}
          onClose={() => setViewing(false)}
        />
      )}
    </div>
  );
}
